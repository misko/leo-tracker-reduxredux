"""Synthetic signed and guard checks off the shared timing CPU."""

from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import json
import os
from pathlib import Path
import runpy
import sys

from .short_shared_integer_phase import CheckedReceiver, Event, compare, native_bytes
from .sparse8_native_profile import Factor, PILOTS, RELEASE, TRAINER, TRAIN_ROOT, checked


def main(root):
    if os.sched_getaffinity(0) != {3} or os.nice(0) < 15:
        raise ValueError("Use low-priority CPU3 for synthetic checks")
    trainer = TRAIN_ROOT/"reports/ALGO08/single-core-2x/receiver_mixer_profile_trial.py"
    checked(trainer, TRAINER)
    sys.path.insert(0, str(trainer.parent))
    train = runpy.run_path(str(trainer))
    waveform = train["waveform"]
    frames, maxima, counts = waveform.pulse_bank(), [0., 0.], Counter()
    with ExitStack() as stack:
        radio = {}
        for index, (edge, record) in enumerate(train["compiler"].training_rows()):
            iq = waveform.iq(record, {"sample_rate_truth_hz": waveform.RATE}, frames[edge])
            if edge not in radio:
                paths = "installed", "exact", "shared"
                pilot = ct.create_string_buffer(checked(RELEASE/"assets"/(edge+".f32"), PILOTS[edge]))
                radio[edge] = {name: CheckedReceiver(root/(name+".so"), pilot, name != "installed") for name in paths}
                for receiver in radio[edge].values():
                    stack.callback(receiver.close)
            for center in train["mixer_centers"](index):
                for lane in (0, 1):
                    stock, exact, shared = (receiver.checked_call(iq.ctypes.data, lane, center)
                                            for receiver in radio[edge].values())
                    if native_bytes(stock[0], Factor) != native_bytes(exact[0], Factor):
                        raise ValueError("The rebuilt verifier differs from the released detector")
                    errors = compare(exact[0], shared[0], 4)
                    compare(exact[1], shared[1], 5)
                    if not shared[2][1] and native_bytes(exact[1], Event) != native_bytes(shared[1], Event):
                        raise ValueError("An exact synthetic fallback changed its verifier output")
                    if errors:
                        maxima = [max(x, y) for x, y in zip(maxima, errors, strict=True)]
                    counts.update(lanes=1, positives=bool(exact[0]), attempted=shared[2][0], accepted=shared[2][1])
        guard = radio["lower"]["shared"].lib.shared_phase_safe
        guard.argtypes, guard.restype = (ct.c_double,)*5, ct.c_int
        checks = dict(clear=bool(guard(.15, .2, .2, 1e-6, 1e-6)),
                      factor_margin=not guard(.025, .2, .2, 1e-6, 1e-6),
                      strong_margin=not guard(.1, .2, .2, 1e-6, 1e-6),
                      bin_tie=not guard(.15, 1e-6, .2, 1e-6, 1e-6),
                      unusable=not guard(.15, .2, .2, float("inf"), 1e-6))
        if not all(checks.values()):
            raise ValueError("An unsafe spectrum passed the guard")
    return dict(instrumented_training_counts=counts, max_native_continuous_errors=maxima, guard=checks)


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), sort_keys=True))
