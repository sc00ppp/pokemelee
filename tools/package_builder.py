"""Maintainer: assemble the user-facing PokéMelee Builder folder (and optionally its zip).

python tools/package_builder.py --runtime <installed runtime> --out <new folder> [--zip]

Layout:
  PokeMeleeBuilder.exe        the drag-and-drop window (launcher/, self-contained .NET 8)
  engine/python               embedded Python 3.13 + numpy, scipy, Pillow, PyYAML
  engine/app/pokemelee        this package, with the local model patches
  engine/dotnet               the .NET 8 runtime the stage helpers (stagegraft dlls) run on
  engine/runtime              the pinned user-build tools (maintainer-only tools left out)
  README.txt, LICENSES/

Nothing is downloaded: the embedded Python comes from the pinned geometry-python runtime, the libraries from the
running interpreter (their versions must match pyproject.toml), .NET from the local install and NuGet cache.
"""
import argparse
import importlib.metadata as metadata
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pokemelee.runtime import lock  # noqa: E402

LIBRARIES = {"numpy": "2.2.6", "scipy": "1.16.0", "pillow": "11.2.1", "PyYAML": None}
README = """PokéMelee Builder
================

Makes PokéMelee from your own discs. You need:
  * Super Smash Bros. Melee, USA, version 1.02, as a full-size .iso (1.36 GB)
  * Pokémon Colosseum, USA, as a full-size .iso (1.36 GB)
  * Windows 10 or 11 (64-bit), about 20 GB of free disk space while it runs, and a graphics card
    with OpenGL (the portraits and stage pictures are rendered on it)

How to use it:
  1. Extract this whole folder somewhere you can write to (not Program Files).
  2. Run PokeMeleeBuilder.exe and drop both ISOs on the window (or drop them on the exe).
  3. Press Build. It takes about 10 minutes.

You get, in the folder you chose (next to your Melee ISO by default):
  PokeMelee.iso                 PokeMelee.xdelta
  PokeMelee AniMelee.iso        PokeMelee AniMelee.xdelta
The .xdelta files are patches against your original Melee ISO.

Compressed or trimmed images (.rvz, .ciso, .gcz, .nkit.iso) don't work; convert them back to a full .iso
first (Dolphin: right-click the game > Convert File > ISO).

If something goes wrong, the full log is "PokeMelee build log.txt" in the output folder.
"""


def copy_tree(source, target, ignore=None):
    shutil.copytree(source, target, ignore=ignore or shutil.ignore_patterns("__pycache__", "*.pyc"))


def runtime_tools(runtime, engine):
    """The pinned tools a user build needs, as fetched (receipts included), plus the compiled helpers."""
    target = engine / "runtime"
    for name, tool in lock()["tools"].items():
        if tool.get("maintainer") or "win-x64" not in tool["platforms"]:
            continue
        copy_tree(runtime / name / "win-x64", target / name / "win-x64")
    copy_tree(runtime / "stagegraft", target / "stagegraft")
    copy_tree(runtime / "audio", target / "audio")


def python_runtime(runtime, engine, embed=None):
    source = Path(embed or runtime / "geometry-python/win-x64")
    target = engine / "python"
    target.mkdir(parents=True)
    keep = re.compile(r"^(python\.exe|pythonw\.exe|python3\.dll|python3\d+\.(dll|zip)|.*\.pyd|.*\.dll|LICENSE\.txt)$", re.I)
    for item in source.iterdir():
        if item.is_file() and keep.match(item.name):
            shutil.copy2(item, target / item.name)
    zips = list(target.glob("python3*.zip"))
    if len(zips) != 1:
        raise SystemExit("The embedded Python runtime is incomplete: " + str(source))
    version = zips[0].stem
    (target / (version + "._pth")).write_text(f"{version}.zip\n.\nLib\\site-packages\n..\\app\nimport site\n",
                                              encoding="utf-8")
    site = target / "Lib/site-packages"
    site.mkdir(parents=True)
    for name, pinned in LIBRARIES.items():
        dist = metadata.distribution(name)
        if pinned and dist.version != pinned:
            raise SystemExit(f"{name} {dist.version} is installed; the build is pinned to {pinned}")
        base = Path(dist.locate_file(""))
        for entry in dist.files:
            parts = PurePath(str(entry)).parts
            if parts[0] == ".." or "__pycache__" in parts or str(entry).endswith((".pyc", ".whl")):
                continue
            source_file = base / entry
            if source_file.is_file():
                (site / entry).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, site / entry)


def app_package(engine):
    copy_tree(ROOT / "pokemelee", engine / "app/pokemelee")
    patches = sorted((engine / "app/pokemelee/recipes/model-patches").glob("*.mpatch"))
    finishing = json.loads((ROOT / "pokemelee/recipes/cast-finishing.json").read_text(encoding="utf-8"))["recipes"]
    if sorted(p.stem for p in patches) != sorted(finishing):
        raise SystemExit("Write the model patches first (python -m pokemelee model-patches ...)")


