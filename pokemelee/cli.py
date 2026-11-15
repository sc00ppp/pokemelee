"""Source-only builder tools. Incomplete ISO builds fail before writing output."""
import argparse
import json
import subprocess
import sys
import zipfile

from .catalog import art_indices, plan
from .disc import Disc


def parser():
    from .runtime import lock
    tool_names = tuple(lock()["tools"])
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
    native = sub.add_parser("compile-stages", help="Compile the authored stage helpers against the pinned HSDRaw runtime")
    native.add_argument("--runtime", default="runtime")
    stages = sub.add_parser("stages", help="Rebuild the approved stages directly from the two source discs")
    stages.add_argument("--melee", required=True)
    stages.add_argument("--colosseum", required=True)
    stages.add_argument("--out", required=True)
    stages.add_argument("--runtime", default="runtime")
    stages.add_argument("--profile", choices=("normal", "animelee"), default="normal")
    stages.add_argument("--stage", action="append", dest="selected")
    voices = sub.add_parser("voices", help="Rebuild approved fighter voices or announcer calls from the source discs")
    voices.add_argument("--melee", required=True)
    voices.add_argument("--colosseum", required=True)
    voices.add_argument("--out", required=True)
    voices.add_argument("--runtime", default="runtime")
    voices.add_argument("--announcer", action="store_true")
    voices.add_argument("--bank", action="append")
    audio_tools = sub.add_parser("compile-audio", help="Compile the authored music/effect drivers against pinned MusyX")
    audio_tools.add_argument("--runtime", default="runtime")
    music = sub.add_parser("music", help="Rebuild the seven approved tracks from Colosseum")
    menu_sounds = sub.add_parser("menu-sounds", help="Rebuild the accepted menu sound bank")
    models = sub.add_parser("source-models", help="Convert the original cast models without changing their rigs")
    for command in (music, menu_sounds, models):
        command.add_argument("--colosseum", required=True)
        command.add_argument("--out", required=True)
        command.add_argument("--runtime", default="runtime")
    menu_sounds.add_argument("--melee", required=True)
    music.add_argument("--song", action="append")
    models.add_argument("--pokemon", action="append")
    models.add_argument("--blender", help="Explicit pinned converter executable")
    models.add_argument("--reader", help="Explicit pinned model-reader directory")
    fetch = sub.add_parser("fetch-tools", help="Download pinned releases directly from the fork repositories")
    fetch.add_argument("--tool", choices=(*tool_names, "all"), default="all")
    fetch.add_argument("--platform", choices=("win-x64", "linux-x64", "osx-arm64"), default="win-x64")
    fetch.add_argument("--out", default="runtime")
    fetch.add_argument("--github-auth", action="store_true", help="Maintainer access to private releases through gh")
    runtime = sub.add_parser("runtime-install", help="Verify and install a maintainer-supplied runtime ZIP")
    runtime.add_argument("name", choices=tool_names)
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
    if args.command == "compile-audio":
        from .audio_tools import compile_audio
        compile_audio(args.runtime)
        return {"compiled": True}
    if args.command == "source-models":
        from .models import convert_models
        return convert_models(Disc(args.colosseum, "colosseum"), args.out, args.runtime, args.pokemon,
                               blender=args.blender, reader=args.reader)
    if args.command == "music":
        from .music import build_music
        return build_music(Disc(args.colosseum, "colosseum"), args.out, args.runtime, args.song)
    if args.command == "menu-sounds":
        from .menu_sounds import build_menu_sounds
        return build_menu_sounds(Disc(args.melee, "melee"), Disc(args.colosseum, "colosseum"), args.out, args.runtime)
    if args.command == "voices":
        from .voices import build_voices, build_announcer
        if args.announcer and args.bank:
            raise ValueError("--bank cannot be combined with --announcer")
        discs = [Disc(args.melee, "melee"), Disc(args.colosseum, "colosseum")]
        if args.announcer:
            return build_announcer(*discs, args.out, args.runtime)
        return build_voices(*discs, args.out, args.runtime, args.bank)
    if args.command == "compile-stages":
        from .stages import compile_tools
        compile_tools(args.runtime)
        return {"compiled": True}
    if args.command == "stages":
        try:
            import numpy, PIL, scipy
        except ImportError as exc:
            raise ValueError('Stage generation needs: python -m pip install ".[stages]"') from exc
        from .stages import build_stages
        return build_stages(Disc(args.melee, "melee"), Disc(args.colosseum, "colosseum"),
                            args.out, args.runtime, args.selected, args.profile)
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
