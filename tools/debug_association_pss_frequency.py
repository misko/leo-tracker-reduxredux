"""Bounded retained-IQ frequency replay and frozen association failure inventory."""

import argparse
import gzip
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.nearest_neighbour_association import gaussian_innovation_score
from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band, band_template
from leo.storage.adaptive_hop import AdaptiveHopIqStore


def select_cases(sessions):
    """One conspicuous failed association per rate/side; intentionally diagnostic."""
    selected = {}
    for session in sessions:
        p = session["tracking"]["product"]
        reviews = {r["tracklet_id"]: r for r in p["track_reviews"]}
        for a in p["tle_candidates"]:
            r = reviews.get(a["representative_tracklet_id"])
            if not a["abstention_recommended"] or r is None or len(r["candidates"]) < 2:
                continue
            best, runner = r["candidates"][:2]
            ratio = runner["randomized_evaluation_rms_hz"] / max(
                best["randomized_evaluation_rms_hz"], 1e-9
            )
            key = (session["sample_rate_hz"], r["edge"])
            case = dict(
                session_id=session["session_id"],
                rate=key[0],
                ratio=ratio,
                manifest=session["capture_digest"],
                review=r,
                association=a,
            )
            if key not in selected or ratio > selected[key]["ratio"]:
                selected[key] = case
    return [selected[key] for key in sorted(selected)]


def search_rows(iq, band, offsets, start, index, label):
    result = acquire_pss_band(
        iq,
        band,
        device_sample_start=start,
        continuity_segment_index=index,
        frequency_offsets_hz=offsets,
    )
    rows = []
    for h in result.hypotheses:
        candidates = h.candidates
        best = max(candidates, key=lambda c: c.robust_z, default=None)
        overlap = band.overlap_hz(h.nominal_frequency_offset_hz)
        rows.append(
            dict(
                kind=label,
                cfo_hz=h.nominal_frequency_offset_hz,
                qualified=len(h.qualified_candidates),
                max_z=best.robust_z if best else None,
                peak_ratio=best.peak_to_median if best else None,
                phase_samples=best.frame_phase_samples if best else None,
                overlap_hz=overlap[1] - overlap[0],
            )
        )
    return rows


def replay(case, root):
    store = AdaptiveHopIqStore(root, read_only=True)
    session = store.inspect(case["session_id"])
    assert session.manifest_sha256 == case["manifest"]
    receipt = session.manifest.receipt
    g = receipt.plan.geometry
    assert g.receiver_ids == (0,)
    r = case["review"]
    middle = (r["start_s"] + r["end_s"]) / 2
    visits = [
        (i, v)
        for i, v in enumerate(receipt.visits)
        if v.event.target.channel == r["channel"] and v.event.target.edge.value == r["edge"]
    ]
    index, selected_visit = min(
        visits,
        key=lambda item: abs(
            (item[1].event.valid_start_counter - receipt.terminal.first_counter) / g.sample_rate_hz
            - middle
        ),
    )
    with store.reader(session.session_id, expected=session) as reader:
        visit, raw = reader.read_visit_ci16(index)
    e = visit.event
    assert e == selected_visit.event, "retained ordinal does not identify selected event"
    # A continuous 20 ms slice: 15 frame opportunities, identical for every hypothesis.
    raw = raw[: round(g.sample_rate_hz * 0.02)]
    iq = (raw[:, 0, 0].astype(np.float32) + 1j * raw[:, 0, 1]).astype(np.complex64)
    reference = starlink_pss_channel_reference_hz(e.target.channel, e.target.edge)
    center = e.actual_lo_frequency_hz + e.actual_if_offset_hz
    half = min(g.sample_rate_hz, g.bandwidth_hz) / 2
    band = PssCaptureBand(g.sample_rate_hz, center - reference, -half, half)
    start = e.valid_start_counter - receipt.terminal.first_counter
    offsets = tuple(float(f) for f in range(-1_200_000, 1_200_001, 100_000))
    rows = search_rows(iq, band, offsets, start, index, "retained")
    rng = np.random.default_rng(20260920)
    # Same exact periodogram; destroy phase organization. This is one diagnostic control.
    surrogate = np.fft.ifft(np.abs(np.fft.fft(iq)) * np.exp(2j * np.pi * rng.random(len(iq))))
    rows += search_rows(
        surrogate.astype(np.complex64), band, offsets, start, index, "phase-randomized"
    )
    # Matched synthetic positive control, not an independent waveform validation.
    cfo = 300_000.0
    pulse = band_template(band, cfo, fft_size=131072).samples.copy()
    pulse *= np.exp(2j * np.pi * cfo * np.arange(len(pulse)) / g.sample_rate_hz)
    injected = (rng.normal(size=len(iq)) + 1j * rng.normal(size=len(iq))).astype(np.complex64)
    for k in range(15):
        pos = round(g.sample_rate_hz * (0.00037 + k / 750))
        if pos + len(pulse) <= len(iq):
            injected[pos : pos + len(pulse)] += 25 * pulse
    rows += search_rows(injected, band, offsets, start, index, "injected-300kHz")
    store.close()
    return dict(
        **case,
        retained_ordinal=index,
        visit_index=e.visit_index,
        sample_count=len(iq),
        band=asdict(band),
        actual_center_hz=center,
        reference_hz=reference,
        rows=rows,
    )


