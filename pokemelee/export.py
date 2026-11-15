"""Local ISO + xdelta export. Publish the pair only after a verified round trip."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .disc import Disc
from .runtime import lock
from .workspace import output_directory, receipt


def fingerprint(path):
    path = Path(path)
    with path.open("rb") as stream:
        return {"bytes": path.stat().st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}


def find_xdelta(supplied=None):
    if supplied:
        value = str(supplied)
        path = Path(value).expanduser()
        if path.is_file():
            return path.resolve()
        found = shutil.which(value)
    else:
        spec = lock()["tools"]["xdelta"]["platforms"]["win-x64"]
        bundled = Path("runtime/xdelta/win-x64") / spec["entrypoint"]
        if os.name == "nt" and bundled.is_file():
            return bundled.resolve()
        found = shutil.which("xdelta3")
    if not found:
        raise ValueError("xdelta3 was not found; fetch the Windows xdelta tool or supply --xdelta PATH")
    return Path(found).resolve()


def _run(executable, args):
    env = os.environ.copy()
    # xdelta reads extra arguments from XDELTA; do not let ambient settings
    # disable checksums or override the explicit base/output files.
    env.pop("XDELTA", None)
    result = subprocess.run([str(executable), *map(str, args)], env=env,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            errors="replace", timeout=3600)
    if result.returncode:
        raise ValueError(f"xdelta3 failed ({result.returncode}): {(result.stderr or result.stdout).strip()[-2000:]}")
    return (result.stdout + result.stderr).strip()


def export_artifacts(melee, built_iso, output, *, xdelta=None):
    """Use after assembly, or to package an existing local build. No upload."""
    base = Disc(melee, "melee")
    built = Path(built_iso).expanduser().resolve(strict=True)
    if os.path.samefile(base.path, built):
        raise ValueError("The built ISO must be different from the original Melee ISO")
    with built.open("rb") as stream:
        header = stream.read(0x440)
    if len(header) != 0x440 or header[0x1C:0x20] != bytes.fromhex("c2339f3d"):
        raise ValueError("The built file must be an uncompressed GameCube ISO")
    out = Path(output).expanduser().absolute()
    if out.exists() or out.is_symlink():
        raise ValueError(f"Output already exists; choose a new directory: {out}")
    tool = find_xdelta(xdelta)
    version = _run(tool, ["-V"]).splitlines()[0]
    parent = out.parent
    while not parent.exists():
        parent = parent.parent
    # Temporary copy, patch (worst case approximately target size), decode.
    if shutil.disk_usage(parent).free < built.stat().st_size * 3.2 + 64 * 1024**2:
        raise ValueError("Not enough free disk space for the ISO, patch and verification copy")
    base_hash, built_hash = fingerprint(base.path), fingerprint(built)
    if base_hash == built_hash:
        raise ValueError("The built ISO is identical to the base Melee ISO")
    with output_directory(out, "package") as root:
        with tempfile.TemporaryDirectory(prefix=".package-", dir=root) as temp:
            temp = Path(temp)
            iso, delta, decoded = temp / "pokemelee.iso", temp / "pokemelee.xdelta", temp / "verify.iso"
            shutil.copyfile(built, iso)
            if fingerprint(iso) != built_hash:
                raise ValueError("Built ISO changed while copying")
            # Standard VCDIFF without secondary compression works with older
            # patchers too. Omit application headers containing local filenames.
            _run(tool, ["-e", "-9", "-S", "none", "-A=", "-D", "-s", base.path, iso, delta])
            _run(tool, ["-d", "-D", "-R", "-s", base.path, delta, decoded])
            if fingerprint(decoded) != built_hash:
                raise ValueError("Patch verification failed: decoded ISO does not match the built ISO")
            if fingerprint(base.path) != base_hash:
                raise ValueError("Base Melee ISO changed during patch creation")
            delta_hash = fingerprint(delta)
            iso.rename(root / iso.name)
            delta.rename(root / delta.name)
        return receipt(root, "package", {"melee": {**base.info(), **base_hash}, "built_iso": built_hash},
                       [{"path": "pokemelee.iso", **built_hash}, {"path": "pokemelee.xdelta", **delta_hash}],
                       patch_verified=True, xdelta={"version": version, **fingerprint(tool)},
                       apply=["xdelta3", "-d", "-s", "<original Melee ISO matching inputs.melee.sha256>",
                              "pokemelee.xdelta", "pokemelee.iso"])
