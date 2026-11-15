"""Fetch and verify pinned fork releases. Fork sources stay in their own repos."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile

from .catalog import PACKAGE
from .disc import safe_name
from .workspace import output_directory, receipt, write_blob


def lock():
    return json.loads((PACKAGE / "dependencies.lock.json").read_text(encoding="utf-8"))


def release_url(name, platform):
    tool = lock()["tools"][name]
    if url := tool["platforms"][platform].get("url"):
        return url
    return f"https://github.com/{tool['repo']}/releases/download/{tool['tag']}/{tool['platforms'][platform]['asset']}"


def fetch(name, platform, output, *, github_auth=False):
    """Public releases need no login. Private maintainer setup can use gh auth."""
    target = Path(output).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise ValueError(f"Output already exists; choose a new directory: {target}")
    tool = lock()["tools"][name]
    spec = tool["platforms"][platform]
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pokemelee-download-", dir=target.parent) as folder:
        archive = Path(folder) / spec["asset"]
        if github_auth and "url" not in spec:
            result = subprocess.run(["gh", "release", "download", tool["tag"], "--repo", tool["repo"],
                                     "--pattern", spec["asset"], "--dir", folder],
                                    capture_output=True, text=True, timeout=600)
            if result.returncode:
                raise ValueError(f"Could not download {name} with gh; check access to {tool['repo']} and the pinned release")
        else:
            request = urllib.request.Request(release_url(name, platform), headers={"User-Agent": "pokemelee-builder/0.1"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response, archive.open("xb") as stream:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > 1024**3:
                            raise ValueError("Runtime download exceeds 1 GiB")
                        stream.write(chunk)
            except urllib.error.URLError as exc:
                raise ValueError(f"Could not fetch {name} release. While the fork is private, maintainers can use --github-auth") from exc
        return install(name, platform, archive, output)


def install(name, platform, archive, output):
    tool = lock()["tools"][name]
    spec = tool["platforms"][platform]
    archive = Path(archive)
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != spec["sha256"]:
        raise ValueError(f"Runtime checksum mismatch for {name}/{platform}")
    with zipfile.ZipFile(archive) as src:
        members, seen, total = [], set(), 0
        for info in src.infolist():
            raw = info.filename.rstrip("/")
            path = PurePosixPath(raw)
            if not raw or path.is_absolute() or "\\" in raw or any(p in ("", ".", "..") for p in raw.split("/")):
                raise ValueError(f"Unsafe runtime archive path: {raw}")
            for part in path.parts:
                safe_name(part)
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"Runtime archive contains special file: {raw}")
            if raw.casefold() in seen:
                raise ValueError(f"Duplicate runtime path: {raw}")
            seen.add(raw.casefold())
            if raw.casefold() in ("receipt.json", "failed.json"):
                raise ValueError("Runtime archive collides with install receipt")
            total += info.file_size
            if total > 2 * 1024**3 or len(seen) > 50000:
                raise ValueError("Runtime archive exceeds size limit")
            members.append((info, raw))
        files = {raw for info, raw in members if not info.is_dir()}
        if missing := set(spec["required"]) - files:
            raise ValueError(f"Runtime archive missing required files: {sorted(missing)}")
        outputs = []
        with output_directory(output, "runtime-install") as root:
            for info, raw in members:
                if not info.is_dir():
                    outputs.append(write_blob(root, raw, src.read(info)))
                    if info.external_attr >> 16 & 0o111:
                        (root / raw).chmod(0o755)
            return receipt(root, "runtime-install", {"tool": name, "platform": platform,
                           "repository": tool["repo"], "tag": tool["tag"], "sha256": actual}, outputs)
