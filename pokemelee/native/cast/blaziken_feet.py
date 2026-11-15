"""Recover Falcon's contact planes from his original costume geometry."""
import json
from pathlib import Path
import numpy as np
from cast_paths import WORK

source = Path(__file__).with_name("stand_feet.py")
ns = {"__name__": "feet_helpers", "__file__": str(source)}
exec(compile(source.read_text(encoding="utf-8").rsplit("\nmain()", 1)[0], str(source), "exec"), ns)
fighter = "CaptainFalcon"
rest, below = ns["skeleton"](fighter)
names = {v: k for k, v in ns["JOINT_NAMES"][fighter].items()}
own = ns["vanilla_feet"](fighter, rest, below, names, ns["sole"])
result = {}
for side, (normal, depth, toe, along, part) in own.items():
    points = ns["foot_points"](below[names[side + "FootJ"]])
    result[side] = [normal.tolist(), None, float(depth), toe, along.tolist(), float(part), float(np.ptp(points @ along))]
(WORK / "hand/blaziken-CaptainFalcon/reference/vanilla-feet.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
