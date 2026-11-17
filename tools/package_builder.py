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

The finished folder is checked before it is zipped: it must not contain the maintainer's user-profile path or build
folders, a .pdb, an .obj, a __pycache__ or a reference to a private repository (see forbidden_content).
"""
import argparse
import importlib.metadata as metadata
import io
import json
import lzma
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path, PurePath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pokemelee.runtime import lock  # noqa: E402

LIBRARIES = {"numpy": "2.2.6", "scipy": "1.16.0", "pillow": "11.2.1", "PyYAML": None}
# Never shipped: compiler and interpreter by-products (pdbs and objs name the folders they were built in)
SKIP = ("__pycache__", "*.pyc", "*.pdb", "*.obj")
# GitHub accounts whose repositories are private (every repository of the maintainer's account is): no shipped file may
# name one. Every reference to such a repository (owner/name, a github.com URL, a zipball folder) carries the account.
PRIVATE_ACCOUNTS = ("sc00ppp",)
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
    shutil.copytree(source, target, ignore=ignore or shutil.ignore_patterns(*SKIP))


def private(value):
    return isinstance(value, str) and any(a.lower() in value.lower() for a in PRIVATE_ACCOUNTS)


def scrub(value):
    """A JSON value without the fields that name a private repository."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if not private(v)}
    if isinstance(value, list):
        return [scrub(v) for v in value if not private(v)]
    return value


def user_lockfile(pinned):
    """The lockfile a user build reads: the bundled tools only (maintainer tools, the maintainer geometry setup and
    to-do notes left out), without fields that name private repositories. Preflight needs each tool's pinned sha256,
    its required files and entrypoint, which all stay."""
    tools = {name: scrub(tool) for name, tool in pinned["tools"].items() if not tool.get("maintainer")}
    return {"schema": pinned["schema"],
            "distribution": "The tools bundled with this builder, as pinned for it. Maintainers fetch and refresh them "
                            "with the repository's own lockfile.",
            "tools": tools}


