"""Running a step's independent jobs, and the build's independent steps, at once."""
from concurrent.futures import FIRST_COMPLETED, FIRST_EXCEPTION, ThreadPoolExecutor, wait
import os
import threading
import time


def workers(jobs=None):
    """One job per core (the owner's call, 11-15), never more than there are jobs."""
    cores = os.cpu_count() or 2
    return max(1, min(cores, cores if jobs is None else jobs))


def run_all(function, items, tries=1):
    """``function`` over ``items`` on threads (the jobs are mostly other programs), results in order. A failed job is
    tried again up to ``tries`` times; after a last failure no new job starts and the error is raised once the running
    ones end."""
    items = list(items)
    if not items:
        return []

    def attempt(item):
        for n in range(1, tries + 1):
            try:
                return function(item)
            except Exception:
                if n == tries:
                    raise
                time.sleep(n)

    with ThreadPoolExecutor(workers(len(items))) as pool:
        futures = [pool.submit(attempt, item) for item in items]
        done, _ = wait(futures, return_when=FIRST_EXCEPTION)
        failed = next((f for f in futures if f in done and f.exception() is not None), None)
        if failed is not None:
            for future in futures:
                future.cancel()
            pool.shutdown(wait=True)
            raise failed.exception()
        return [future.result() for future in futures]


class Step:
    """A build step's output folder, once it is built."""

    def __init__(self, name, function, args, kwargs, folder):
        self.name, self.function, self.args, self.kwargs, self.folder = name, function, args, kwargs, folder
        self.output = self.result = None

    def needs(self):
        return {x for x in _walk((self.args, self.kwargs)) if isinstance(x, Step)}


def _walk(value):
    if isinstance(value, Step):
        yield value
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)


def _resolve(value):
    if isinstance(value, Step):
        return value.output
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_resolve(v) for v in value)
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    return value


class Graph:
    """Steps that start as soon as the steps they read are built. ``add`` takes the step's function and arguments; any
    argument that is another step's handle becomes that step's output folder (``work/<name>`` unless ``output`` names
    another), and the step's handle keeps what its function returned."""

    def __init__(self, work, log):
        self.work, self.steps, self.lock, self.out = work, [], threading.Lock(), log

    def log(self, line, **_):
        """One line in one write: two steps starting at once must not run their lines together (the launcher reads
        them)."""
        with self.lock:
            self.out(line + '\n', end='', flush=True)

    def add(self, name, function, *args, output=None, **kwargs):
        step = Step(name, function, args, kwargs, output or self.work / name)
        self.steps.append(step)
        return step

    def _run(self, step):
        self.log('Building ' + step.name, flush=True)
        started = time.monotonic()
        step.result = step.function(*_resolve(step.args), output=step.folder, **_resolve(step.kwargs))
        step.output = str(step.folder)
        self.log(f'Finished {step.name} in {time.monotonic() - started:.0f} s', flush=True)

    def run(self):
        waiting, running, error = list(self.steps), {}, None
        with ThreadPoolExecutor(len(self.steps)) as pool:
            while waiting or running:
                if error is None:
                    for step in [s for s in waiting if all(n.output is not None for n in s.needs())]:
                        waiting.remove(step)
                        running[pool.submit(self._run, step)] = step
                if not running:
                    break
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    del running[future]
                    if future.exception() is not None and error is None:
                        error = future.exception()
                        self.log('A step failed; waiting for the running steps to end', flush=True)
        if error is not None:
            raise error
        if waiting:
            raise ValueError('Build steps wait on each other: ' + ', '.join(s.name for s in waiting))
