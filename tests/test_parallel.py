import tempfile
import threading
import unittest
from pathlib import Path

from pokemelee.parallel import Graph, run_all
from pokemelee.stages import sharing


class RunAllTest(unittest.TestCase):
    def test_keeps_order_and_retries(self):
        tries = {}
        lock = threading.Lock()

        def flaky(x):
            with lock:
                tries[x] = tries.get(x, 0) + 1
                if x == 3 and tries[x] == 1:
                    raise OSError("file in use")
            return x * 10

        self.assertEqual(run_all(flaky, range(6), tries=2), [0, 10, 20, 30, 40, 50])
        self.assertEqual(tries[3], 2)

    def test_raises_the_failure(self):
        def bad(x):
            if x == 2:
                raise ValueError("no")
            return x

        with self.assertRaises(ValueError):
            run_all(bad, range(4))


class GraphTest(unittest.TestCase):
    def test_steps_get_the_outputs_they_read(self):
        with tempfile.TemporaryDirectory() as work:
            seen = {}

            def make(*inputs, output, other=None):
                seen[Path(output).name] = inputs
                return Path(output).name

            graph = Graph(Path(work), lambda *a, **k: None)
            a = graph.add("a", make)
            b = graph.add("b", make, a)
            c = graph.add("c", make, [a, b], other=None)
            graph.run()
            self.assertEqual(seen["b"], (str(Path(work) / "a"),))
            self.assertEqual(seen["c"], ([str(Path(work) / "a"), str(Path(work) / "b")],))
            self.assertEqual(c.result, "c")

    def test_a_failure_stops_what_needs_it(self):
        with tempfile.TemporaryDirectory() as work:
            ran = []

            def fail(output):
                raise ValueError("broken")

            graph = Graph(Path(work), lambda *a, **k: None)
            a = graph.add("a", fail)
            graph.add("b", lambda x, output: ran.append("b"), a)
            with self.assertRaises(ValueError):
                graph.run()
            self.assertEqual(ran, [])


class SharingTest(unittest.TestCase):
    def test_jobs_sharing_a_file_run_in_one_group(self):
        with tempfile.TemporaryDirectory() as folder:
            files = [Path(folder) / f"{n}.dat" for n in "xyz"]
            for f in files:
                f.write_bytes(b"")
            x, y, z = (str(f) for f in files)
            jobs = [(None, "a", None, {"in": [x]}, None), (None, "b", None, {"in": y}, None),
                    (None, "c", None, {"in": {"one": y, "two": z}}, None), (None, "d", None, {"in": "none"}, None)]
            groups = sorted(sorted(j[1] for j in g) for g in sharing(jobs))
            self.assertEqual(groups, [["a"], ["b", "c"], ["d"]])


if __name__ == "__main__":
    unittest.main()
