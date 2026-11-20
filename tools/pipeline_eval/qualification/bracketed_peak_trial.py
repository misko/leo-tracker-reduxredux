"""Seal fixed-lag weak-peak proposals before scoring against independent detector outputs."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from ..__main__ import ROOT, local_output, save_json
from ..variants import bracketed_peak as method
from ..variants import coherent_peak_filter, track_epoch
from .factor_cross import winner
from .full_v5_check import BULK, _load_case, _sha
from .prefix_figures import csv_file

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
BASE = SCREEN / "receiver-core/full-stride"
OUT = SCREEN / "track-recovery/bracketed-peaks"
CASES = (
    "DS26-0036",
    "DS29-0082",
    "DS26-0237",
    "DS29-0174",
    "DS26-0122",
    "DS29-0247",
    "DS26-0162",
    "DS29-0519",
)
MODES = ("bracketed", "sham")


def read(path):
    return json.loads(path.read_bytes())


def freeze(out):
    file = BASE / "prediction-lock.json"
    refs = read(file)["files"]
    if _sha(BASE / "source-lock.json") != refs["source-lock.json"]:
        raise ValueError("source lock no longer matches the whole-IQ record")
    original = read(BASE / "source-lock.json")["cases"]
    assert set(original) == set(CASES)
    frozen = {}
    for ident in CASES:
        name = f"native/control/{ident}.json.gz"
        frozen[ident] = dict(
            wide_file=name,
            wide_archive_sha256=refs[name],
            capture_native_sha256=original[ident]["capture_native_sha256"],
        )
    code = [
        Path(__file__),
        Path(method.__file__),
        Path(coherent_peak_filter.__file__),
        Path(track_epoch.__file__),
        out / "PROTOCOL.md",
    ]
    source = dict(inputs=frozen, parent_lock=_sha(file), files={p.name: _sha(p) for p in code})
    lock = out / "source-lock.json"
    if lock.exists() and read(lock) != source:
        raise ValueError("existing weak-peak plan binds different inputs or code")
    save_json(lock, source)
    return source


def wide(ident, plan):
    item = plan["inputs"][ident]
    archive = BASE / item["wide_file"]
    if _sha(archive) != item["wide_archive_sha256"]:
        raise ValueError(f"changed wide archive for {ident}")
    raw = gzip.decompress(archive.read_bytes())
    return json.loads(raw), sha256(raw).hexdigest()


def lock_files(out, name, files):
    save_json(out / name, dict(files={file: _sha(out / file) for file in files}))


def select(out):
    if (out / "selection-lock.json").exists():
        raise FileExistsError("choose a fresh directory for a new measurement")
    plan = freeze(out)
    edits, tables = {}, []
    for ident in CASES:
        doc, digest = wide(ident, plan)
        source = doc["source"]
        rate = source["sample_rate_hz"]
        edits[ident] = dict(native_sha256=digest)
        for mode in MODES:
            wall, cpu = perf_counter(), process_time()
            chosen, counts = method.select(source["probes"], rate, sham=mode == "sham")
            costs = dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - wall)
            edits[ident][mode] = chosen
            tables.append(
                dict(
                    id=ident,
                    mode=mode,
                    edits=len(chosen),
                    probes=counts["probes"],
                    negative=counts["negative"],
                    bracketed=counts.get("bracketed_negative_with_candidates", 0),
                    peak_pending=counts.get("largest_pending_lane", 0),
                    capacity_evictions=counts.get("capacity_evictions", 0),
                    max_released_delay_s=max(
                        (e["delay_samples"] / rate for e in chosen), default=None
                    ),
                    **costs,
                )
            )
    save_json(out / "edits.json", edits)
    csv_file(out / "selection.csv", tables)
    lock_files(out, "selection-lock.json", ("edits.json", "source-lock.json", "selection.csv"))
    return tables


def exact_probe(wide_probe, capture_probe):
    return {k: v for k, v in wide_probe.items() if k != "candidates"} == {
        k: v for k, v in capture_probe.items() if k != "candidates"
    }


def agreement(doc, teacher, changes):
    source = doc["source"]
    other = teacher["source"]
    rate = source["sample_rate_hz"]
    if (
        source["session_id"] != other["session_id"]
        or rate != other["sample_rate_hz"]
        or doc["clock_anchor"] != teacher["clock_anchor"]
    ):
        raise ValueError("different capture clocks or session")
    positives, missed, hits = {}, 0, 0
    for i, (p, q) in enumerate(zip(source["probes"], other["probes"], strict=True)):
        if not exact_probe(p, q):
            raise ValueError("incompatible detector opportunity")
        j = winner(q["candidates"])
        if j is not None:
            positives[i] = q["candidates"][j]
            missed += winner(p["candidates"]) is None
    counted = set()
    for row in changes:
        i, j = row["probe_index"], row["candidate_index"]
        p = source["probes"][i]
        if i in counted or winner(p["candidates"]) is not None:
            raise ValueError("change must select one measured row on a previously negative probe")
        counted.add(i)
        if i not in positives:
            continue
        chosen = method.Peak.from_candidate(p, p["valid_start_counter"], p["candidates"][j])
        target = method.Peak.from_candidate(p, p["valid_start_counter"], positives[i])
        hits += method.close_peak(
            chosen.epoch, chosen.cfo_hz, target.epoch, target.cfo_hz, rate / method.FRAME_RATE_HZ
        )
    return dict(
        capture_positive=len(positives),
        capture_positive_wide_negative=missed,
        selected=len(changes),
        capture_positive_at_selection=len(counted & positives.keys()),
        same_capture_winner=hits,
    )


def score(out):
    if (out / "measurement-lock.json").exists():
        raise FileExistsError("scoring already sealed")
    for name, hash_ in read(out / "selection-lock.json")["files"].items():
        if _sha(out / name) != hash_:
            raise ValueError("selection inputs changed after the seal")
    edits, plan, rows = read(out / "edits.json"), read(out / "source-lock.json"), []
    for ident in CASES:
        doc, native_hash = wide(ident, plan)
        case = _load_case(ident)
        capture = BULK / case["native"]["path"]
        if (
            native_hash != edits[ident]["native_sha256"]
            or _sha(capture) != plan["inputs"][ident]["capture_native_sha256"]
        ):
            raise ValueError("detector inputs differ from preselection identities")
        teacher = read(capture)
        for mode in MODES:
            rows.append(dict(id=ident, mode=mode, **agreement(doc, teacher, edits[ident][mode])))
    csv_file(out / "bracketed-peaks.csv", rows)
    lock_files(out, "measurement-lock.json", ("selection-lock.json", "bracketed-peaks.csv"))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("select", "score"))
    parser.add_argument("--out", type=local_output, default=OUT)
    args = parser.parse_args()
    print(json.dumps((select if args.action == "select" else score)(args.out), indent=2))
