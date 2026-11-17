"""Rebuild approved stage recipes directly from the two source discs."""
from concurrent.futures import ProcessPoolExecutor
import json
import copy
from pathlib import Path
import subprocess
import threading

from .catalog import PACKAGE, load
from .export import fingerprint
from .fsys import entries
from .parallel import run_all, workers
from .workspace import output_directory, receipt, write_blob, write_json

FLAVORS = {"agate": "agate", "realgam": "agate", "phenac-lobby": "bf",
           "mt-battle-crater": "fd", "mt-battle-garden": "ys", "phenac-city": "stadium"}
NATIVE_TOOLS = set(FLAVORS.values()) | {"forms", "colodump", "menugraft", "texenc"}
# phenac.generate keeps its work in module globals, and the normal and AniMelee stage steps run at once (11-15: the
# normal GrPs.dat once came out with the other step's state): one generate at a time
PHENAC = threading.Lock()
STADIUM_SCREEN = 1      # GrPs's map_head group 1 is the big screen (decomp gr/grpstadium.c: PsType_Display)


def compile_tools(runtime, flavors=None):
    runtime = Path(runtime).resolve()
    library = runtime / "hsdlib/win-x64/HSDRaw.dll"
    if not library.is_file():
        raise ValueError("Fetch the pinned Windows HSDRaw runtime before compiling stage helpers")
    for flavor in sorted(set(flavors or NATIVE_TOOLS)):
        if flavor not in NATIVE_TOOLS:
            raise ValueError(f"Unknown native stage flavor: {flavor}")
        target = runtime / "stagegraft" / flavor
        args = ["dotnet", "build", str(PACKAGE / "native/stagegraft.csproj"), "-c", "Release",
                f"-p:Flavor={flavor}", f"-p:HSDRawPath={library}",
                f"-p:BaseIntermediateOutputPath={runtime / 'stagegraft-obj' / flavor}/",
                "-o", str(target), "--nologo", "-v", "quiet"]
        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise ValueError(f"Stage helper {flavor} did not compile: {result.stdout}\n{result.stderr}")


class Inputs:
    def __init__(self, melee, colosseum, root):
        self.discs = {"melee": melee, "colosseum": colosseum}
        self.root, self.archives, self.sources = root, {}, []

    def archive(self, name):
        if name not in self.archives:
            blob = self.discs["colosseum"].read(name)
            self.archives[name] = dict(entries(blob))
        return self.archives[name]

    def resolve(self, value):
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        if not isinstance(value, str) or not value.startswith("${"):
            return value
        role, relative = value[2:].split("}/", 1)
        path = (self.root / role / relative).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"Recipe path escapes workspace: {value}")
        if role == "generated":
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative.startswith("ps/san/") and not path.is_file():
                from .hsd import sanitize_stage
                filename = Path(relative).name
                raw = self.discs["melee"].read(filename)
                record = write_blob(self.root, f"generated/{relative}", sanitize_stage(raw))
                self.sources.append({"game": "melee", "file": filename, "operation": "resolve_model_group_externs", "sha256": record["sha256"]})
            return str(path)
        if path.is_file():
            return str(path)
        if role == "melee":
            data = self.discs[role].read(relative)
            source = {"game": role, "file": relative}
        elif role == "colosseum":
            archive, entry = relative.split("/", 1)
            archive += ".fsys"
            data = self.archive(archive)[entry]
            source = {"game": role, "file": archive, "entry": entry}
        else:
            raise ValueError(f"Unknown recipe input role: {role}")
        record = write_blob(self.root, f"{role}/{relative}", data)
        self.sources.append({**source, "sha256": record["sha256"]})
        return str(path)


def run_helper(runtime, flavor, args, log):
    executable = Path(runtime).resolve() / "stagegraft" / flavor / f"stagegraft-{flavor}.dll"
    if not executable.is_file():
        raise ValueError(f"Compile the native stage helper first: {flavor}")
    result = subprocess.run(["dotnet", str(executable), *map(str, args)],
                            capture_output=True, text=True, timeout=600)
    Path(log).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError(f"Stage helper {flavor} failed; see {Path(log).name}")


def stadium_meshes(inputs, runtime, root, anime=False):
    from PIL import Image
    from .phenac import generate
    source = inputs.resolve("${colosseum}/M1_out/04_M1_out.rdat")
    dump = root / "phenac-textures"
    run_helper(runtime, "colodump", [source, dump], root / "phenac-textures.log")
    geometry = root / "phenac-geometry"
    geometry.mkdir()
    with Image.open(dump / "tex/T0000_CMP.png") as atlas, PHENAC:
        return generate(atlas, geometry, anime=anime)


def stadium_pictures(source):
    """(image offsets, palette offsets) of Stadium's pictures that AniMelee leaves as they are: the 768x168 one (flattening
    ruined it) and everything the big screen shows, whose type announcements came out as blobs of the stage's colours."""
    from . import anime_flat
    dat, images = anime_flat.stage_parts(source)[:2]
    screen_images, screen_tables = anime_flat.group_textures(dat, STADIUM_SCREEN)
    big = {off for off, image in images.items() if (image.width, image.height) == (768, 168)}
    return sorted(screen_images | big), sorted(screen_tables)


