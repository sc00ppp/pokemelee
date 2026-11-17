"""Reject binary/game payloads and machine-specific paths in candidate source.

This is a guard against accidental commits, not a copyright/provenance verdict.
Only inspect Git's tracked files and nonignored untracked candidates.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {".py", ".json", ".toml", ".md", ".yml", ".yaml", ".cs", ".csproj", ".c"}
EXACT = {".gitignore", ".gitattributes"}
# Third-party licence texts ship verbatim, as the plain .txt their projects publish them in
LICENCE_TEXTS = ("third_party_licenses", {".txt"})
PERSONAL_PATH = re.compile(r"(?:[A-Z]:[\\/](?:Users|randall-runs|rigswap-core|colo_tmp|projects|SSBM Nucleus)[\\/])", re.I)


def check(path, data):
    errors = []
    licence_text = path.parts[:1] == (LICENCE_TEXTS[0],) and path.suffix.lower() in LICENCE_TEXTS[1]
    if path.name not in EXACT and path.suffix.lower() not in ALLOWED and not licence_text:
        errors.append("not an allowed source extension")
    if len(data) > 512 * 1024:
        errors.append("unexpectedly large source file")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return errors + ["binary/non-UTF-8 content"]
    if "\0" in content:
        errors.append("NUL bytes")
    if PERSONAL_PATH.search(content):
        errors.append("personal workstation path")
    if re.search(r"(?:data:[^;]+;base64,|[A-Za-z0-9+/]{2048,})", content):
        errors.append("possible embedded binary payload")
    return errors


def main():
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=ROOT, check=True, capture_output=True)
    paths = sorted(set(p.decode("utf-8") for p in result.stdout.split(b"\0") if p))
    problems = []
    for name in paths:
        path = ROOT / name
        if path.is_symlink():
            problems.append((name, ["symlink"]))
        elif path.exists():
            if errors := check(Path(name), path.read_bytes()):
                problems.append((name, errors))
    for name, errors in problems:
        print(f"{name}: {', '.join(errors)}", file=sys.stderr)
    print(f"Checked {len(paths)} source candidates; {len(problems)} rejected")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
