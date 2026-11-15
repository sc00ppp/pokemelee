"""Build Melee geometry and facts entirely from the user's extracted disc files."""
import json
from pathlib import Path
import sys

from rigswap.plugins import melee

job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
files, targets = Path(job["files"]), Path(job["targets"])
result = melee.prepare(files, targets)
if set(result) != set(job["fighters"]) or any(value != "made" for value in result.values()):
    raise RuntimeError(f"Incomplete Melee target conversion: {result}")
# This function uses the game's tables, not an inference provider.
melee.describe_targets(targets, files)
(targets / "complete.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
