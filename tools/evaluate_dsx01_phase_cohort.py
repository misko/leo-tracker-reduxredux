"""Complete matched fixed-GPS phase fits; never a geographic accuracy claim."""

import argparse
import json
from pathlib import Path

from associate_merged_track_catalogue import write
from evaluate_shared_satellite_phase import Experiment, protocol


def run(case, output):
    root = Path(__file__).resolve().parents[1]
    recording = root / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter" / case
    for fitted_c in (False, True):
        study = Experiment(
            recording,
            Path(f"/tmp/ds22-shared-phase-bank-{case}"),
            fitted_c=fitted_c,
            phase_enabled=True,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1.0,
        )
        own = output / case / ("c0" if not fitted_c else "fitted_c")
        protocol(study, own, "fixed_supplied_site_cohort", 32)
        fit = study.fit(37.849061591561885, -122.48574968092912, 32, exact=True)
        assoc = study.associate(fit)
        write(
            own / "diagnosis.json",
            [
                dict(
                    site="supplied_evaluation_site",
                    fit=fit,
                    association=assoc,
                    use="fixed ground-truth diagnostic, not an estimated position",
                )
            ],
        )
        print(
            json.dumps(
                dict(
                    case=case,
                    fitted_c=fitted_c,
                    compatible_points=assoc["compatible_points"],
                    fragments=assoc["compatible_fragments"],
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=tuple(f"DSX01-S{i:02}" for i in range(1, 6)), required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.output)
