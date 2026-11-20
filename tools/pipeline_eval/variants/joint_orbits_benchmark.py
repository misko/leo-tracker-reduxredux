"""Run joint orbit assignment on a frozen anonymous-track benchmark case."""

import json
from hashlib import sha256
from pathlib import Path

from ..scoring import ARMS
from .joint_orbits import BOUNDARY, infer


def _unavailable(reason):
    return dict(
        status="unavailable",
        reason=reason,
        boundary=BOUNDARY,
        metrics={},
        arms={arm: {"latlon": None} for arm in ARMS},
    )


def run(case, work_dir):
    offers = case.get("regions", [])
    if len(offers) != 1:
        return _unavailable("single supplied tile required")
    observation, catalog = (case.get(field) for field in ("observation_path", "catalog_path"))
    if not observation or not catalog:
        return _unavailable("missing anonymous tracks or causal catalogue")
    try:
        raw, tle = Path(observation).read_bytes(), Path(catalog).read_bytes()
    except FileNotFoundError:
        return _unavailable("missing anonymous tracks or causal catalogue")
    (tile,) = offers
    result = infer(json.loads(raw), tile, tle.decode("ascii"))
    return dict(
        result,
        input_binding=dict(
            observation_sha256=sha256(raw).hexdigest(),
            catalog_sha256=sha256(tle).hexdigest(),
            tile=tile,
        ),
    )
