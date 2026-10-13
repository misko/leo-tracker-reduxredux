"""Prepare matched nuisance starts and candidate proposals from frozen measured tracks."""

import argparse
import hashlib
import json
from pathlib import Path

from leo.analysis.glrt_bias_initialization import bias_shape_seed
from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, nuisance_design
from tools.audit_wrapped_full_catalogue import common_seed, embed_incumbent
from tools.evaluate_sparse_glrt import local_output, write_json
from tools.evaluate_wrapped_fast_scan import load_bundle, load_phase_bank, phase_provider


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--surface", type=Path, required=True)
    p.add_argument("--track-initial", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    data, bank, meta, _ = load_bundle(args.bundle)
    source = json.loads((args.surface / "result.json").read_text())
    tracks = json.loads(args.track_initial.read_text())
    for doc in (source, tracks):
        if (
            doc["input_digest"] != meta["input_sha256"]
            or doc["orbit_digest"] != meta["orbit_bank_sha256"]
        ):
            raise ValueError("starts and tracks must be bound to the same recording/orbits")
    if not source["completed"] or source["phase_model"] != "fixed-reception-frame-orbital-phase":
        raise ValueError("completed fixed-reception-frame reference fit required")
    cfg = WrappedConfig(**source["config"])
    if cfg.satellite_bias_sigma_hz is None or cfg.relative_phase_sigma_s is None:
        raise ValueError("source fit must use declared carrier and relative-phase priors")
    phases, receipt = load_phase_bank(args.bundle, bank)
    if receipt != source["phase_receipt"]:
        raise ValueError("changed orbital phase bank")
    provider = phase_provider(phases, bank, data, meta["site"], (0, 0), inertial_phase=True)
    known = [
        embed_incumbent(source["reference"]["arms"][a], source["candidate_norad"], bank["norad"])
        for a in ("zero-c", "fitted-c")
    ]
    warm = [common_seed(f) for f in known]
    proposed, proposals = [], []
    for arm, fit in zip(("zero-c", "fitted-c"), known, strict=True):
        design, _, _ = nuisance_design(
            data,
            bank["rf_hz"],
            coefficient=fit["coefficient_enabled"],
            band_drift=cfg.band_drift_sigma_hz_s is not None,
        )
        pred, opp, timing, _ = provider.predict(fit["phase_s"])
        candidate, matches = bias_shape_seed(
            data,
            pred,
            opp,
            tracks["bootstrap_tracks"],
            design @ fit["beta"],
            timing=timing,
            bias_sigma_hz=cfg.satellite_bias_sigma_hz,
            phase_sigma_s=cfg.relative_phase_sigma_s,
            maximum_satellites=cfg.maximum_satellites,
        )
        candidate.update(
            beta=common_seed(fit)["beta"],
            coefficient_hz_ghz=fit["coefficient_hz_ghz"],
            phase_s=fit["phase_s"],
            weights=None,
        )
        proposed.append(candidate)
        proposals.extend(
            dict(row, calibration_arm=arm, norad=int(bank["norad"][row["satellite"]]))
            for row in matches
        )
    manifest = dict(
        input_digest=meta["input_sha256"],
        orbit_digest=meta["orbit_bank_sha256"],
        phase_receipt=receipt,
        source_config=source["config"],
        source_surface_sha256=hashlib.sha256(
            (args.surface / "result.json").read_bytes()
        ).hexdigest(),
        source_tracks_sha256=hashlib.sha256(args.track_initial.read_bytes()).hexdigest(),
        source_digests={
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__),
                Path("src/leo/analysis/glrt_bias_initialization.py"),
                Path("src/leo/analysis/glrt_shape_initialization.py"),
            )
        },
        scope="Measured-track proposals; no winning labels or position errors enter matching",
    )
    for name, seeds in (("warm", warm), ("shape", proposed), ("combined", warm + proposed)):
        write_json(args.output / f"{name}-initial.json", dict(manifest, selected_seeds=seeds))
    union = set(source["candidate_norad"])
    union.update(int(bank["norad"][p["satellite"]]) for p in proposals)
    write_json(
        args.output / "proposal-pool.json",
        dict(
            input_digest=meta["input_sha256"],
            orbit_digest=meta["orbit_bank_sha256"],
            norad=sorted(union),
        ),
    )
    write_json(
        args.output / "proposals.json",
        dict(
            manifest,
            proposals=proposals,
            existing_candidates=source["candidate_norad"],
            new_candidates=sorted(union - set(source["candidate_norad"])),
        ),
    )
    print(
        json.dumps(
            dict(
                tracks=len(tracks["bootstrap_tracks"]),
                proposals=len(proposals),
                candidates=len(union),
                new_candidates=len(union - set(source["candidate_norad"])),
            )
        )
    )


if __name__ == "__main__":
    main()
