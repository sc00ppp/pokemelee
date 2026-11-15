"""Local output handling: new directories only; completion recorded last."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


@contextmanager
def output_directory(path, operation):
    # Check the lexical leaf first so even a broken symlink cannot be overwritten.
    root = Path(path).expanduser().absolute()
    if root.exists() or root.is_symlink():
        raise ValueError(f"Output already exists; choose a new directory: {root}")
    root.mkdir(parents=True, exist_ok=False)
    root = root.resolve()
    try:
        yield root
    except Exception as exc:
        write_json(root / "failed.json", {"operation": operation, "error": str(exc)})
        raise


def receipt(root, operation, inputs, outputs, **extra):
    value = dict(schema=1, operation=operation, complete=True,
                 created_utc=datetime.now(timezone.utc).isoformat(),
                 inputs=inputs, outputs=outputs, **extra)
    write_json(root / "receipt.json", value)
    return value


def write_blob(root, relative, data):
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Output escapes workspace: {relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    return {"path": relative, "bytes": len(data), "sha256": digest(data)}
