"""Rebuild approved stage recipes directly from the two source discs."""
import json
import copy
from pathlib import Path
import struct
import subprocess

from .catalog import PACKAGE, load
from .export import fingerprint
from .fsys import entries
from .workspace import output_directory, receipt, write_blob, write_json

FLAVORS = {"agate": "agate", "realgam": "agate", "phenac-lobby": "bf",
           "mt-battle-crater": "fd", "mt-battle-garden": "ys", "phenac-city": "stadium"}
NATIVE_TOOLS = set(FLAVORS.values()) | {"forms", "colodump"}


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
            if relative == "celebi/celebi.dat":
                archive, entry = "wzx_relive_celebi_appear.fsys", "00_relive_celebi_appear.t20"
                blob = self.archive(archive)[entry]
                offset = 0x520  # HSD archive inside the Colosseum cutscene resource
                length = struct.unpack_from(">I", blob, offset)[0]
                if length < 0x20 or offset + length > len(blob):
                    raise ValueError("Invalid Celebi HSD archive extent")
                data = blob[offset:offset + length]
                source = {"game": role, "file": archive, "entry": entry, "offset": offset, "bytes": length}
            else:
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
    with Image.open(dump / "tex/T0000_CMP.png") as atlas:
        return generate(atlas, geometry, anime=anime)


def anime_stage(source, target, row, spec):
    from . import anime_flat, anime_stage as lines
    flat = bytearray(anime_flat.stage(source))
    if source.name in ("GrPs.dat", "GrPs.usd"):
        raw = source.read_bytes()
        for off, image in anime_flat.stage_parts(source)[1].items():
            if (image.width, image.height) == (768, 168):
                size = anime_flat.datprobe.gx_image_size(image.format, image.width, image.height)
                at = anime_flat.HEADER + off
                flat[at:at + size] = raw[at:at + size]
    flat_path = source.parent.parent / "flat" / source.name
    flat_path.parent.mkdir(exist_ok=True)
    flat_path.write_bytes(flat)
    edge_visible = None
    if row["id"] == "mt-battle-garden":
        from .anime_garden import edge_filter
        edge_visible = edge_filter(flat_path, spec)
    return lines.outline(flat_path, target, edge_visible=edge_visible)


def build_stages(melee, colosseum, output, runtime, selected=None, profile="normal"):
    if profile not in ("normal", "animelee"):
        raise ValueError("Unknown stage profile")
    reference = load(f"references/{profile}.json")["files"]
    rows = load("stages.json")["stages"]
    names = set(selected or [r["id"] for r in rows])
    if names - {r["id"] for r in rows}:
        raise ValueError("Unknown stage recipe")
    outputs = []
    with output_directory(output, "stages") as root:
        inputs = Inputs(melee, colosseum, root / "inputs")
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
                spec_path = root / (name + ".json")
                write_json(spec_path, current)
                run_helper(runtime, flavor, ["build", spec_path], root / (name + ".log"))
                if not target.is_file():
                    raise ValueError(f"Stage {name} was not generated; see its local log")
                if profile == "animelee":
                    styled = root / "files" / name
                    styled.parent.mkdir(exist_ok=True)
                    log = anime_stage(target, styled, row, current)
                    (root / (name + ".anime.log")).write_text(log, encoding="utf-8")
                    target = styled
                actual = fingerprint(target)
                if actual["sha256"] != reference[name]["sha256"]:
                    raise ValueError(f"Stage {name} differs from the approved output; inspect before accepting")
                outputs.append({"path": f"files/{name}", "stage": row["id"], **actual})
        return receipt(root, "stages", {"profile": profile, "melee": melee.info(), "colosseum": colosseum.info(), "files": inputs.sources}, outputs)
