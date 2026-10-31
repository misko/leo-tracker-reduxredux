"""Relocate active ALGO04 evidence; preserve its nested historical export bytes."""

import hashlib
import json
import re
import shutil
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relocate(source, destination, original_root, files):
    """Verify original bytes first; rebind only local paths and their digest edges.

    The source remains untouched. Hash edges are checked against original bytes
    before a new digest is calculated, so relocation cannot bless corrupt proofs.
    """
    source, destination, origin = Path(source), Path(destination), Path(original_root)
    if not origin.is_absolute() or destination.exists():
        raise ValueError("Absolute origin and unused cache destination required")
    for name, expected in files.items():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("Unsafe exported member")
        member = source / p
        if any(
            p.is_symlink() for p in (member, *member.parents) if p != source.parent
        ) or not member.resolve().is_relative_to(source.resolve()):
            raise ValueError("Export member escapes private source")
        if digest(member) != expected.removeprefix("sha256:"):
            raise ValueError("Export bytes changed: " + name)
    destination.mkdir(parents=True)
    done, active = {}, set()

    def relative(value):
        if not isinstance(value, str) or not value.startswith(str(origin) + "/"):
            return None
        part = Path(value).relative_to(origin)
        if ".." in part.parts:
            raise ValueError("Embedded cache path escapes private source")
        return str(part)

    def path_value(value):
        if value == str(origin):
            return str(destination)
        name = relative(value)
        return str(destination / name) if name is not None else value

    def convert(value):
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, str):
            return path_value(value)
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            name = relative(key)
            if (
                name is not None
                and name not in files
                and isinstance(item, str)
                and re.fullmatch(r"(sha256:)?[0-9a-f]{64}", item)
            ):
                raise ValueError("Original proof member missing from private export: " + key)
            if (
                name in files
                and isinstance(item, str)
                and re.fullmatch(r"(sha256:)?[0-9a-f]{64}", item)
            ):
                if files[name].removeprefix("sha256:") != item.removeprefix("sha256:"):
                    raise ValueError("Original proof digest mismatch: " + key)
                changed = materialize(name)
                result[path_value(key)] = (
                    "sha256:" if item.startswith("sha256:") else ""
                ) + changed
            elif key == "files" and isinstance(item, dict) and isinstance(value.get("root"), str):
                # The snapshot contract uses relative file keys and a root.
                mapped = {}
                for child, expected in item.items():
                    member = relative(str(Path(value["root"]) / child))
                    if member in files:
                        if files[member].removeprefix("sha256:") != expected.removeprefix(
                            "sha256:"
                        ):
                            raise ValueError("Original snapshot digest mismatch: " + child)
                        mapped[child] = (
                            "sha256:" if expected.startswith("sha256:") else ""
                        ) + materialize(member)
                    else:
                        raise ValueError("Snapshot member missing from private export: " + child)
                result[key] = mapped
            else:
                result[path_value(key)] = convert(item)
        return result

    def materialize(name):
        if name in done:
            return done[name]
        if name in active:
            raise ValueError("Cyclic scientific receipt hashes")
        active.add(name)
        src, dst = source / name, destination / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".json" and Path(name).parts[0] != "source-export":
            dst.write_text(
                json.dumps(convert(json.loads(src.read_text())), indent=2, allow_nan=False) + "\n"
            )
        else:
            shutil.copyfile(src, dst)
        done[name] = digest(dst)
        active.remove(name)
        return done[name]

    for name in files:
        materialize(name)
    return dict(
        source_hashes=files,
        relocated_hashes=done,
        original_root=str(origin),
        relocated_root=str(destination),
        scientific_values_unchanged=True,
        opaque_historical_subtrees=["source-export"],
    )