def dotnet_runtime(engine):
    """dotnet.exe, its newest host resolver and the newest installed .NET 8 runtime: enough for `dotnet x.dll`."""
    listing = subprocess.run(["dotnet", "--list-runtimes"], capture_output=True, text=True, check=True).stdout
    rows = re.findall(r"Microsoft\.NETCore\.App (8\.0\.\d+) \[(.+?)\]", listing)
    if not rows:
        raise SystemExit("Install the .NET 8 runtime on this machine first")
    version, shared = max(rows, key=lambda r: tuple(map(int, r[0].split("."))))
    root = Path(shared).parents[1]
    target = engine / "dotnet"
    target.mkdir(parents=True)
    for name in ("dotnet.exe", "LICENSE.txt", "ThirdPartyNotices.txt"):
        if (root / name).exists():
            shutil.copy2(root / name, target / name)
    fxr = max((root / "host/fxr").iterdir(), key=lambda p: tuple(map(int, p.name.split("."))))
    copy_tree(fxr, target / "host/fxr" / fxr.name)
    copy_tree(root / "shared/Microsoft.NETCore.App" / version, target / "shared/Microsoft.NETCore.App" / version)
    return version


def launcher(out, runtime_version):
    build = out.parent / (out.name + "-launcher")
    shutil.rmtree(build, ignore_errors=True)
    packages = Path(os.environ.get("NUGET_PACKAGES", Path.home() / ".nuget/packages"))
    subprocess.run(["dotnet", "publish", str(ROOT / "launcher/PokeMeleeBuilder.csproj"), "-c", "Release", "-o", str(build),
                    "--source", str(packages), f"-p:RuntimeFrameworkVersion={runtime_version}"], check=True)
    shutil.copy2(build / "PokeMeleeBuilder.exe", out / "PokeMeleeBuilder.exe")
    shutil.rmtree(build, ignore_errors=True)


def licenses(out, engine):
    folder = out / "LICENSES"
    folder.mkdir()
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", folder / "THIRD_PARTY_NOTICES.md")
    found = [(p.parts[-3], p) for p in engine.joinpath("runtime").glob("*/win-x64/*")]
    found += [("dotnet", p) for p in engine.joinpath("dotnet").glob("*.txt")] + [("python", engine / "python/LICENSE.txt")]
    for tool, path in found:
        if path.is_file() and re.match(r"(license|copying|notice|thirdpartynotices)", path.name, re.I):
            shutil.copy2(path, folder / f"{tool}-{path.name}")


def smoke_test(engine):
    python = engine / "python/python.exe"
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["PATH"] = str(engine / "dotnet") + os.pathsep + env.get("PATH", "")
    env["DOTNET_ROOT"] = str(engine / "dotnet")
    check = ("import numpy, scipy.ndimage, PIL.Image, yaml, lzma, pokemelee.builder as b; "
             "b.preflight(r'%s'); print('engine ok', numpy.__version__)" % (engine / "runtime"))
    subprocess.run([str(python), "-c", check], cwd=engine, env=env, check=True)
    dll = next((engine / "runtime/stagegraft").glob("*/stagegraft-*.dll"))
    result = subprocess.run([str(engine / "dotnet/dotnet.exe"), "--list-runtimes"], env=env, capture_output=True, text=True)
    print("bundled .NET:", result.stdout.strip(), "| helper", dll.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime", required=True, help="An installed runtime folder (fetch-tools + compile steps)")
    parser.add_argument("--out", required=True, help="A new folder for the builder")
    parser.add_argument("--python-embed", help="Embedded Python folder (default: <runtime>/geometry-python/win-x64)")
    parser.add_argument("--launcher-runtime", default="8.0.22", help="Cached .NET 8 runtime pack for the launcher")
    parser.add_argument("--zip", action="store_true", help="Also write <out>.zip")
    args = parser.parse_args()
    runtime, out = Path(args.runtime).resolve(), Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"{out} already exists; choose a new folder")
    engine = out / "engine"
    engine.mkdir(parents=True)
    print("tools"); runtime_tools(runtime, engine)
    print("python"); python_runtime(runtime, engine, args.python_embed)
    print("package"); app_package(engine)
    print(".NET"); dotnet_runtime(engine)
    print("launcher"); launcher(out, args.launcher_runtime)
    (out / "README.txt").write_text(README, encoding="utf-8")
    licenses(out, engine)
    smoke_test(engine)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"builder folder: {out} ({size / 2**20:.0f} MB)")
    if args.zip:
        archive = shutil.make_archive(str(out), "zip", out.parent, out.name)
        print(f"zip: {archive} ({Path(archive).stat().st_size / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()
