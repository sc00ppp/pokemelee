"""Source-only builder and component tools for the user's two original discs."""
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
    geometry = sub.add_parser("setup-geometry", help="Install the pinned offline character converter")
    geometry.add_argument("--runtime", default="runtime")
    geometry.add_argument("--github-auth", action="store_true")
    targets = sub.add_parser("melee-targets", help="Generate the accepted cast's Melee targets from the original disc")
    targets.add_argument("--melee", required=True)
    targets.add_argument("--out", required=True)
    targets.add_argument("--runtime", default="runtime")
    targets.add_argument("--hsd")
    targets.add_argument("--blender")
    cast = sub.add_parser("cast", help="Replay the verified character recipes from regenerated disc components")
    for name in ("colosseum", "models", "targets", "out"):
        cast.add_argument("--" + name, required=True)
    cast.add_argument("--runtime", default="runtime")
    cast.add_argument("--pokemon", action="append")
    cast.add_argument("--hsd")
    cast.add_argument("--blender")
    cast.add_argument("--jobs", type=int, default=2)
    icons = sub.add_parser("css-icons", help="Render the accepted character-select tiles from generated components")
    for name in ("models", "cast", "out"):
        icons.add_argument("--" + name, required=True)
    icons.add_argument("--runtime", default="runtime")
    icons.add_argument("--profile", choices=("normal", "animelee"), action="append")
    icons.add_argument("--blender")
    portraits = sub.add_parser("portraits", help="Render the accepted costume portraits from generated components")
    for name in ("cast", "targets", "out"):
        portraits.add_argument("--" + name, required=True)
    portraits.add_argument("--runtime", default="runtime")
    portraits.add_argument("--pokemon", action="append")
    color_portraits = sub.add_parser("color-portraits", help="Render the accepted alternate costume portraits")
    for name in ("colosseum", "colors", "cast", "targets", "portraits", "out"):
        color_portraits.add_argument("--" + name, required=True)
    color_portraits.add_argument("--runtime", default="runtime")
    color_portraits.add_argument("--pokemon", action="append")
    colors = sub.add_parser("colors", help="Rebuild the accepted shiny and designed team costumes")
    for name in ("colosseum", "cast", "out"):
        colors.add_argument("--" + name, required=True)
    colors.add_argument("--pokemon", action="append")
    menu_sources = sub.add_parser("menu-sources", help="Decode the accepted menu logo, backdrop and panel from Colosseum")
    menu_sources.add_argument("--colosseum", required=True)
    menu_sources.add_argument("--out", required=True)
    menu_sources.add_argument("--runtime", default="runtime")
    menus = sub.add_parser("menus", help="Rebuild the accepted menus from original discs and generated menu sources")
    for name in ("melee", "sources", "out"):
        menus.add_argument("--" + name, required=True)
    menus.add_argument("--runtime", default="runtime")
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
    build = sub.add_parser("build", help="Replay the two-disc build and create local ISO/xdelta outputs")
    build.add_argument("--melee", required=True)
    build.add_argument("--colosseum", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--runtime", default="runtime")
    build.add_argument("--jobs", type=int, default=2)
    build.add_argument("--profile", choices=("normal", "animelee"), action="append")
    return root


def run(args):
    if args.command == "color-portraits":
        from .portraits import build_color_portraits
        return build_color_portraits(Disc(args.colosseum, "colosseum"), args.colors, args.cast, args.targets,
                                     args.portraits, args.out, args.runtime, args.pokemon)
    if args.command == "portraits":
        from .portraits import build_portraits
        return build_portraits(args.cast, args.targets, args.out, args.runtime, args.pokemon)
    if args.command == "colors":
        from .colors import build_colors
        return build_colors(Disc(args.colosseum, "colosseum"), args.cast, args.out, args.pokemon)
    if args.command == "menu-sources":
        from .menu_sources import generate_menu_sources
        return generate_menu_sources(Disc(args.colosseum, "colosseum"), args.out, args.runtime)
    if args.command == "menus":
        from .menus import build_menus
        return build_menus(Disc(args.melee, "melee"), args.sources, args.out, args.runtime)
    if args.command == "css-icons":
        from .icons import generate_icons
        return generate_icons(args.models, args.cast, args.out, args.runtime,
                              args.profile or ("normal", "animelee"), blender=args.blender)
    if args.command == "cast":
        from .cast import build_cast
        return build_cast(Disc(args.colosseum, "colosseum"), args.models, args.targets, args.out, args.runtime,
                          args.pokemon, hsd=args.hsd, blender=args.blender, jobs=args.jobs)
    if args.command == "setup-geometry":
        from .geometry import setup_geometry
        return setup_geometry(args.runtime, github_auth=args.github_auth)
    if args.command == "melee-targets":
        from .targets import prepare_targets
        return prepare_targets(Disc(args.melee, "melee"), args.out, args.runtime, hsd=args.hsd, blender=args.blender)
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
        if args.tool == "all" and args.platform == "win-x64":
            from .geometry import configure_geometry
            configure_geometry(args.out)
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
            from .builder import build_all
            return build_all(discs['melee'], discs['colosseum'], args.out, args.runtime,
                             args.profile or ('normal', 'animelee'), args.jobs)
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
