"""Extract explicit inputs from the user's discs, without modifying the discs."""
from pathlib import PurePosixPath

from . import fsys
from .workspace import digest, output_directory, receipt, write_blob


def extract(disc, output, names, *, unpack=False):
    names = sorted(set(names))
    if not names:
        raise ValueError("Select at least one disc file")
    missing = set(names) - disc.entries.keys()
    if missing:
        raise ValueError(f"Missing disc files: {', '.join(sorted(missing))}")
    if unpack and any(not name.lower().endswith(".fsys") for name in names):
        raise ValueError("--unpack-fsys accepts only FSYS archives")
    sources, outputs = [], []
    with output_directory(output, "extract") as root:
        for name in names:
            data = disc.read(name)
            sources.append({"disc_file": name, "bytes": len(data), "sha256": digest(data)})
            if unpack:
                stem = str(PurePosixPath(name).with_suffix(""))
                for entry, payload in fsys.entries(data):
                    outputs.append(write_blob(root, f"{stem}/{entry}", payload))
            else:
                outputs.append(write_blob(root, name, data))
        return receipt(root, "extract", {"disc": disc.info(), "files": sources}, outputs)