def runtime_tools(runtime, engine):
    """The pinned tools a user build needs, as fetched (receipts included, without private repository names), plus the
    compiled helpers."""
    target = engine / "runtime"
    for name, tool in lock()["tools"].items():
        if tool.get("maintainer") or "win-x64" not in tool["platforms"]:
            continue
        copy_tree(runtime / name / "win-x64", target / name / "win-x64")
        record = target / name / "win-x64/receipt.json"
        if record.is_file():
            record.write_text(json.dumps(scrub(json.loads(record.read_text(encoding="utf-8"))), indent=2) + "\n",
                              encoding="utf-8")
    copy_tree(runtime / "stagegraft", target / "stagegraft")
    copy_tree(runtime / "audio", target / "audio", shutil.ignore_patterns(*SKIP, "*.log"))   # compile logs stay home


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
            if parts[0] == ".." or "__pycache__" in parts or str(entry).lower().endswith((".pyc", ".whl", ".pdb", ".obj")):
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
    shipped = engine / "app/pokemelee/dependencies.lock.json"
    shipped.write_text(json.dumps(user_lockfile(lock()), indent=2) + "\n", encoding="utf-8")


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
    """LICENSES/: the notices, the licence texts collected in third_party_licenses/ (each from its component's own
    distribution) and the ones that come inside the bundled runtimes. Every [file] the notices name must be there."""
    folder = out / "LICENSES"
    folder.mkdir()
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", folder / "THIRD_PARTY_NOTICES.md")
    for text in sorted((ROOT / "third_party_licenses").iterdir()):
        shutil.copy2(text, folder / text.name)
    found = [(p.parts[-3], p) for p in engine.joinpath("runtime").glob("*/win-x64/*")]
    found += [(p.parts[-4], p) for p in engine.joinpath("runtime").glob("*/win-x64/*/LICENSE")]       # musyx source tree
    found += [("dotnet", p) for p in engine.joinpath("dotnet").glob("*.txt")] + [("python", engine / "python/LICENSE.txt")]
    site = engine / "python/Lib/site-packages"
    for name in LIBRARIES:
        dist = next(site.glob(f"{name.lower()}-*.dist-info"))
        found += [(name.lower(), p) for p in dist.rglob("*") if p.is_file()]
    for tool, path in found:
        if path.is_file() and re.match(r"(license|copying|notice|thirdpartynotices)", path.name, re.I):
            shutil.copy2(path, folder / f"{tool}-{path.name}")
    named = {n.strip() for group in re.findall(r"\[([^\]]+)\]", (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"))
             for n in group.split(",") if re.fullmatch(r"\s*[\w.-]+\.(txt|md)\s*|\s*[\w-]+-LICENSE\s*", n)}
    missing = sorted(n for n in named if not (folder / n).is_file())
    if missing:
        raise SystemExit("THIRD_PARTY_NOTICES.md names licence files that are not in LICENSES/: " + ", ".join(missing))


def smoke_test(engine):
    python = engine / "python/python.exe"
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"                 # the check must not leave __pycache__ in the package
    env["PATH"] = str(engine / "dotnet") + os.pathsep + env.get("PATH", "")
    env["DOTNET_ROOT"] = str(engine / "dotnet")
    check = ("import numpy, scipy.ndimage, PIL.Image, yaml, lzma, pokemelee.builder as b; "
             "b.preflight(r'%s'); print('engine ok', numpy.__version__)" % (engine / "runtime"))
    subprocess.run([str(python), "-B", "-c", check], cwd=engine, env=env, check=True)
    dll = next((engine / "runtime/stagegraft").glob("*/stagegraft-*.dll"))
    result = subprocess.run([str(engine / "dotnet/dotnet.exe"), "--list-runtimes"], env=env, capture_output=True, text=True)
    print("bundled .NET:", result.stdout.strip(), "| helper", dll.name)


def bundle_members(data):
    """(path, bytes) of every file inside a .NET single-file apphost (bundle manifest v2+; compressed members inflated)."""
    signature = bytes.fromhex("8b1202b96a612038727b930214d7a03213f5b9e6efae3318ee3b2dce24b36aae")
    at = data.find(signature)
    if at < 8:
        return []
    pos = struct.unpack_from("<q", data, at - 8)[0]
    if not 0 < pos < len(data):                  # a plain apphost carries the signature with no bundle behind it
        return []
    major, _, count = struct.unpack_from("<IIi", data, pos)
    pos += 12

    def string(p):
        n, shift = 0, 0
        while True:
            b = data[p]
            p, n, shift = p + 1, n | (b & 0x7F) << shift, shift + 7
            if b < 0x80:
                return data[p:p + n].decode("utf-8"), p + n
    _, pos = string(pos)
    pos += 40 if major >= 2 else 0
    members = []
    for _ in range(count):
        offset, size = struct.unpack_from("<qq", data, pos)
        pos += 16
        packed = 0
        if major >= 6:
            packed = struct.unpack_from("<q", data, pos)[0]
            pos += 8
        path, pos = string(pos + 1)
        raw = data[offset:offset + (packed or size)]
        members.append((path, zlib.decompress(raw, -15) if packed else raw))
    return members


def contents(path, data):
    """(where, bytes) for a file and for what it holds compressed: zip members, a model patch's lzma body, the
    members of a single-file .NET apphost."""
    yield path, data
    if data[:4] == b"PK\x03\x04" and zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for item in z.infolist():
                if not item.is_dir():
                    yield f"{path}!{item.filename}", z.read(item)
    if data.startswith(b"PMMP1\n"):
        n = struct.unpack_from("<I", data, 6)[0]
        yield f"{path}!body", lzma.decompress(data[10 + n:])
    if data[:2] == b"MZ" and path.lower().endswith(".exe"):
        for name, member in bundle_members(data):
            yield f"{path}!{name}", member


def forbidden_strings(*folders, home=None):
    """What must not appear in a shipped file: the user-profile path (and its \\Users\\<name> part, whatever the
    drive), the given build folders and the top-level folder each sits in, and the private accounts."""
    home = Path(home or Path.home())
    found = [("user profile", str(home)), ("user profile", "\\users\\" + home.name)]
    for folder in folders:
        # The builder is made on Windows and its binaries embed Windows paths, so a path with a drive letter is read
        # as one whatever machine asks (elsewhere Path would take "E:/x" for a relative name and resolve it away).
        windows = PureWindowsPath(str(folder))
        folder = Path(folder).resolve() if os.name == "nt" or not windows.drive else windows
        found.append(("build folder", str(folder)))
        if len(folder.parts) > 1 and folder.parts[1].lower() != "users":
            found.append(("build folder", str(type(folder)(folder.anchor) / folder.parts[1])))
    found += [("private repository", account) for account in PRIVATE_ACCOUNTS]
    variants = []
    for kind, text in found:
        for form in {text, text.replace("\\", "/"), text.replace("\\", "\\\\")}:
            variants.append((kind, form.lower()))
    return sorted(set(variants))


def forbidden_content(folder, strings):
    """Every reason the finished folder may not ship, as (path, what): a __pycache__, a .pdb, an .obj, or one of
    `strings` (kind, lower-case text) in any file, as ASCII/UTF-8 or UTF-16, including what files hold compressed."""
    folder = Path(folder)
    needles = [(kind, s.encode("utf-8"), s.encode("utf-16-le")) for kind, s in strings]
    problems = []
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        if path.is_dir():
            if path.name == "__pycache__":
                problems.append((rel, "__pycache__ folder"))
            continue
        if path.suffix.lower() in (".pdb", ".obj", ".pyc"):
            problems.append((rel, path.suffix.lower() + " file"))
        for where, data in contents(rel, path.read_bytes()):
            low = data.lower()
            for kind, ascii_form, wide_form in needles:
                if ascii_form in low or wide_form in low:
                    problems.append((where, f"{kind}: {ascii_form.decode()}"))
    return problems


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
    problems = forbidden_content(out, forbidden_strings(ROOT, runtime, out.parent))
    for where, what in problems:
        print(f"  NOT CLEAN {where}: {what}")
    if problems:
        raise SystemExit(f"{len(problems)} problem(s): the folder must not ship as it is")
    print("clean: no user-profile path, build folder, pdb, obj, __pycache__ or private repository")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"builder folder: {out} ({size / 2**20:.0f} MB)")
    if args.zip:
        archive = shutil.make_archive(str(out), "zip", out.parent, out.name)
        print(f"zip: {archive} ({Path(archive).stat().st_size / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()
