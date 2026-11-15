"""The accepted content and its actual cold-build readiness."""
import json
from pathlib import Path

PACKAGE = Path(__file__).parent


def load(name):
    return json.loads((PACKAGE / "recipes" / name).read_text(encoding="utf-8"))


def plan():
    cast, stages, pipeline = load("cast.json"), load("stages.json"), load("pipeline.json")
    blockers = [row for row in pipeline["steps"] if row["state"] != "verified"]
    return {"profile": "pokemelee-plain", "baseline": "Cast Test 30",
            "iso_build_ready": not blockers, "cast": cast, "stages": stages,
            "pipeline": pipeline["steps"], "blocking_steps": [b["id"] for b in blockers]}


def art_indices():
    cast = load("cast.json")
    return sorted({c["art_index"] for c in cast["fighters"] + cast["partners"]})
