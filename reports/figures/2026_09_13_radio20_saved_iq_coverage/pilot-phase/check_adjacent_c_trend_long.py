"""Production C trend replay; localized training remains offline diagnostic input."""

import ctypes as c
import json
from pathlib import Path
import subprocess
import numpy as np
from tests.starlink_glrt.test_tracking_trend import TrackingTrend
from tests.starlink_glrt.test_native_trend import Estimate
from tests.starlink_glrt.test_tracking_schedule import TrackingBatch, Job, oracle
from tests.starlink_glrt.test_tracking_solver import Moments, moments
from tests.starlink_glrt.test_native_solver import dense_fit
from validate_native_admission import rotated
from check_adjacent_c_validity import BASE, FW, RATE, digest


def main():
    source = BASE / "adjacent-c-validity-v1.json"
    prior = json.loads(source.read_text())
    manifest = json.loads((BASE / "missed-candidate-replay-v1/result.json").read_text())
    names = [
        "glrt_tracking_iq.c",
        "glrt_native_solver.c",
        "glrt_native_trend.c",
        "glrt_native_schedule.c",
        "glrt_tracking_schedule.c",
    ]
    binary = BASE / "adjacent-c-trend-long-v1.so"
    assert not binary.exists()
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            *[str(FW / "tools" / name) for name in names],
            "-lm",
            "-o",
            str(binary),
        ],
        check=True,
    )
    lib = c.CDLL(str(binary))
    ptr = c.POINTER(c.c_int16)
    lib.glrt_tracking_trend_reset.argtypes = [c.POINTER(TrackingTrend), c.c_uint32, c.c_uint32]
    lib.glrt_tracking_trend_observe.argtypes = [
        c.POINTER(TrackingTrend),
        c.c_uint32,
        c.c_uint32,
        c.c_uint64,
        c.c_uint32,
        c.POINTER(Estimate),
    ]
    lib.glrt_tracking_trend_batch.argtypes = [
        c.POINTER(TrackingTrend),
        c.c_uint32,
        c.c_uint32,
        c.c_uint32,
        c.c_uint32,
        c.POINTER(TrackingBatch),
        c.POINTER(c.c_double),
    ]
    lib.glrt_tracking_prediction.argtypes = [c.POINTER(TrackingBatch), c.c_uint, c.POINTER(Job)]
    lib.glrt_tracking_iq_moments_2500000.argtypes = [
        ptr,
        ptr,
        c.c_size_t,
        c.c_uint64,
        c.c_uint32,
        c.c_uint32,
        c.POINTER(Moments),
    ]
    lib.glrt_tracking_solve.argtypes = [
        c.c_uint32,
        c.c_uint32,
        c.POINTER(Moments),
        c.POINTER(Estimate),
    ]
    refs = np.fromfile(BASE / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4)
    result = dict(
        scope="production_C_trend_saved_positive_up_to_frame_1799",
        new_rf_samples=0,
        acceptance_gates_changed=False,
        native_tracking_qualified=False,
        training_localization_is_diagnostic=True,
        source_sha256=digest(Path(__file__)),
        prior_sha256=digest(source),
        binary_sha256=digest(binary),
        c_source_sha256={name: digest(FW / "tools" / name) for name in names},
        cases=[],
    )
    for old in prior["cases"]:
        case = next(r for r in manifest["cases"] if r["label"] == old["label"])
        path = BASE / "missed-candidate-replay-v1" / case["label"] / "iq.ci16"
        assert digest(path) == case["input_sha256"]
        if case["label"] == "positive":
            path = BASE / "paced-original-seed-input-v1/positive.ci16"
            assert (
                digest(path) == "af991e03e69271c253d2fe6b5aeff110c9da5d5bd6ddda8c6850584f9e97b1c4"
            )
        iq = np.fromfile(path, dtype="<i2").reshape(-1, 2)
        training = TrackingTrend()
        assert lib.glrt_tracking_trend_reset(c.byref(training), 1, RATE) == 0
        for r in old["localized"][:32]:
            estimate = Estimate(r["delay_s"], 0, r["cfo_hz"], r["coherence"], 0, r["rejection"])
            rc = lib.glrt_tracking_trend_observe(
                c.byref(training),
                1,
                r["frame"],
                r["start"],
                r["reference_phase"],
                c.byref(estimate),
            )
            assert rc == int(r["rejection"] == 0)
        for feedback in (False, True):
            trend = TrackingTrend.from_buffer_copy(bytes(training))
            rows = []
            for frame in range(32, 1800):
                batch = TrackingBatch()
                slope = c.c_double()
                job = Job()
                before = bytes(trend)
                rc = lib.glrt_tracking_trend_batch(
                    c.byref(trend), frame, 1, frame, 0, c.byref(batch), c.byref(slope)
                )
                assert bytes(trend) == before
                if rc:
                    rows.append(dict(frame=frame, batch_result=rc))
                    break
                assert lib.glrt_tracking_prediction(c.byref(batch), 0, c.byref(job)) == 0
                assert (job.start, job.phase_step, job.reference_phase) == oracle(batch, 0)
                cut = np.ascontiguousarray(iq[job.start : job.start + 3300])
                ref = np.ascontiguousarray(refs[job.reference_phase])
                data = Moments()
                estimate = Estimate()
                assert (
                    lib.glrt_tracking_iq_moments_2500000(
                        cut.ctypes.data_as(ptr),
                        ref.ctypes.data_as(ptr),
                        3300,
                        job.start,
                        0,
                        job.phase_step,
                        c.byref(data),
                    )
                    == 0
                )
                assert (
                    lib.glrt_tracking_solve(
                        RATE, job.reference_phase, c.byref(data), c.byref(estimate)
                    )
                    == 0
                )
                z = rotated(cut, 0, job.phase_step)
                assert list(data.words) == list(moments(z, ref.astype(np.int64)).words)
                raw = ref.astype(float)
                pilot = raw[:, 0] + 1j * raw[:, 1]
                basis = np.column_stack(
                    (
                        pilot,
                        -raw[:, 2] - 1j * raw[:, 3],
                        1j * np.pi * 1000 / RATE * (2 * np.arange(3300) - 3299) * pilot,
                    )
                )
                correction, coherence, _ = dense_fit(basis, z)
                np.testing.assert_allclose(
                    [estimate.delay * 1e6, estimate.residual / 1000],
                    np.clip(correction, -0.25, 0.25),
                    rtol=2e-10,
                    atol=2e-11,
                )
                np.testing.assert_allclose(estimate.coherence, coherence, rtol=2e-12, atol=2e-14)
                assert estimate.rejection == (
                    (32 if np.any(abs(correction) >= 0.25) else 0) | (64 if coherence < 0.05 else 0)
                )
                if feedback:
                    rc = lib.glrt_tracking_trend_observe(
                        c.byref(trend), 1, frame, job.start, job.reference_phase, c.byref(estimate)
                    )
                    assert rc == int(estimate.rejection == 0)
                rows.append(
                    dict(
                        frame=frame,
                        start=job.start,
                        phase=job.reference_phase,
                        step=job.phase_step,
                        cfo_rate_hz_s=slope.value,
                        coherence=estimate.coherence,
                        delay_s=estimate.delay,
                        cfo_hz=estimate.cfo,
                        rejection=estimate.rejection,
                        moments=list(data.words),
                    )
                )
            row = dict(
                label=case["label"],
                feedback=feedback,
                training_count=training.history.count,
                terminal_history_count=trend.history.count,
                measurements=rows,
                accepted=sum(r.get("rejection", -1) == 0 for r in rows),
            )
            result["cases"].append(row)
            print(
                case["label"],
                "feedback",
                feedback,
                "accepted",
                row["accepted"],
                "records",
                len(rows),
                flush=True,
            )
    with (BASE / "adjacent-c-trend-long-v1.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
