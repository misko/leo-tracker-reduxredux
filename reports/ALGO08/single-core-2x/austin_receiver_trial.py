"""Test the native two-scan receiver on an authenticated single-antenna field excerpt."""

import argparse
from contextlib import ExitStack
import gzip
import json
from pathlib import Path

import numpy as np

from residual_native_trial import ScheduledReceiver, bytes_fields
from tools.algo08_scan import PINS
from tools.pipeline_eval.qualification import austin_waveform as wave
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver


BINARIES = {"deployed": "f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809",
            "floating": "1b4c43dc1f2edc64ead9c4b9c0f4d724f79f623e04a13f40812a1d4bb40345a5",
            "integer": "c34c55748bd9b5feac6f1736e27acb78b4a1caa97f0d13a50b604cffd61d2d70"}
WIDE_REFERENCE_SHA256 = "b1777be4ff36dcddd099e794914574c76a84f744a57941d3781143b59a5e30c4"


def score(factors, target):
    if not factors:
        return dict(factors=0, signed_cfo_hz=None, phase_error_samples=None, within_tolerance=False)
    winner = max(factors, key=lambda f: (f[4]-f[5], -f[0]))
    error = None if target is None else wave.circular(winner[1]+winner[2]-target, wave.RATE/wave.FRAME_HZ)
    return dict(factors=len(factors), winning_rank=winner[0], signed_cfo_hz=winner[3],
                margin=winner[4]-winner[5], phase_error_samples=error,
                within_tolerance=error is not None and abs(error) <= wave.TIME_TOLERANCE_SAMPLES)


def run(archive, source_audit, wide_reference, assets, floating, integer):
    paths = dict(deployed=assets/"cancellation-factors.so", floating=floating, integer=integer)
    if {k: wave.digest(v.read_bytes()) for k, v in paths.items()} != BINARIES:
        raise ValueError("Detector binaries differ from the pinned release or research builds")
    reference = wide_reference.read_bytes()
    if wave.digest(reference) != WIDE_REFERENCE_SHA256:
        raise ValueError("Unexpected archived receiver input reference")
    records = [json.loads(line) for line in gzip.decompress(reference).splitlines()]
    bound_windows = {(r["edge"], r["panel"], r["start_ms"]): r["iq_sha256"]
                     for r in records if r["template"] == "exact"}
    raw, metadata, authority = wave.archive(archive, source_audit)
    measured = []
    for edge in wave.EDGE_HZ:
        pilot = assets/(edge+".f32")
        if wave.digest(pilot.read_bytes()) != PINS[pilot.name]:
            raise ValueError("Unexpected pilot asset")
        data = wave.extract_edge(raw, authority["actual_center_hz"], edge)
        template = np.fromfile(pilot, dtype="<f4")
        with ExitStack() as stack:
            radios = {k: (Receiver if k == "deployed" else ScheduledReceiver)(p, template)
                      for k, p in paths.items()}
            for radio in radios.values():
                stack.callback(radio.close)
            for start in (0, 20):
                index = start * wave.RATE // 1000
                window = data[index:index+wave.DWELL_SAMPLES]
                for panel, signal in (("physical", window), ("phase-null", wave.phase_null(window, wave.BASE_SEED+start))):
                    iq, _ = wave.ci16(signal)
                    digest = wave.digest(iq.tobytes())
                    if digest != bound_windows[edge, panel, start] or iq.shape != (200_000, 1, 2):
                        raise ValueError("Narrowband field input differs from the archived study")
                    stereo = np.zeros((200_000, 2, 2), dtype="<i2")
                    stereo[:, :1] = iq
                    results = {}
                    for name, radio in radios.items():
                        results[name+"_full"], _, _ = radio.timed(stereo, 0, 0)
                        if name != "deployed":
                            results[name+"_primary"], _, _ = radio.timed_primary(stereo, 0, 0)
                    measured.append(dict(edge=edge, panel=panel, start_ms=start, iq_sha256=digest, outputs=results))
    # Consult the authors' relative frame times after all native calls have returned.
    marks = wave.ordered_frames(metadata)
    for row in measured:
        start = row["start_ms"]/1000
        targets = [t for _, t in marks if start <= t and t+1/wave.FRAME_HZ <= start+.02]
        if not targets:
            raise ValueError("Expected published relative frame times in the selected window")
        target = (targets[0]-start)*wave.RATE if row["panel"] == "physical" else None
        outputs = row.pop("outputs")
        row["methods"] = {k: dict(score(f, target), ordered_factor_sha256=wave.digest(bytes_fields(f)))
                          for k, f in outputs.items()}
    return dict(archive_sha256=wave.ARCHIVE_SHA, archived_windows_sha256=WIDE_REFERENCE_SHA256,
                binaries=BINARIES, frame_tolerance_samples=wave.TIME_TOLERANCE_SAMPLES, rows=measured)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("archive", "source_audit", "wide_reference", "assets", "floating", "integer"):
        parser.add_argument(field, type=Path)
    print(json.dumps(run(**vars(parser.parse_args())), indent=2, allow_nan=False))
