"""Render the report-backed historical ledger, separate from the new replay."""

# ruff: noqa: E501 -- prose table cells stay on one source line.
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

# Interpretations refer to the linked historical reports, never this scan.
OUTCOMES = {
    1: "No defensible unique phase bridge across the tested segment boundaries; sample/reference authority and ordinary-frame predictability were prerequisites.",
    2: "Exact Qin phase was measurable inside a frame, but held neighboring-frame prediction and epoch stability did not qualify either tested boundary.",
    3: "Held adjacent-frame prediction worked in P2 and parts of P1/P5; P4 failed. Comparability was confined to each independently acquired 20 ms container.",
    4: "Per-frame frequency supported a robust constant-rate line; phase innovations required explicit resets rather than a continuous carrier assumption.",
    5: "Letting discontinuous phase update the five-state filter worsened Doppler-rate estimates; the frequency-only ablation stayed closer to the reference.",
    6: "Ordinary 2pi tracking suffered frequent slips: 87.81% exceeded the configured gate in one seven-track replay. Computational completion was not a phase pass.",
    7: "Full 300-symbol/eight-tone slopes recovered useful frame-local frequency with nuisance phase per frame; that did not establish inter-frame carrier continuity.",
    8: "Modulo-pi batch interpretations explained local structure, but an offline branch fit alone was not evidence of causal or unambiguous 2pi recovery.",
    9: "Causal modulo-pi treatment avoided many ordinary-2pi resets on qualified windows; shorter wrap interval and modulo-pi selection prevent treating lower RMS alone as neutral model discovery.",
    10: "The five-state modulo-pi tracker qualified selected local windows, including 66/66 updates in the mechanism example, but only 3/40 in a separate phase-blind window sample.",
    11: "Historical production audit found 419 inner locks and 216 fully qualified 75 ms segments among 2,691 windows; all five dwells had nonzero yield.",
    12: "Short independently processed chunks retained conditional phase information; the 120 ms scale itself did not explain all degradation. Long smooth CFO lines could absorb local changes.",
    13: "Within-visit simultaneous double differences were feasible in historical adaptive scans, but bookkeeping and retune-bounded support did not certify cross-retune absolute phase.",
    14: "Pooling complex Qin evidence with independent frame nuisance phase improved held sequence support and rate repeatability over 20/50/100 ms. This was frequency recovery, not phase stitching.",
    15: "A different recording contained timestamp words in IQ and real RX0 pilots outside the old search range. Diagnostic masking did not reconstruct missing RF or certify other recordings.",
    16: "The predeclared five-dwell primary comparison was unavailable due to incomplete common support. A labeled four-dwell sensitivity favored robust jump over V2, but not over the trailing 20 ms line.",
    17: "V2 lost to a causal trailing 20 ms frequency line across 12 estimable historical dwells. V3 added phase-safe acquisition/tracking; acquisition behavior still needed the later V4 correction.",
    18: "The experimental seeded V4 completed its 537-window canary and predeclared gates while retaining the V3 tracking core. This was experimental qualification, not detector calibration or production promotion.",
    19: "Historical narrowband PSS carrier/rate evidence was conditional and SSS weak; later track-conditioned PSS improved local precision without establishing absolute carrier accuracy.",
    20: "PSS corroborated timing on some visits. Weighting, branch lifting and GLRT conditioning had to be distinguished from independent CFO validation.",
    21: "Matched-pilot double differences needed a noise-control correction: overlapping templates can create apparent common phase even with independent receiver noise.",
    22: "A frozen 20-visit study had 17 visits with at least two qualified overlap blocks; common support and source pairing excluded others. Window length changed availability and conditional precision.",
    23: "Training-only response-normalized phase passed held waveform gates on 36 late-track dwells (median R 0.9761); observed changes still exceeded candidate geometric scale and were not calibrated baseline phase.",
    24: "Raw broadband IQ resolved a receiver-offset branch and supported some shared waveform evidence; a shared broadband component did not establish that every pilot pair was the same source.",
    25: "FFT/common-band and direct-IQ formulations recovered conditional receiver phase. Full-bin Parseval equivalence is an identity, not independent evidence; masks and response fitting change the observable.",
    26: "Full captured-band alignment recovered injected delay/coherence and supported selected real dwells; usable common recorded bandwidth, fitted response and physical overlap limited interpretation.",
    27: "Wrapped instrument-inclusive RX phase could be measured on phase-blind selected tracks, but independent dwell fits did not provide a uniquely stitched absolute phase across retunes.",
    28: "Shared-counter adjacent-dwell fits showed conditional boundary continuity. A joint interior fit is distinct from a previous-dwell-only forecast, and held boundary errors remained far above geometric scale.",
    29: "Multiple historical tracks supplied conditional phase measurements, with corrected device-counter centers needed for comparisons. Within-recording repetition was not independent-session replication.",
    30: "Phase supplied conditional RX-pairing evidence. Candidate-specific geometric boundary changes were orders of magnitude smaller than residuals; direct TLE reranking was not supported by that observable.",
}

OVERRIDE = {
    1: "reports/2026_08_22_frame_local_phase_qualification.md",
    8: "reports/2026_08_22_edge_pilot_phase_slope.md",
    11: "reports/2026_08_23_five_dwell_modulo_pi_qualification.md",
    30: "reports/2026_09_25_phase_assisted_satellite_association/REPORT.md",
}


def main() -> None:
    methods = json.loads((HERE / "method-registry.json").read_text())["methods"]
    lines = [
        "# Historical phase-recovery approaches",
        "",
        "These are outcomes reported on earlier recordings, not results for `scan-fw-32a202b6e55630ec`. The new replay keeps failures, conditional successes and distinct phase observables separate. Multiple rows are variants of a shared estimator and are not independent experiments.",
        "",
        "| Approach | Historical report | Reported outcome |",
        "| --- | --- | --- |",
    ]
    for method in methods:
        number = method["ledger_row"]
        source = OVERRIDE.get(number)
        if source is None:
            source = next(path for path in method["historical_report_refs"] if path.endswith(".md"))
        path = REPO / source
        if not path.is_file():
            raise FileNotFoundError(path)
        label = (
            path.stem.replace("_", " ")
            if path.name != "REPORT.md"
            else path.parent.name.replace("_", " ")
        )
        link = os.path.relpath(path, HERE)
        lines.append(f"| {number:02d}. {method['name']} | [{label}]({link}) | {OUTCOMES[number]} |")
    (HERE / "HISTORICAL_REVIEW.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
