"""Size reception-time corrections at completed blind positions, without fitting."""

import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_reception_doppler import paired_reception_frequency
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import problem_for
from run_dsx01_clock_transfer import measurement_path
from run_dsx01_joint_marginal import OUTPUT as BASE

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency

OUTPUT = ROOT / "reports/2026_10_18_dsx01_reception_doppler"


def run():
    OUTPUT.mkdir(exist_ok=True)
    records, inputs = {}, {}
    for case in (f"DSX01-S0{k}" for k in range(1, 6)):
        source = BASE / case / "robust/endpoints.json"
        inputs[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
        fit = json.loads(source.read_text())["fits"]["c0"]
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        p = problem_for(scan, fit, "robust")
        phases = np.array(fit["state"]["phases"])[p.labels]
        site = fit["latitude_deg"], fit["longitude_deg"]
        nominal = paired_phase_frequency(p.sky, p.flat_times, p.flat_labels, phases, *site)[0]
        row = {}
        for model in ("retarded", "relativistic"):
            f, delay = paired_reception_frequency(
                p.sky,
                p.flat_times,
                p.flat_labels,
                phases,
                *site,
                relativistic=model == "relativistic",
            )
            native, centered, nonaffine, tracks = p.q * (f - nominal), [], [], []
            for i, sl in zip(p.members, p.slices, strict=True):
                t, delta = scan.tracks[i]["times"], native[sl]
                design = np.column_stack((np.ones(len(t)), t - t.mean()))
                left = delta - design @ np.linalg.lstsq(design, delta, rcond=None)[0]
                centered.extend(delta - delta.mean())
                nonaffine.extend(left)
                tracks.append(
                    dict(
                        component=scan.tracks[i]["key"],
                        correction_hz=delta,
                        nonaffine_rms_hz=float(np.sqrt(np.mean(left**2))),
                    )
                )
            row[model] = dict(
                native_RMS_hz=float(np.sqrt(np.mean(native**2))),
                curve_centered_RMS_hz=float(np.sqrt(np.mean(np.array(centered) ** 2))),
                curve_nonaffine_RMS_hz=float(np.sqrt(np.mean(np.array(nonaffine) ** 2))),
                delay_range_s=[float(delay.min()), float(delay.max())],
                tracks=tracks,
            )
        records[case] = row
    write(OUTPUT / "blind_endpoint_corrections.json", records)
    write(
        OUTPUT / "protocol.json",
        dict(
            inference_or_GPS_fit=False,
            positions_are_completed_blind_endpoints=True,
            no_GPS_or_future_TLE_used=True,
            inputs_sha256=inputs,
            common_c0_labels_and_phases=True,
            models=[
                "retarded coordinate-frequency ratio",
                "retarded plus c^-2 clock/potential terms",
            ],
            Earth_monopole_only=True,
            atmospheric_and_Shapiro_terms_omitted=True,
            primary_model_reference="https://arxiv.org/html/1312.0725#S2.SS1",
            source_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), ROOT / "tools/dsx01_reception_doppler.py")
            },
        ),
    )
    print(json.dumps(dict(scans=len(records), no_geographic_refit=True)), flush=True)


if __name__ == "__main__":
    run()
