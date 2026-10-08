"""Reference-free bounded coarse-region inventory and regional fit replay."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter31"))
# isort: off
from branch import regional  # noqa: E402
from inputs import write_json  # noqa: E402
from newer import load_member  # noqa: E402
# isort: on


def inventory(document, count=32):
    points = document["methods"][0]["points"]
    coarse = sorted(
        (r for r in points if r["spacing_km"] == 40 and r["objective"] is not None),
        key=lambda r: (r["objective"], r["east_km"], r["north_km"]),
    )[:count]
    selected = []
    for source, rows in (
        ("coarse40", coarse),
        ("ordinary-retained", document["diagnostics"]["retained_basins"]),
    ):
        for rank, row in enumerate(rows, 1):
            point = [row["east_km"], row["north_km"]]
            if any(r["point"] == point for r in selected):
                continue
            selected.append(dict(index=len(selected), point=point, source=source, source_rank=rank))
    return selected


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    document = json.loads((REPORTS / plan["baseline"]).read_text())
    assert inventory(document) == plan["regions"]
    members = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())[
        "members"
    ]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    canary = json.loads(
        (REPORTS / "2026_10_08_position_error_iter31/results/discarded.json").read_text()
    )
    invocation_start = time.monotonic()
    for region in plan["regions"]:
        path = HERE / "results" / f"region-{region['index']:02d}.json"
        if path.exists():
            # Completed immutable outputs are checkpoints, including failed attempts.
            saved = json.loads(path.read_text())
            assert saved["region"] == region
            assert (
                saved["protocol_sha256"]
                == hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
            )
            continue
        if time.monotonic() - invocation_start >= 600:
            print("Checkpointed bounded invocation; remaining regions require resume", flush=True)
            return
        begun = time.monotonic()
        result = dict(
            region=region,
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        )
        try:
            fitted, receipt = regional(case, region["point"])
            fitted["scope"] = (
                "Private bounded score-selected coarse inventory; no reference selection"
            )
            result.update(status="complete", document=fitted, receipt=receipt)
            if region["point"] == canary["point"]:
                for row, old in zip(
                    receipt["regional_fits"], canary["receipt"]["regional_fits"], strict=True
                ):
                    assert (row["arm"], row["start"]) == (old["arm"], old["start"])
                    assert row["fit"]["converged"] == old["fit"]["converged"]
                    for key in ("vector", "objective"):
                        np.testing.assert_allclose(
                            row["fit"][key], old["fit"][key], atol=1e-5, rtol=0
                        )
                result["canary_passed"] = True
        except (ValueError, TimeoutError) as error:
            result.update(status="failed", error=repr(error))
        result["elapsed_s"] = time.monotonic() - begun
        write_json(path, result)
        print(
            region["index"],
            region["point"],
            result["status"],
            round(result["elapsed_s"], 2),
            flush=True,
        )


if __name__ == "__main__":
    main()
