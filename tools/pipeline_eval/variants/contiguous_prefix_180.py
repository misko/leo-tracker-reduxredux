"""Benchmark the measured 180-second compact v5 fit on frozen capture-era GLRT."""

import json
import os
from hashlib import sha256
from pathlib import Path

from ..__main__ import local_output
from ..qualification.contiguous_prefix_trial import position
from ..qualification.full_v5_check import BULK, _load_case
from ..qualification.recording_to_v5 import save
from ..scoring import ARMS
from .contiguous_prefix import BOUNDARY, PREFIX_SECONDS, restrict


def _unavailable(reason):
    return dict(
        status="unavailable",
        reason=reason,
        boundary=BOUNDARY,
        metrics={},
        arms={arm: {"latlon": None} for arm in ARMS},
    )


def run(case, work_dir):
    sealed = _load_case(case["id"])
    required = ("native", "request", "track_config", "catalog")
    if not all(isinstance(sealed.get(k), dict) for k in required):
        return _unavailable("180-second replay requires complete frozen GLRT and v5 bindings")

    native = sealed["native"]
    root = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", BULK))
    try:
        raw = (root / native["path"]).read_bytes()
    except OSError as error:
        return _unavailable(str(error))
    native_sha = sha256(raw).hexdigest()
    if native_sha != native["sha256"]:
        raise ValueError("capture-era GLRT input differs from the frozen digest")
    document = json.loads(raw)
    try:
        view, metrics = restrict(document, prefix=True)
    except ValueError as error:
        return _unavailable(str(error))

    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "native-prefix.json"
    save(path, view)
    try:
        prediction = position(sealed, path, work_dir, metrics, "capture-era-prefix")
    except OSError as error:
        return _unavailable(str(error))
    result = prediction["result"]
    result["input_binding"] = dict(
        case_id=sealed["id"],
        capture_native_sha256=native_sha,
        inference_factor_sha256=prediction["inference_factor_sha256"],
        request_sha256=sealed["request"]["sha256"],
        track_config_sha256=sealed["track_config"]["sha256"],
        catalog_sha256=sealed["catalog"]["sha256"],
        prefix_seconds=PREFIX_SECONDS,
    )
    return result
