"""Adapt sealed owner-oracle coordinates to the standard roof figure contract."""

import argparse
import gzip
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, validate_result
from .fresh_scenes import _read, _sha
from .full_v5_check import _load_case
from .owner_factor import CASES, FILE, REPORT, _load
from .owner_factor_models import BOUNDARY

CARD_PREFIX = "owner-oracle-"
PUBLIC_LABEL = "Diagnostic only · no fixes issued"
SOURCE_LOCK = "source-lock.json"
INPUT_LOCK = "input-lock.json"
PREDICTION_LOCK = "prediction-lock.json"
ORIGINAL_LOCK = "original-prediction-lock.json"
CARDS = (
    (
        "common-lean-owners",
        "Common mask · lean owners and matched aliases",
        ("lean_owner_lean_alias", "lean_owner_v5_alias"),
    ),
    (
        "common-v5-owners",
        "Common mask · v5 owners and matched aliases",
        ("v5_owner_lean_alias", "v5_owner_v5_alias"),
    ),
    ("full-v5-lean", "Full v5 conditional mask · lean exact fit", ("v5_full_lean",)),
    ("common-v5-clock", "Common mask · v5 owners and compact clock/prior", ("v5_common_clock",)),
    ("full-v5-clock", "Full v5 conditional mask · compact clock/prior", ("v5_full_clock",)),
    (
        "full-v5-diagonal",
        "Full v5 conditional mask · compact diagonal noise",
        ("v5_full_diagonal",),
    ),
)
DIAGNOSTIC_LABELS = {
    "common-lean-owners": "Forced · common lean owners",
    "common-v5-owners": "Forced · common v5 owners",
    "full-v5-lean": "Forced · full v5, lean fit",
    "common-v5-clock": "Forced · common clock/prior",
    "full-v5-clock": "Forced · full clock/prior",
    "full-v5-diagonal": "Forced · full diagonal noise",
}


def _bindings(case, trial):
    native, catalog, observation = "native_sha256", "catalog_sha256", "observation_sha256"
    expected = {
        native: case["native"]["sha256"],
        catalog: case["catalog"]["sha256"],
        observation: case["observation"],
    }
    if any(trial["bindings"].get(name) != digest for name, digest in expected.items()):
        raise ValueError(f"{case['id']} owner oracle differs from rooftop input authority")
    return expected


def _forced(trial, cells):
    records = [trial["estimates"][cell] for cell in cells]
    for item in records:
        validate_result(item)
        if item["status"] != "withheld" or any(
            arm["latlon"] is not None or arm.get("forced_latlon") is None
            for arm in item["arms"].values()
        ):
            raise ValueError("standard owner-oracle figures require sealed forced outcomes")
    first = records[0]
    if any(item["arms"] != first["arms"] for item in records[1:]):
        raise ValueError("distinct alias outcomes cannot share an owner-oracle card")
    return {
        arm: {
            "latlon": None,
            "forced_latlon": first["arms"][arm]["forced_latlon"],
            "rf_rms_hz": first["arms"][arm].get("rf_rms_hz"),
        }
        for arm in ARMS
    }


def export(source=REPORT, output=None):
    source = Path(source).resolve()
    output = Path(output or source / "standard-roof").resolve()
    if source == output:
        raise ValueError("write the standard export separately from the original predictions")
    lock = _read(source / PREDICTION_LOCK)
    if (
        tuple(lock["cases"]) != CASES
        or _sha(source / FILE) != lock["files"][FILE]
        or _sha(source / SOURCE_LOCK) != lock["source_lock_sha256"]
        or _sha(source / INPUT_LOCK) != lock["input_lock_sha256"]
    ):
        raise ValueError("owner-oracle archive differs from its prediction seal")
    trials = _load(source / FILE)
    if len(trials) != len(CASES) or {row["id"] for row in trials} != set(CASES):
        raise ValueError("owner-oracle archive lacks the complete rooftop roster")
    by_id = {row["id"]: row for row in trials}
    bindings = {case: _bindings(_load_case(case), by_id[case]) for case in CASES}
    rows, charts = [], []
    for name, title, cells in CARDS:
        identifier = CARD_PREFIX + name
        for case in CASES:
            arms = _forced(by_id[case], cells)
            rows.append(
                dict(
                    id=case,
                    method=identifier,
                    **bindings[case],
                    result=dict(
                        status="withheld",
                        reason="forced_diagnostic_only",
                        boundary=BOUNDARY,
                        metrics={"privileged_diagnostic": True},
                        arms=arms,
                    ),
                )
            )
        charts.append(
            dict(
                id=identifier,
                method=identifier,
                scope="roof",
                title=f"Privileged owner oracle · {title}",
                caption="Forced estimates use archived ownership, masks or alias evidence.",
                cases=list(CASES),
                seal=PREDICTION_LOCK,
                provenance=[ORIGINAL_LOCK, INPUT_LOCK],
                source_lock={"file": SOURCE_LOCK, "digest_key": "source_lock_sha256"},
                series=[
                    dict(
                        key="one",
                        label=PUBLIC_LABEL,
                        forced_label=DIAGNOSTIC_LABELS[name],
                        file=FILE,
                        value=identifier,
                    )
                ],
            )
        )
    content = gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0)
    write(output / FILE, content)
    for current, target in (
        (PREDICTION_LOCK, ORIGINAL_LOCK),
        (SOURCE_LOCK, SOURCE_LOCK),
        (INPUT_LOCK, INPUT_LOCK),
    ):
        write(output / target, (source / current).read_bytes())
    save_json(
        output / PREDICTION_LOCK,
        dict(
            cases=list(CASES),
            source_lock_sha256=lock["source_lock_sha256"],
            files={name: _sha(output / name) for name in (FILE, ORIGINAL_LOCK, INPUT_LOCK)},
        ),
    )
    save_json(output / "figures.json", dict(version=1, charts=charts))
    return tuple(chart["id"] for chart in charts)


if __name__ == "__main__":
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--evidence", type=Path, default=REPORT)
    command.add_argument("--out", type=Path)
    args = command.parse_args()
    for chart in export(args.evidence, args.out):
        print(chart)
