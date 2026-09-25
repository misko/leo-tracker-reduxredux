"""Bounded, read-only replay; writes JSON lines only to stdout.

Run with the production release's Python as the storage service user.
No RF acquisition, persisted IQ changes, or production configuration writes.
"""

import json
from pathlib import Path
import time

import numpy as np

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_scores, refine_glrt64_epochs
from leo.contracts.starlink_frequency import (
    STARLINK_LNB_LO_HZ,
    starlink_edge_if_center_frequency_hz,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def score(values, rate, edge, center, halfwidth, count=8):
    started = time.monotonic()
    config = SymbolwiseAcquisitionConfig(
        maximum_probe_samples=len(values),
        retained_candidate_count=count,
        candidate_epoch_separation_samples=5,
        candidate_cfo_separation_hz=10000,
        residual_cfo_min_hz=-halfwidth,
        residual_cfo_max_hz=halfwidth,
    )
    acquired = acquire_symbolwise(
        values,
        rate,
        ReceiverFrequencyCalibration("replay", center, "0" * 64),
        edge=edge,
        config=config,
    )
    candidates = acquired.candidates
    epochs = tuple(c.refined_epoch_sample for c in candidates)
    frequencies = tuple(c.absolute_cfo_hz for c in candidates)
    integers = conditioned_glrt64_scores(
        values, rate, epoch_samples=epochs, acquired_cfo_hz=frequencies, edge=edge
    )
    fractional = refine_glrt64_epochs(
        values,
        rate,
        integer_epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=edge,
        expected_integer_scores=integers,
    )
    rows = [
        dict(
            epoch=c.refined_epoch_sample,
            acquired_cfo=c.absolute_cfo_hz,
            integer_margin=i.margin,
            fractional_margin=f.fractional_margin,
            status=f.status.value,
            tracking_cfo=f.fractional_tracking_cfo_hz,
        )
        for c, i, f in zip(candidates, integers, fractional)
    ]
    rows.sort(
        key=lambda r: r["fractional_margin"] if r["fractional_margin"] is not None else -1,
        reverse=True,
    )
    return dict(seconds=time.monotonic() - started, top=rows[:3])


def main():
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        for sid, requested in [
            ("scan-fw-4fd51c7c4c1a0273", [706, 806]),
            ("scan-fw-84ded59806e73af6", [705, 707]),
        ]:
            with AdaptiveHopAnalysisInputStore(store).source(sid) as source:
                geometry = source.receipt.plan.geometry
                rate = geometry.sample_rate_hz
                visits = list(requested)
                if rate == 10000000:
                    visits += [
                        next(
                            i
                            for i in range(807, len(source.visits))
                            if source.visits[i].event.target.channel == 1
                            and source.visits[i].event.target.edge.value == "lower"
                        )
                    ]
                for visit in visits:
                    event = source.visits[visit].event
                    x = source.read_visit(visit)[: round(rate * 0.020)].copy()
                    masked = []
                    for index in np.flatnonzero(np.max(np.abs(x), axis=1) > 2048):
                        row = x[index]
                        words = np.array(
                            [row[0].real, row[0].imag, row[1].real, row[1].imag], dtype="<i2"
                        )
                        counter = int(words.view("<u8")[0])
                        if counter == event.valid_start_counter + int(index) + 2:
                            x[index] = 0
                            masked.append(int(index))
                    # Actual LO is the physical IQ reference, not the requested target.
                    nominal = starlink_edge_if_center_frequency_hz(
                        event.target.channel, event.target.edge
                    )
                    nominal += STARLINK_LNB_LO_HZ - geometry.lnb_lo_hz
                    center = nominal - event.actual_lo_frequency_hz
                    for rx in range(2):
                        for mode, reference, width in [
                            ("baseline", 0, 400000),
                            ("tuning_only", center, 400000),
                            ("tuning_wide", center, 800000),
                        ]:
                            # Wider trial remains blind; no receiver/epoch fitted to the examples.
                            result = score(x[:, rx], rate, event.target.edge, reference, width)
                            print(
                                json.dumps(
                                    dict(
                                        session=sid,
                                        visit=visit,
                                        rate=rate,
                                        rx=rx,
                                        mode=mode,
                                        center=reference,
                                        halfwidth=width,
                                        masked=masked,
                                        candidates=8,
                                        **result,
                                    )
                                ),
                                flush=True,
                            )
                    if rate == 10000000 and visit == 806:
                        for count in (32, 64, 128):
                            result = score(x[:, 0], rate, event.target.edge, center, 800000, count)
                            print(
                                json.dumps(
                                    dict(
                                        session=sid,
                                        visit=visit,
                                        rate=rate,
                                        rx=0,
                                        mode="budget_sweep",
                                        center=center,
                                        halfwidth=800000,
                                        masked=masked,
                                        candidates=count,
                                        **result,
                                    )
                                ),
                                flush=True,
                            )
    finally:
        store.close()


if __name__ == "__main__":
    main()
