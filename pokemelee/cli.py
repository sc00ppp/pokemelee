"""Source-only builder tools. Incomplete ISO builds fail before writing output."""
import argparse
import json
import subprocess
import sys
import zipfile

from .catalog import art_indices, plan
from .disc import Disc


def parser():
    root = argparse.ArgumentParser(prog="pokemelee", description="PokéMelee build tooling for your own two game discs")
    sub = root.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Check supported disc versions and filesystem structure")
    for name in ("melee", "colosseum"):
        check.add_argument("--" + name, required=True)
    check.add_argument("--hash", action="store_true", help="Also compute full disc SHA-256 hashes")
    ls = sub.add_parser("list", help="List a supported disc's files")
    ex = sub.add_parser("extract", help="Extract named disc files into a new local directory")
    for cmd in (ls, ex):
        cmd.add_argument("--game", choices=("melee", "colosseum"), required=True)
        cmd.add_argument("--iso", required=True)
    ex.add_argument("--file", action="append", required=True, dest="files")
    ex.add_argument("--out", required=True)
    ex.add_argument("--unpack-fsys", action="store_true")
    art = sub.add_parser("menu-art", help="Generate stock icons and fallback party-face CSS icons from Colosseum")
    art.add_argument("--colosseum", required=True)
    art.add_argument("--out", required=True)
    art.add_argument("--index", action="append", help="Internal species art index; default: full cast")
    sub.add_parser("plan", help="Show the accepted cast, stages, and unresolved build steps")
    sub.add_parser("tools", help="Show exact native runtime pins")
    fetch = sub.add_parser("fetch-tools", help="Download pinned releases directly from the fork repositories")
    fetch.add_argument("--tool", choices=("hsdlib", "mex", "xdelta", "all"), default="all")
    fetch.add_argument("--platform", choices=("win-x64", "linux-x64", "osx-arm64"), default="win-x64")
    fetch.add_argument("--out", default="runtime")
    fetch.add_argument("--github-auth", action="store_true", help="Maintainer access to private releases through gh")
    runtime = sub.add_parser("runtime-install", help="Verify and install a maintainer-supplied runtime ZIP")
    runtime.add_argument("name", choices=("hsdlib", "mex", "xdelta"))
    runtime.add_argument("archive")
    runtime.add_argument("--platform", choices=("win-x64", "linux-x64", "osx-arm64"), required=True)
    runtime.add_argument("--out", required=True)
    package = sub.add_parser("package", help="Export a built ISO and verified xdelta together, locally")
    package.add_argument("--melee", required=True, help="Original base Melee ISO for the patch")
    package.add_argument("--built-iso", required=True, help="An already assembled PokéMelee ISO")
    package.add_argument("--out", required=True, help="A new local output directory")
    package.add_argument("--xdelta", help="xdelta3 executable; default: fetched Windows tool or xdelta3 on PATH")
    build = sub.add_parser("build", help="Build-readiness gate (ISO assembly is not yet portable)")
    build.add_argument("--melee", required=True)
    build.add_argument("--colosseum", required=True)
    build.add_argument("--out", required=True)
    return root


def run(args):
    if args.command == "plan":
        return plan()
    if args.command == "tools":
        from .runtime import lock
        return lock()
    if args.command == "fetch-tools":
        from pathlib import Path
        from .runtime import fetch, lock
        names = tuple(name for name, tool in lock()["tools"].items() if args.platform in tool["platforms"]) if args.tool == "all" else (args.tool,)
        results = {}
        for name in names:
            target = Path(args.out) / name / args.platform
            result = fetch(name, args.platform, target, github_auth=args.github_auth)
            results[name] = {"path": str(target.resolve()), "files": len(result["outputs"]), "sha256": result["inputs"]["sha256"]}
        return results
    if args.command == "package":
        from .export import export_artifacts
        return export_artifacts(args.melee, args.built_iso, args.out, xdelta=args.xdelta)
    if args.command == "runtime-install":
        from .runtime import install
        return install(args.name, args.platform, args.archive, args.out)
    if args.command in ("check", "build"):
        discs = {name: Disc(getattr(args, name), name) for name in ("melee", "colosseum")}
        if args.command == "build":
            pending = plan()["blocking_steps"]
            raise ValueError("Two-ISO build is not ready. No output written. Remaining: " + ", ".join(pending))
        return {name: disc.info(args.hash) for name, disc in discs.items()}
    if args.command == "menu-art":
        try:
            from .art import generate
        except ImportError as exc:
            raise ValueError('Menu art needs the art extra: python -m pip install ".[art]"') from exc
        return generate(Disc(args.colosseum, "colosseum"), args.out, args.index or art_indices())
    disc = Disc(args.iso, args.game)
    if args.command == "list":
        return {name: {"bytes": row.size} for name, row in disc.entries.items()}
    from .extract import extract
    return extract(disc, args.out, args.files, unpack=args.unpack_fsys)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(f"pokemelee: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0
