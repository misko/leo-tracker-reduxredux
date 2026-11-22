"""Capture representative native-bound inputs from one frozen saved solve."""

import argparse
import json
import runpy
import sys
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch


def worker(native, spec, archive, offer, output):
    from tools.pipeline_eval.variants.experimental import lean_startup

    install = lean_startup.install
    measurements = defaultdict(lambda: dict(calls=0, cpu_ns=0, updates=0, max_updates=0))
    representative = {}

    with ExitStack() as stack:
        def install_then_capture():
            install()
            import numpy as np

            from leo.analysis.localization_v4.native_bound import NativeBound

            original = NativeBound.__call__

            def captured(self, raw, features, sigma, groups, **options):
                before = self.counts.copy()
                start = process_time_ns()
                result = original(self, raw, features, sigma, groups, **options)
                elapsed = process_time_ns() - start
                frame = sys._getframe(1)
                caller = Path(frame.f_code.co_filename).stem
                outcome, = [key for key, count in self.counts.items() if count > before[key]
                            and (key.startswith("fallback_") or key == "activated")]
                distinct = np.unique(groups)
                rows, columns = features.shape
                updates = result["precision_iterations"]
                if outcome == "fallback_unsupported":
                    support = np.array([np.any(features[groups == group] != 0, axis=0)
                                        for group in distinct])
                    widths = np.count_nonzero(support, axis=1)
                    private = support[:, np.count_nonzero(support, axis=0) == 1]
                    maximum = int(np.count_nonzero(private, axis=1).max())
                    if rows > 100000 or columns > 512 or len(distinct) > 2048:
                        outcome += "/input-size"
                    elif maximum > 2:
                        outcome += f"/private-width-{maximum}"
                    elif int(widths @ widths) > 2000000:
                        outcome += "/layout-memory"
                    else:
                        outcome += "/other"

                key = (outcome, caller, rows, columns, len(distinct))
                measured = measurements[key]
                measured["calls"] += 1
                measured["cpu_ns"] += elapsed
                measured["updates"] += updates
                measured["max_updates"] = max(measured["max_updates"], updates)
                if caller in ("position", "history_position") or outcome != "activated":
                    sample = (outcome, caller)
                    previous = representative.get(sample)
                    if previous is None or elapsed > previous[0]:
                        args = ("raw", "features", "sigma", "groups")
                        data = {key: np.array(value, copy=True) for key, value in
                                zip(args, (raw, features, sigma, groups), strict=True)}
                        data.update({key: np.array(value) for key, value in options.items()
                                     if value is not None})
                        representative[sample] = elapsed, data
                return result

            stack.enter_context(patch.object(NativeBound, "__call__", captured))

        stack.enter_context(patch.object(lean_startup, "install", install_then_capture))
        helper = Path(__file__).with_name("residual_attribution_trial.py")
        run = runpy.run_path(str(helper))["worker"]
        run(native, spec, archive, offer, output / "terminal.json", include_evidence=True)
    import numpy as np

    samples = {}
    for index, ((outcome, caller), (elapsed, data)) in enumerate(sorted(representative.items())):
        name = f"sample-{index:02}.npz"
        np.savez(output / name, **data)
        samples[name] = dict(outcome=outcome, caller=caller, cpu_ns=elapsed)
    groups = [dict(outcome=outcome, caller=caller, rows=rows, columns=columns, groups=groups,
                   **value) for (outcome, caller, rows, columns, groups), value in
              sorted(measurements.items())]
    with (output / "capture.json").open("x") as stream:
        json.dump(dict(groups=groups, samples=samples), stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "spec", "archive", "offer", "output"):
        parser.add_argument(name, type=Path)
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=False)
    worker(**vars(options))
