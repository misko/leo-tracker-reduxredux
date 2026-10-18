"""Inventory jointly supported phase clipping across all five DSX01 scans."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from search_track_evidence_position import ROOT, EvidenceExperiment

from leo.analysis.research.phase_family_nomination import nominate_clipped_families

PRIOR = ROOT / "reports/2026_10_17_robust_curve_reassociation"


def load_study(case, fitted_c):
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter" / case
    bank = (
        ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs" / case
        if case == "DSX01-S01"
        else PRIOR / "frozen_inputs" / case
    )
    study = EvidenceExperiment(
        recording,
        bank,
        fitted_c=fitted_c,
        phase_enabled=True,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1,
    )
    partition = PRIOR / "partition" / case
    receipt = json.loads((partition / "receipt.json").read_text())
    for key in ("curves", "background"):
        if (
            hashlib.sha256((partition / f"{key}.json").read_bytes()).hexdigest()
            != receipt[f"{key}_sha256"]
        ):
            raise ValueError("robust partition changed")
    tracks = json.loads((partition / "curves.json").read_text())
    for t in tracks:
        t["times"], t["values"] = np.asarray(t["times"]), np.asarray(t["values"])
    background = json.loads((partition / "background.json").read_text())
    study.set_observation_partition(tracks, [r["observation_id"] for r in background])
    arm = "fitted_c" if fitted_c else "c0"
    if case == "DSX01-S01":
        source = PRIOR / "fits" / case / f"repaired_{arm}" / "fixed_site.json"
        fit = json.loads(source.read_text())["fit"]
    elif case == "DSX01-S02":
        source = PRIOR / "track_evidence_audit" / case / f"repaired_{arm}" / "safeguarded_fit.json"
        fit = json.loads(source.read_text())
    else:
        source = PRIOR / "fixed_cohort" / case / arm / "fit.json"
        fit = json.loads(source.read_text())
    return study, fit, source, recording, background


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for i in range(1, 6):
        case = f"DSX01-S{i:02d}"
        arms, sources = {}, {}
        for fitted in (False, True):
            arm = "fitted_c" if fitted else "c0"
            study, fit, source, _, _ = load_study(case, fitted)
            association = study.associate(fit)
            folder = output / case / arm
            folder.mkdir(parents=True)
            write(folder / "baseline_association.json", association)
            write(folder / "baseline_fit.json", fit)
            arms[arm] = association
            sources[arm] = dict(
                path=str(source.relative_to(ROOT)),
                sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            )
            if not fitted:
                sky, phases, bounds = study.sky["norad"], fit["phases_s"], study.bounds
        families = nominate_clipped_families(
            arms["c0"]["rows"], arms["fitted_c"]["rows"], sky, phases, bounds
        )
        write(output / case / "nominations.json", families)
        row = dict(
            case=case,
            candidates=families,
            baseline_points={arm: r["compatible_points"] for arm, r in arms.items()},
            source_fits=sources,
        )
        summaries.append(row)
        write(output / "progress.json", summaries)
        print(json.dumps(row), flush=True)
    write(output / "summary.json", summaries)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            nomination_source_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/phase_family_nomination.py").read_bytes()
            ).hexdigest(),
            common_c0_nomination_population=True,
            minimum_curved_fragments=2,
            fraction_of_phase_bound_required=0.995,
            only_candidates_with_admitted_curved_support_in_either_arm_locked=True,
            linear_only_candidates_do_not_lock_phase_or_veto_curved_nominations=True,
            curved_fragments_already_admitted_in_either_arm_excluded_from_new_calibration=True,
            measured_curvature_not_polynomial_degree=True,
            no_linear_calibration=True,
            supplied_gps_fixed=True,
            not_a_position_accuracy_experiment=True,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.output)