def score_sensitivity():
    output = []
    residual = np.linspace(-50, 50, 14)
    for prediction_sigma in (0.0, 400.0, 800.0, 1600.0):
        score = gaussian_innovation_score(
            residual,
            [100.0] * 14,
            [prediction_sigma] * 14,
            offset_prior_standard_uncertainty_hz=25.0,
        )
        output.append(
            dict(
                prediction_sigma_hz=prediction_sigma,
                rms_hz=float(np.sqrt(np.mean(residual**2))),
                nll=score.marginal_negative_log_likelihood,
                logdet=score.log_determinant_covariance,
                quadratic=score.mahalanobis_squared,
            )
        )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.audit) as stream:
        sessions = json.load(stream)["sessions"]
    cases = select_cases(sessions)
    (args.output / "selected-cases.json").write_text(json.dumps(cases, indent=2))
    failures = Counter()
    margins = []
    for session in sessions:
        for a in session["tracking"]["product"]["tle_candidates"]:
            failures.update(a["abstention_reasons"])
            margins.append(dict(session_id=session["session_id"], **a))
    (args.output / "association-evidence.json").write_text(
        json.dumps(
            dict(reasons=failures, comparisons=margins, covariance_sensitivity=score_sensitivity()),
            indent=2,
        )
    )
    results = []
    for case in cases:
        path = args.output / f"{case['session_id']}-{case['review']['edge']}.json"
        if path.exists():
            result = json.loads(path.read_text())
        else:
            result = replay(case, args.bulk_root)
            path.write_text(json.dumps(result, indent=2))
        results.append(result)
        print(case["session_id"], case["rate"], case["review"]["edge"], flush=True)
    fig, axes = plt.subplots(3, 2, figsize=(14, 12), sharex=True)
    for axis, result in zip(axes.flat, results, strict=True):
        for kind in ("retained", "phase-randomized", "injected-300kHz"):
            rows = [r for r in result["rows"] if r["kind"] == kind]
            axis.plot([r["cfo_hz"] / 1e6 for r in rows], [r["max_z"] for r in rows], label=kind)
        axis.axhline(6, color="grey", linestyle="--", label="z gate (not sufficient)")
        axis.set_title(
            f"{result['rate'] / 1e6:g} MS/s · CH{result['review']['channel']} "
            f"{result['review']['edge']}\n{result['session_id']}"
        )
        axis.set_ylabel("Maximum folded robust z")
        axis.set_xlabel("Searched carrier offset (MHz)")
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(args.output / "pss-frequency-controls.png", dpi=150)
    for axis in axes.flat:
        axis.set_ylim(0, 20)
    fig.suptitle("Score detail · injected positive-control peaks exceed this 0–20 zoom")
    fig.tight_layout()
    fig.savefig(args.output / "pss-frequency-detail.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
