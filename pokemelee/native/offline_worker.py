"""Run a fixed local converter with inference imports and network disabled."""
import importlib.abc
from pathlib import Path
import runpy
import sys


class NoAuthoring(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        roots = ("rigswap.ai", "rigswap.core.run", "rigswap.pipeline")
        if any(fullname == name or fullname.startswith(name + ".") for name in roots):
            raise ImportError("Authoring is disabled in the PokéMelee builder: " + fullname)


def no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
        raise RuntimeError("Network access is disabled in the PokéMelee converter")


def main():
    # argv: -c, builder root, pinned helper root, script, script arguments
    sys.path[:0] = [sys.argv[1], sys.argv[2], str(Path(sys.argv[3]).parent)]
    sys.meta_path.insert(0, NoAuthoring())
    sys.addaudithook(no_network)
    sys.argv = sys.argv[3:]
    runpy.run_path(sys.argv[0], run_name="__main__")
