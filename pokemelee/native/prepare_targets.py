"""Build Melee geometry and facts entirely from the user's extracted disc files."""
import json
from pathlib import Path
import sys
import runpy

from rigswap.plugins import melee

job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
files, targets = Path(job["files"]), Path(job["targets"])
result = melee.prepare(files, targets)
if set(result) != set(job["fighters"]) or any(value != "made" for value in result.values()):
    raise RuntimeError(f"Incomplete Melee target conversion: {result}")
# This function uses the game's tables, not an inference provider.
melee.describe_targets(targets, files)
sys.path.insert(0, str(Path(__file__).parent / "cast"))
runpy.run_path(str(Path(__file__).parent / "cast/ics_targets.py"), run_name="__main__")
for name in ("Popo", "Nana"):
    if not (targets / (name + ".blend")).is_file():
        raise RuntimeError("Incomplete Ice Climbers target: " + name)
    result[name] = "made"
(targets / "complete.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
