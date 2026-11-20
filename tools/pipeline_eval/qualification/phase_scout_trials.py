"""Measure adaptive phase masks against the authentic full sixteen-center detector."""

import argparse
import json
import os
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryFile
from time import perf_counter, process_time
from unittest.mock import patch

from ..__main__ import ROOT, local_output, save_json, write
from ..variants import iq_stream, phase_scout
from . import ordinary_front_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _load_case, _sha
from .pilot_kernel_eval import _windows
from .portable_gate_trials import compressed_rows
from .wide_regional_eval import CHUNK_PREFIX, synthetic, templates

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support/phase-scout"
SCHEDULE = ((2, (14, 18, 22, 26)), (7, (14, 18, 22, 26)))
CASES = ("DS26-0036", "DS29-0082")
SIGNALS = ((760111, 1900), (357121, 1900), (794991, 1900), (64123, 705), (201333, 400), (0, 0))
MODES = ("stock", "candidate")
RATE = 10_000_000


def traces(call, directory):
    with (
        TemporaryFile(dir=directory) as output,
        patch.dict(os.environ, {"LEO_PHASE_SCOUT_TRACE": "1"}),
    ):
        saved = os.dup(2)
        try:
            os.dup2(output.fileno(), 2)
            call()
        finally:
            os.dup2(saved, 2)
            os.close(saved)
        output.seek(0)
        rows = [line.decode().split()[1:] for line in output if line.startswith(b"phase-scout ")]
    return [
        dict(
            receiver=int(rx),
            rank=int(rank),
            epoch=int(epoch),
            mask=int(mask),
            cfo_hz=list(map(float, (a, b, c))),
            coherence=list(map(float, (d, e, f))),
        )
        for rx, rank, epoch, mask, a, b, c, d, e, f in rows
    ]


def replay(work, release):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    contexts = {}
    with ExitStack() as stack:
        inputs = []
        for ident in CASES:
            case = _load_case(ident)
            for segment, sequences in SCHEDULE:
                with patch.object(iq_stream, "MAX_CHUNK_PREFIX", CHUNK_PREFIX):
                    windows = _windows(case, segment, sequences)
                for window in windows:
                    inputs.append(
                        (
                            window,
                            dict(
                                id=ident,
                                condition="recorded",
                                segment=segment,
                                visit=window.acquisition["global_visit"],
                                sequence=window.sequence,
                                channel=window.target["channel"],
                                native_sha256=case["native"]["sha256"],
                                segment_sha256=case["recording"]["segments"][segment]["sha256"],
                            ),
                        )
                    )
        for edge in ("lower", "upper"):
            for j, (f, amplitude) in enumerate(SIGNALS):
                hz = f * (-1 if (edge == "upper") != bool(j % 2) else 1)
                condition = "null" if not amplitude else "weak" if amplitude < 1000 else "planted"
                signal = [(735, hz, amplitude)] if amplitude else []
                scene = _test_signal(
                    synthetic(RATE, edge), signal, 667201 + 37 * j + (edge == "upper")
                )
                inputs.append(
                    (
                        scene,
                        dict(
                            id=f"{edge}-{j}",
                            condition=condition,
                            plant_hz=hz,
                            planted_epoch=735,
                            amplitude=amplitude,
                        ),
                    )
                )
        public = [
            dict(
                label,
                edge=w.target["edge"],
                iq_sha256=w.iq_sha256,
                receiver_count=len(w.receiver_ids),
                samples=len(w.samples),
            )
            for w, label in inputs
        ]
        save_json(
            REPORT / "plan.json",
            dict(
                design=_sha(REPORT / "PROTOCOL.md"),
                source=_sha(Path(__file__)),
                overlay=_sha(Path(phase_scout.__file__)),
                header=_sha(phase_scout.HEADER),
                build=release,
                inputs=public,
                repeats=2,
                cpus=sorted(os.sched_getaffinity(0)),
            ),
        )
        for i, ((window, _label), authority) in enumerate(zip(inputs, public, strict=True)):
            rate, edge, receivers = (
                window.sample_rate_hz,
                window.target["edge"],
                len(window.receiver_ids),
            )
            assert rate == RATE and receivers in (1, 2)
            if (edge, receivers) not in contexts:
                pair = templates(rate, edge)
                contexts[edge, receivers] = {
                    mode: stack.enter_context(
                        NativeShortWindow(
                            release[mode],
                            *pair,
                            sample_rate_hz=rate,
                            receiver_count=receivers,
                            fractional_epoch=True,
                        )
                    )
                    for mode in MODES
                }
            variants = contexts[edge, receivers]

            def call(samples, mode, variants=variants):
                wall, cpu = perf_counter(), process_time()
                out = variants[mode].analyze(samples, include_timings=True)
                return out, dict(wall_s=perf_counter() - wall, host_cpu_s=process_time() - cpu)

            with patch.object(ordinary_front_eval, "MODES", MODES):
                result = ordinary_front_eval.benchmark(window.samples, call, i, 2)
            assert result["stable"]
            trace = traces(lambda samples=window.samples: call(samples, "candidate"), work)
            assert len(trace) <= 32 and all(0 < t["mask"] < 2**21 for t in trace)
            print(
                authority["id"],
                authority.get("visit"),
                sum(t["mask"] != 2**21 - 1 for t in trace),
                result["exact"],
                flush=True,
            )
            yield dict(authority, **result, scout=trace)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = local_output(args.work)
    release = json.loads((work / "build.json").read_bytes())
    for mode in MODES:
        if _sha(Path(release[mode])) != release[mode + "_sha256"]:
            raise ValueError("scout trial library differs from its receipt")
    rows = list(replay(work, release))
    raw = REPORT / "predictions.jsonl.gz"
    write(raw, compressed_rows(rows))
    save_json(
        REPORT / "prediction-lock.json",
        dict(files={p.name: _sha(p) for p in (raw, REPORT / "plan.json")}, attempts=len(rows)),
    )


if __name__ == "__main__":
    main()