def anime_stage(source, target, spec):
    from . import anime_flat, anime_stage as lines, stage_characters as cast
    roots = cast.item_roots(lines.Dat.read(source), spec)
    keep = stadium_pictures(source) if source.name in ("GrPs.dat", "GrPs.usd") else ((), ())
    flat = bytearray(anime_flat.stage(source, roots=roots, characters=cast.materials(source, roots), keep=keep))
    flat_path = source.parent.parent / "flat" / source.name
    flat_path.parent.mkdir(exist_ok=True)
    flat_path.write_bytes(flat)
    depths = cast.flight_depths(flat_path, spec)
    return lines.outline(flat_path, target, edge_visible=cast.edge_filter(flat_path, roots, depths), roots=roots, depths=depths,
                         plain=cast.plain_filter(flat_path, spec, roots), quiet=cast.quiet_filter(flat_path, spec, roots),
                         solid=cast.scenery_filter(flat_path, spec, 'solid', roots),
                         sideways=cast.scenery_filter(flat_path, spec, 'sides', roots), water=cast.water(spec))


def files_in(value):
    """The existing files a spec names."""
    if isinstance(value, dict):
        return set().union(*map(files_in, value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*map(files_in, value)) if value else set()
    if isinstance(value, str) and len(value) < 1024 and Path(value).is_absolute() and Path(value).is_file():
        return {Path(value).resolve()}
    return set()


def sharing(jobs):
    """The stage jobs in groups that share no input file. A helper opens its inputs for itself (HSDRaw), so two at
    once on one file fail: each group runs in turn, the groups side by side."""
    groups = []
    for job in jobs:
        files = files_in(job[3])
        joined = [g for g in groups if g[0] & files]
        for g in joined:
            groups.remove(g)
        groups.append((files.union(*(g[0] for g in joined)), [j for g in joined for j in g[1]] + [job]))
    return [jobs_ for _, jobs_ in groups]


def build_stages(melee, colosseum, output, runtime, selected=None, profile="normal"):
    if profile not in ("normal", "animelee"):
        raise ValueError("Unknown stage profile")
    reference = load(f"references/{profile}.json")["files"]
    rows = load("stages.json")["stages"]
    names = set(selected or [r["id"] for r in rows])
    if names - {r["id"] for r in rows}:
        raise ValueError("Unknown stage recipe")
    with output_directory(output, "stages") as root:
        inputs = Inputs(melee, colosseum, root / "inputs")
        jobs = []       # (row, name, flavor, spec, built file): every input is resolved here, before any job runs
        for row in rows:
            if row["id"] not in names:
                continue
            spec = inputs.resolve(load(row["spec"]))
            if row["id"] == "phenac-city":
                spec["cs"]["meshes"] = stadium_meshes(inputs, runtime, root, anime=profile == "animelee")
            for approved in row["approved_outputs"]:
                name = approved["name"]
                current = copy.deepcopy(spec)
                flavor = FLAVORS[row["id"]]
                if name.startswith("GrPs"):
                    if name in ("GrPs.dat", "GrPs.usd"):
                        current["target"] = inputs.resolve("${generated}/ps/san/" + name)
                    else:
                        form = {"1": "fire", "2": "grass", "3": "water", "4": "rock"}[name[4]]
                        current = inputs.resolve(load(f"stages/stadium-{form}.json"))
                        flavor = "forms"
                target = root / ("unstyled" if profile == "animelee" else "files") / name
                target.parent.mkdir(exist_ok=True)
                current["out"] = str(target)
                write_json(root / (name + ".json"), current)
                jobs.append((row, name, flavor, current, target))

        def build(group):
            from .dat import Dat
            from .stage_characters import item_roots, light
            for row, name, flavor, current, target in group:
                run_helper(runtime, flavor, ["build", root / (name + ".json")], root / (name + ".log"))
                if not target.is_file():
                    raise ValueError(f"Stage {name} was not generated; see its local log")
                if profile == "normal":     # AniMelee's characters stay flat: lights off and plain colours are its style
                    done = light(target, target, item_roots(Dat.read(target), current))
                    (root / (name + ".light.log")).write_text(str(done), encoding="utf-8")

        run_all(build, sharing(jobs))
        if profile == "animelee":
            # the outlines are Python through and through: one process per stage, all cores
            (root / "files").mkdir(exist_ok=True)
            with ProcessPoolExecutor(workers(len(jobs))) as pool:
                logs = list(pool.map(anime_stage, *zip(*[(target, root / "files" / name, current)
                                                         for _, name, _, current, target in jobs])))
            for (_, name, *_), log in zip(jobs, logs):
                (root / (name + ".anime.log")).write_text(log, encoding="utf-8")
        outputs = []
        for row, name, *_ in jobs:
            target = root / "files" / name
            actual = fingerprint(target)
            if actual["sha256"] != reference[name]["sha256"]:
                raise ValueError(f"Stage {name} differs from the approved output; inspect before accepting")
            outputs.append({"path": f"files/{name}", "stage": row["id"], **actual})
        return receipt(root, "stages", {"profile": profile, "melee": melee.info(), "colosseum": colosseum.info(), "files": inputs.sources}, outputs)
