"""Reproduce archived ordinary DS18 transport; no new fit or truth-guided inputs."""

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from engine import common_inventory, inventory, load, read  # noqa: E402
from policy import endpoint_sources  # noqa: E402


def main():
    reports = HERE.parent
    bindings = read(reports / "2026_10_09_position_error_iter51/protocol.json")["members"]
    binding = next(b for b in bindings if b["member"]["inventory_label"] == "DS18-022")
    case, baseline, _ = load(binding)
    original = read(reports / "2026_10_08_position_error_iter41/protocol.json")
    assert inventory(baseline) == original["regions"]
    regions = [read(p) for p in sorted(
        (reports / "2026_10_08_position_error_iter41/results").glob("region-*.json")
    )]
    regions = [r for r in regions if r["status"] == "complete"]
    _, actual = common_inventory(case, baseline, regions)
    expected = read(reports / "2026_10_09_position_error_iter53/results.json")
    assert actual["candidate_union"] == expected["candidate_union"]
    assert len(actual["rows"]) == len(expected["rows"]) == 192
    for new, old in zip(actual["rows"], expected["rows"], strict=True):
        for key in ("region", "source_arm", "start", "basin", "status", "violations"):
            assert new[key] == old[key], (key, new["region"])
        for key in ("seed", "clock", "affine_delta", "common_score"):
            np.testing.assert_allclose(new[key], old[key], rtol=0, atol=1e-6)
    assert endpoint_sources(actual["rows"]) == read(
        reports / "2026_10_09_position_error_iter71/protocol.json"
    )["endpoint_indices"]
    print("PASS: ordinary inventory, 145-satellite union, 192 transports, 63 source indices")


if __name__ == "__main__":
    main()
