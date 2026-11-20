"""Check the observed sign of a known native pilot arrival-time perturbation."""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np

from leo.analysis.starlink.native_short_window import NativeShortWindow

from ..__main__ import ROOT, save_json
from . import range_epoch_model as m
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _load_case, _sha
from .input_factor_bridge import check
from .pilot_kernel_eval import _windows
from .wide_regional_eval import RATE, synthetic, templates

OUT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/range-epoch"
BUILD = Path("/srv/bulk/leo-dev/20261119-wide-regional/wide/width-receipt.json")
SHIFTS = (0, -9, -4, 4, 9)
COUNTER = 5913168033303
ACTUAL = "DS26-0036"


def keys(window):
    rows = window["rows"]
    selected = {}
    for row in rows:
        rx = row["receiver_id"]
        peaks = [
            p
            for p in row["candidates"]
            if p["fractional_epoch"]["status"] == "complete"
            and p["fractional_epoch"]["margin"] >= 0.025
        ]
        selected[rx] = peaks
    return selected


def strongest(peaks):
    return max(peaks, key=lambda p: p["fractional_epoch"]["margin"], default=None)


def epoch(peak):
    return peak["epoch"] + peak["fractional_epoch"]["offset_samples"]


def cfo(peak):
    return peak["fractional_epoch"]["tracking_cfo_hz"]


def measure(binary, window, origin, source):
    edge = window.target["edge"]
    period = RATE / m.FRAME_HZ
    with NativeShortWindow(
        binary,
        *templates(RATE, edge),
        sample_rate_hz=RATE,
        receiver_count=len(window.receiver_ids),
        fractional_epoch=True,
    ) as detector:
        stock = keys(detector.analyze(window.samples))
        results = []
        for shift in SHIFTS:
            delayed = np.roll(window.samples, shift, axis=0)
            tested = keys(detector.analyze(delayed)) if shift else stock
            stamp = sha256(delayed.tobytes()).hexdigest()
            for rx, peaks in stock.items():
                begin = strongest(peaks)
                matches = [
                    p
                    for p in tested[rx]
                    if begin is not None and abs(m.wrap(cfo(p) - cfo(begin), m.FOLD_HZ)) < 1000
                ]
                got = strongest(matches)
                row = dict(
                    source=source,
                    edge=edge,
                    receiver=rx,
                    circular_delay_samples=shift,
                    counter=origin,
                    shifted_iq_sha256=stamp,
                    available=got is not None,
                    passed=None,
                )
                if got is not None:
                    before = epoch(begin)
                    after = epoch(got)
                    reported = m.wrap(after - before, period)
                    a = m.native_phase(origin, COUNTER, before, RATE)
                    b = m.native_phase(origin, COUNTER, after, RATE)
                    advanced = m.native_phase(origin - shift, COUNTER, after, RATE)
                    row.update(
                        native_integer_epoch=got["epoch"],
                        native_fractional_offset_samples=got["fractional_epoch"]["offset_samples"],
                        reported_epoch_delta_samples=reported,
                        fixed_counter_phase_delta_samples=m.wrap(b - a, period),
                        shifted_counter_phase_delta_samples=m.wrap(advanced - a, period),
                        folded_cfo_delta_hz=m.wrap(cfo(got) - cfo(begin), m.FOLD_HZ),
                        passed=abs(reported - shift) < 0.35,
                    )
                results.append(row)
    return results


def main():
    receipt = json.loads(BUILD.read_bytes())
    binary = Path(receipt["path"])
    digest = check(binary, receipt["sha256"])
    if receipt["wide_cfo_band_hz"] != [-800000, 800000]:
        raise ValueError("native sign test requires the exact compiled wide producer")
    plan = OUT / "native-origin-plan.json"
    save_json(
        plan,
        dict(
            code_sha256=_sha(Path(__file__)),
            parent_measurement_sha256=_sha(OUT / "measurement-lock.json"),
            library_receipt_sha256=_sha(BUILD),
            binary_sha256=digest,
            shifts=SHIFTS,
            planted_cases=["lower", "upper"],
            measured_case=dict(id=ACTUAL, segment=0, sequence=0),
            shift_tolerance_samples=0.35,
            templates={
                edge: [sha256(a.tobytes()).hexdigest() for a in templates(RATE, edge)]
                for edge in ("lower", "upper")
            },
        ),
    )
    rows = []
    for edge in ("lower", "upper"):
        planted = _test_signal(synthetic(RATE, edge), [(735, 157213, 6500)], 750)
        rows += measure(binary, planted, COUNTER + 137, "injected actual pilot template")
    source = _load_case(ACTUAL)
    (actual,) = _windows(source, 0, (0,))
    clock = actual.acquisition["sample_start"]
    rows += measure(binary, actual, clock, "first archived DS26-0036 window")
    file = OUT / "native-origin-results.json"
    save_json(
        file,
        dict(
            rows=rows,
            measured_native_iq_sha256=actual.iq_sha256,
            measured_segment_sha256=source["recording"]["segments"][0]["sha256"],
            matches=sum(r["passed"] is True for r in rows),
            attempted=len(rows),
        ),
    )
    save_json(OUT / "native-origin-lock.json", dict(files={x.name: _sha(x) for x in (plan, file)}))
    print("native sign checks", sum(r["passed"] is True for r in rows), len(rows), flush=True)


if __name__ == "__main__":
    main()
