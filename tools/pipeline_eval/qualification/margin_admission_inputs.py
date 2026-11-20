"""Bind sealed complete wide factors and prior detector prevalence."""

import gzip
import json
from hashlib import sha256

from ..__main__ import ROOT, save_json
from ..variants import margin_admission as method
from .full_v5_check import BULK, _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/margin-admission"
WIDE = REPORT.parent.parent / "acquisition-support/scout-full"
TRAIN = ("DS26-0036", "DS29-0082")
HELD = ("DS26-0237", "DS29-0174", "DS26-0014", "DS29-0127")
CPUS = (6, 11)
LIMIT_S = 170


def read(path):
    return json.loads(path.read_bytes())


def authority(ident):
    lock = read(WIDE / "prediction-lock.json")
    source = WIDE / "source-lock.json"
    if _sha(source) != lock["files"][source.name] or ident not in lock["cases"]:
        raise ValueError("expected a published complete wide waveform")
    source_fields = read(source)
    plan = source_fields["cases"][ident]
    name = f"native/control/{ident}.json.gz"
    path = WIDE / name
    return dict(
        id=ident,
        native_export=name,
        export_sha256=lock["files"][name],
        parent_prediction_sha256=_sha(WIDE / "prediction-lock.json"),
        catalogue_sha256=plan["catalog_sha256"],
        capture_request_sha256=plan["request_sha256"],
        capture_native_sha256=plan["capture_native_sha256"],
        tile=plan["tile"],
        track_loader=source_fields["receiver"],
    ), path


def load(ident):
    binding, path = authority(ident)
    if _sha(path) != binding["export_sha256"]:
        raise ValueError("sealed wide factors changed")
    raw = gzip.decompress(path.read_bytes())
    data = json.loads(raw)
    binding["wide_native_sha256"] = sha256(raw).hexdigest()
    return raw, data, binding


def key(value):
    return tuple(value[k] for k in ("visit_index", "receiver_id", "probe_index"))


def population(ident, document, binding):
    case = _load_case(ident)
    path = BULK / case["native"]["path"]
    if _sha(path) != binding["capture_native_sha256"]:
        raise ValueError("capture-era detector labels changed")
    teacher = read(path)["source"]
    wide = document["source"]
    if (
        teacher["session_id"] != wide["session_id"]
        or teacher["sample_rate_hz"] != wide["sample_rate_hz"]
    ):
        raise ValueError("teacher belongs to another acquisition or sample rate")
    records = {key(p): p for p in teacher["probes"]}
    if len(records) != len(teacher["probes"]):
        raise ValueError("duplicate capture-era probe authority")
    result = []
    for p in wide["probes"]:
        old = records.get(key(p))
        if old is not None and any(
            old[k] != p[k] for k in ("valid_start_counter", "channel", "edge")
        ):
            raise ValueError("wide receiver probe body differs from capture-era hardware support")
        active = old is not None and any(c[method.FLAG] for c in old["candidates"])
        result.append((p["valid_start_counter"], method.probe_margin(p), active))
    return result


def lock_threshold(plan_sha):
    current = REPORT / "threshold-lock.json"
    if current.exists():
        raise FileExistsError(current)
    groups, receipts = [], {}
    for ident in TRAIN:
        _, doc, bound = load(ident)
        source = population(ident, doc, bound)
        groups.append([(score, label) for _, score, label in source])
        receipts[ident] = bound
    minimum = method.threshold(groups)
    summary = {
        ident: dict(
            count=len(group),
            teacher_positive=sum(label for _, label in group),
            ordinary_positive=sum(score >= method.STOCK for score, _ in group),
            calibrated_positive=sum(score >= minimum for score, _ in group),
        )
        for ident, group in zip(TRAIN, groups, strict=True)
    }
    rows = dict(
        plan_sha256=plan_sha,
        threshold=minimum,
        threshold_hex=minimum.hex(),
        inputs=receipts,
        prevalence=summary,
    )
    save_json(current, rows)
    return rows
