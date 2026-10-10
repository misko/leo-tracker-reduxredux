import numpy as np

from leo.storage.short_window import ShortWindowWriter

TARGET = dict(
    target_id="ch1",
    channel=1,
    edge="lower",
    rf_center_hz=10709687500,
    lnb_lo_hz=9750000000,
    rf_mapping_authority="hypothesis",
)


def recording(root, *, count=3, rate=2500000, generation_change=False):
    writer = ShortWindowWriter(
        root,
        "segment",
        configuration={"sample_rate_hz": rate, "window_ms": 20, "targets": [TARGET]},
        radio={"serial": "synthetic"},
        receiver_ids=(0, 1),
    )
    for visit in range(count):
        samples = np.zeros((50000, 2, 2), dtype="<i2")
        samples[:, 0, 0] = visit
        writer.append(
            sequence=visit,
            target_id="ch1",
            samples=samples,
            powers=({}, {}),
            acquisition={
                "global_visit": visit,
                "sample_start": visit * 100000,
                "sample_end": visit * 100000 + 50000,
                "generation": int(generation_change and visit > 0),
                "actual_if_center_hz": 959687500,
                "complete": True,
                "validity_authority": "provider_attested",
                "validity_includes_guard": True,
                "quality_flags": [],
            },
        )
    return writer.finish(stop_reason="max_visits")


class Predictor:
    def score_ci16(self, samples):
        visit = int(samples[0, 0, 0])
        return [
            dict(
                margin=0.02 if visit and rx == 1 else 0.001,
                exact=0.03,
                control=0.01,
                epoch_sample=0,
            )
            for rx in range(2)
        ]


def predictor(edge, receivers):
    return Predictor()


def detector(window, receivers):
    from leo.contracts.fast_scan import FastScanReceiverV1

    return tuple(FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in receivers)
