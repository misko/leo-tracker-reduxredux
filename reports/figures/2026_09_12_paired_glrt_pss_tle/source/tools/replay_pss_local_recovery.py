"""Bounded raw-IQ diagnostic of PSS branch recovery around frozen causal priors."""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from leo.analysis.starlink.pss_timing import (
    _conditioned_template,
    _fractional_match_peak,
    pss_subband_template,
)
from leo.storage import RecordingStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output
    if out.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    out.mkdir(exist_ok=True)
    root = Path("/srv/bulk/leo/experiments")
    source = root / "paired-five-pss-bandwidth-20260912-v2-fractional"
    lock = root / "paired-five-pss-bandwidth-20260912-v3-causal-lock"
    cs = json.loads((source / "selection.json").read_text())["selected"]
    summaries = json.loads((source / "summary.json").read_text())
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    try:
        for c in cs:
            result = []
            b = c["native"]["binding"]
            rate = 25_000_000
            bundle = store.inspect(c["capture_id"])
            if (
                "sha256:" + bundle.manifest_sha256.removeprefix("sha256:")
                != c["native"]["manifest_digest"]
            ):
                raise ValueError("manifest changed")
            reader = store.reader(bundle, b["stream_id"], verify=True)
            summary = next(
                r
                for r in summaries
                if r["capture_id"] == c["capture_id"] and r["lane"] == "native25"
            )
            decisions = json.loads((lock / (c["capture_id"] + ".json")).read_text())["decisions"]
            for bi in range(9):
                doc = json.loads((source / c["capture_id"] / f"native25-{bi:02}.json").read_text())
                mode = next(
                    m
                    for m in doc["result"]["modes"]
                    if m["mode_id"] in summary["selected_mode_ids"]
                )
                ws = mode["windows"]
                first, last = (
                    ws[0]["fractional_global_device_sample"] / rate,
                    ws[-1]["fractional_global_device_sample"] / rate,
                )
                selected = [
                    d
                    for d in decisions
                    if d["predicted_phase_s"] is not None
                    and first - 1e-9 <= d["time_s"] <= last + 1e-9
                ]
                rejected = [d for d in selected if d["status"] == "rejected"]
                accepted = [d for d in selected if d["status"] == "accepted"]
                control = (
                    [
                        accepted[i]
                        for i in np.unique(
                            np.linspace(0, len(accepted) - 1, min(4, len(accepted)), dtype=int)
                        )
                    ]
                    if accepted
                    else []
                )
                chosen = sorted(rejected + control, key=lambda d: d["index"])
                span = reader.read_device_span(
                    doc["input_device_sample_start"], 6_250_000, receiver_ids=(b["receiver_id"],)
                )
                if not span.valid_samples.all() or len(np.unique(span.continuity_segment_ids)) != 1:
                    raise ValueError("missing or discontinuous IQ")
                digest = hashlib.sha256(span.samples.tobytes()).hexdigest()
                if digest != doc["selected_iq_sha256"]:
                    raise ValueError("IQ hash changed")
                iq = span.samples[:, 0, 0].astype(np.float32) + 1j * span.samples[:, 0, 1].astype(
                    np.float32
                )
                projection = doc["projection"]
                template = pss_subband_template(
                    rate,
                    slice_center_offset_hz=projection["output_center_frequency_hz"]
                    - projection["channel_reference_hz"],
                )
                cfo = mode["nominal_frequency_offset_hz"]
                bytime = {round(w["fractional_global_device_sample"], 3): w for w in ws}

                def analyze(
                    d,
                    iq=iq,
                    template=template,
                    cfo=cfo,
                    doc=doc,
                    bi=bi,
                    rate=rate,
                    bytime=bytime,
                    c=c,
                ):
                    old = d["time_s"] * rate
                    prediction = old - d["innovation_s"] * rate
                    center = prediction - doc["input_device_sample_start"]
                    lo, hi = int(np.floor(center - 2)), int(np.ceil(center + 2)) + 1
                    origin = lo - 16
                    stop = hi + len(template) + 16
                    aperture = iq[origin:stop]
                    left, right = lo - origin, hi - origin

                    def measure(frequency):
                        conditioned = _conditioned_template(template, frequency, rate)
                        delay, power, _ = _fractional_match_peak(
                            aperture, conditioned, search_start=left, search_stop=right
                        )
                        return delay + origin, power

                    fixed_delay, fixed_power = measure(cfo)
                    freqs = cfo + np.arange(-150_000, 150_001, 25_000)
                    trials = [measure(f) for f in freqs]
                    winner = int(np.argmax([p for _, p in trials]))
                    bestfreq = float(freqs[winner])
                    bestdelay, bestpower = trials[winner]
                    if 0 < winner < len(freqs) - 1:
                        optimum = minimize_scalar(
                            lambda f: -measure(f)[1],
                            bounds=(freqs[winner - 1], freqs[winner + 1]),
                            method="bounded",
                            options={"xatol": 50, "maxiter": 18},
                        )
                        delay, power = measure(optimum.x)
                        if power > bestpower:
                            bestfreq = float(optimum.x)
                            bestdelay, bestpower = delay, power
                    w = bytime[round(old, 3)]
                    return dict(
                        index=d["index"],
                        block_index=bi,
                        time_s=d["time_s"] - c["native_start_s"],
                        original_status=d["status"],
                        original_phase_ns=d["observed_phase_s"] * 1e9,
                        prior_phase_ns=d["predicted_phase_s"] * 1e9,
                        original_innovation_ns=d["innovation_s"] * 1e9,
                        fixed_cfo_innovation_ns=(fixed_delay - center) / rate * 1e9,
                        joint_innovation_ns=(bestdelay - center) / rate * 1e9,
                        original_cfo_hz=cfo,
                        joint_cfo_hz=bestfreq,
                        original_power=w["normalized_match_power"],
                        fixed_cfo_power=fixed_power,
                        joint_power=bestpower,
                        interior=bool(lo + 0.5 < bestdelay < hi - 1.5),
                        cfo_interior=bool(freqs[0] < bestfreq < freqs[-1]),
                    )

                with ThreadPoolExecutor(max_workers=4) as pool:
                    result.extend(pool.map(analyze, chosen))
                print(
                    c["capture_id"][-6:],
                    bi,
                    "rejected",
                    len(rejected),
                    "controls",
                    len(control),
                    flush=True,
                )
            (out / (c["capture_id"] + ".json")).write_text(
                json.dumps(
                    dict(capture_id=c["capture_id"], records=result), indent=2, allow_nan=False
                )
                + "\n"
            )
    finally:
        store.close()
    (out / "protocol.json").write_text(
        json.dumps(
            dict(
                source=str(source),
                lock=str(lock),
                prior="frozen existing causal prediction; recovered points do not update it",
                selection="every rejected frame plus up to four evenly spaced "
                "accepted controls per 250ms block",
                timing_half_radius_samples=2,
                integer_bounds="floor/ceil around fractional prior; bounded guards",
                cfo_radius_hz=150000,
                cfo_step_hz=25000,
                cfo_refinement_tolerance_hz=50,
                fresh_rf=False,
                all_45_iq_hashes_verified=True,
                validation="conditional diagnostic; not end-to-end lock",
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
