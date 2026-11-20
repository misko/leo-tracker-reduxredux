"""Verify and load the exact Python sources used by the measured curvature study."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
REPORT_RELATIVE = "reports/2026_11_19_receiver_screening/streamlined/late-routing"
REPORT = ROOT / REPORT_RELATIVE
ZIP = "measured-source.zip"
BLIND = "archive-predecision.json.gz"
BLIND_LOCK = "archive-predecision-lock.json"
GATE = "tools/pipeline_eval/variants/late_routing.py"
TRIAL = "tools/pipeline_eval/qualification/late_routing_trial.py"
WORKER = "tools/pipeline_eval/qualification/late_routing_worker.py"
EXTRACTOR = "tools/pipeline_eval/qualification/late_routing_archive.py"
BYPASS = "tools/pipeline_eval/qualification/late_routing_bypass.py"


def _digest(data):
    return sha256(data).hexdigest()


def _recorded_digest(sources, relative):
    parts = Path(relative).parts
    matches = [
        digest for path, digest in sources.items() if Path(path).parts[-len(parts):] == parts
    ]
    if len(matches) != 1:
        raise ValueError(f"missing or ambiguous measured source {relative}")
    return matches[0]


def measured_sources(folder):
    """Verify the archive from the original receipts, independent of checkout path."""
    run_bytes = (folder / "run-lock.json").read_bytes()
    blind_bytes = (folder / BLIND_LOCK).read_bytes()
    run, blind = json.loads(run_bytes), json.loads(blind_bytes)
    bypass = json.loads((folder / "bypass-lock.json").read_bytes())
    if (
        blind["run_lock_sha256"] != _digest(run_bytes)
        or bypass["parent_science"] != _digest(run_bytes)
        or bypass["archive_predecision"] != _digest(blind_bytes)
    ):
        raise ValueError("measured run, archive and bypass receipts do not bind to each other")
    protocol_digest = _recorded_digest(run["sources"], f"{REPORT_RELATIVE}/PROTOCOL.md")
    if _digest((folder / "PROTOCOL.md").read_bytes()) != protocol_digest:
        raise ValueError("the measured protocol differs from its original receipt")
    expected = {
        **{name: _recorded_digest(run["sources"], name) for name in (GATE, TRIAL, WORKER)},
        EXTRACTOR: blind["extractor_sha256"],
        BYPASS: bypass["source"],
    }
    with ZipFile(folder / ZIP) as archive:
        if sorted(archive.namelist()) != sorted(expected):
            raise ValueError("unexpected member in measured source archive")
        sources = {name: archive.read(name) for name in expected}
    for name, data in sources.items():
        if _digest(data) != expected[name]:
            raise ValueError(f"measured {name} differs from the original source receipt")
    return sources


def _load(sources, relative):
    name = relative.removesuffix(".py").replace("/", ".")
    module = ModuleType(name)
    module.__file__ = relative
    module.__package__ = name.rpartition(".")[0]
    exec(compile(sources[relative], relative, "exec"), module.__dict__)
    return module


def measured_extract(sources):
    """Reconstruct the original archive extractor with its original gate."""
    extractor = _load(sources, EXTRACTOR)
    extractor.evaluate = _load(sources, GATE).evaluate
    return extractor.extract


def measured_worker(sources):
    """Bind the replayed numerical worker to the measured in-process gate."""
    worker = _load(sources, WORKER)
    worker.late_routing = _load(sources, GATE)
    return worker.worker


def verify_run(folder, current):
    """Require the same inputs and runtime, with measured sources from the archive."""
    sealed = json.loads((folder / "run-lock.json").read_bytes())
    if {k: v for k, v in current.items() if k != "sources"} != {
        k: v for k, v in sealed.items() if k != "sources"
    }:
        raise ValueError("causal requests, frozen runtime or matched roster changed")
    return sealed, measured_sources(folder)


def verify_gates(folder):
    """Compare both implementations with every sealed decision and RF diagnostic."""
    from ..variants.late_routing import evaluate

    original = _load(measured_sources(folder), GATE).evaluate
    lock = json.loads((folder / BLIND_LOCK).read_bytes())
    data = (folder / BLIND).read_bytes()
    if _digest(data) != lock["files"][BLIND]:
        raise ValueError("recorded gating evidence differs from the original receipt")
    rows = json.loads(gzip.decompress(data))
    if sorted(row["id"] for row in rows) != lock["cases"]:
        raise ValueError("recorded gating cases differ from the original roster")
    routed = bypassed = 0
    for row in rows:
        wanted = {k: v for k, v in row["route"].items() if k not in ("cpu_s", "wall_s")}
        if original(row["samples"]) != wanted or evaluate(row["samples"]) != wanted:
            raise ValueError(f"{row['id']} recorded, original or cleaned gate differs")
        routed += int(wanted["run"])
        bypassed += int(not wanted["run"])
    return dict(cases=len(rows), routed=routed, bypassed=bypassed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    print(json.dumps(verify_gates(parser.parse_args().report), sort_keys=True))
