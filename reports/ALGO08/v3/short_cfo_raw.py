"""Opt in to the frozen fixed-epoch CFO refinement during signed raw acquisition."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
import runpy
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import mixed_aperture_receiver as mixed


LIBRARY_SHA256 = "fed887f464c78d9a547bd1d939dbb0a3987ab4babd3db8f0779928be5a6a1d4e"
EXTENSION_SHA256 = "82a9900ad8b7f643d6305f64e2723c131078dbd9f77c0788b84f0e1fea6de5a2"
POLICY_SHA256 = "55c693bc8e379665b43f16cb8831052dfcb096fbd12b89d8ae071f2178d46a15"
FREEZE_SHA256 = "efd70c2ee3739320067788d6feb7c7b6c77a8ee29285c2a61b4787eb28c34951"
STEP = 1.0
CFO = "fractional_tracking_cfo_hz"
FIELDS = ("candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples", CFO,
          "fractional_exact_score", "fractional_control_score")


def refined_probe(probe, waveform, full, policy, center):
    """Preserve the verifier's selected factor and diagnostics around its signed CFO."""
    (factor,) = probe["candidates"]
    original = (tuple(factor[key] for key in FIELDS),)
    diagnostic = policy.refiner.diagnostics(full, waveform, probe["receiver_id"], original)
    amended, reason = policy.amend(original, diagnostic, STEP, center)
    (previous,), (updated,) = original, amended
    if previous[:3] + previous[4:] != updated[:3] + updated[4:]:
        raise ValueError("Fixed-epoch CFO refinement changed another native factor field")
    if previous[3] == updated[3]:
        return probe, reason, False
    return dict(probe, candidates=[dict(factor, **{CFO: updated[3]})]), reason, True


class RefinedShortDetector(mixed.MixedApertureDetector):
    def __init__(self, short_binary, short_sha256, *, full_coverage, policy):
        if not full_coverage:
            raise ValueError("Fixed-epoch CFO refinement requires the original complete 20/12 ms schedule")
        super().__init__(short_binary, short_sha256, full_coverage=full_coverage)
        self.policy = policy
        self.lanes = {}
        self.cpu_ns = self.wall_ns = 0

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        import numpy as np

        full = None
        with super().detector(method, edge, binary=binary, pilot=pilot) as receive, ExitStack() as resource:
            def refined(window):
                nonlocal full
                old = self.visits["short_primary"]
                probes = receive(window)
                if self.visits["short_primary"] == old:
                    return probes
                target = window.target
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - window.acquisition["actual_if_center_hz"]
                for index, probe in enumerate(probes):
                    if not probe["candidates"]:
                        continue
                    start_cpu, start_wall = process_time_ns(), perf_counter_ns()
                    if full is None:
                        asset = np.frombuffer(mixed.verified(pilot, mixed.PILOT_SHA[edge]), dtype="<f4")
                        full = mixed.NativePath(binary, asset, "full")
                        resource.callback(full.close)
                    probes[index], reason, changed = refined_probe(probe, window.samples, full, self.policy, center)
                    counts = self.lanes.setdefault((edge, probe["receiver_id"]), Counter())
                    counts.update({"attempted": 1, "changed": int(changed), reason: 1})
                    self.cpu_ns += process_time_ns() - start_cpu
                    self.wall_ns += perf_counter_ns() - start_wall
                return probes

            yield refined

    def receipt(self):
        return super().receipt() | {"cfo_refinement": dict(cpu_ns=self.cpu_ns, wall_ns=self.wall_ns,
            lanes=[dict(edge=edge, receiver_id=lane, counts=dict(counts)) for (edge, lane), counts in sorted(self.lanes.items())])}


def recipe(original, parent):
    return original | {"fixed_epoch_cfo_refinement": dict(
        parent_detector_sha256="sha256:"+parent, wrapper_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        library_sha256=LIBRARY_SHA256, extension_sha256=EXTENSION_SHA256, policy_sha256=POLICY_SHA256,
        freeze_sha256=FREEZE_SHA256, step=STEP, support="positive short primaries in the original stereo window",
    )}


def run_cli(library, argv):
    from functools import partial
    from types import SimpleNamespace

    from leo.contracts.digests import canonical_digest
    from reports.ALGO08.v3 import short_cfo_refine as frozen
    import full_short_run

    incompatible = {"--held-anchor-route", "--short-lane-mask"}
    if any(option.split("=", 1)[0] in incompatible for option in argv):
        raise ValueError("Use the original unfiltered short-primary receiver for fixed-epoch CFO refinement")
    mixed.verified(library, LIBRARY_SHA256)
    mixed.verified(Path(frozen.__file__), POLICY_SHA256)
    mixed.verified(HERE/"short_cfo_refine.inc", EXTENSION_SHA256)
    policy = SimpleNamespace(refiner=frozen.Refine(library), amend=frozen.amend)
    parent = full_short_run.RECIPE_SHA
    receiver = recipe(full_short_run.checked_recipe(), parent)
    pin = canonical_digest(receiver).removeprefix("sha256:")
    bootstrap = HERE/"unified_short_bootstrap.py"
    with (patch.object(mixed, "MixedApertureDetector", partial(RefinedShortDetector, policy=policy)),
          patch.object(full_short_run, "checked_recipe", return_value=receiver),
          patch.object(full_short_run, "RECIPE_SHA", pin), patch.object(sys, "argv", [str(bootstrap), *argv])):
        runpy.run_path(str(bootstrap), run_name="__main__")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    cli.add_argument("--cfo-refinement-library", type=Path, required=True)
    args, inherited = cli.parse_known_args()
    run_cli(args.cfo_refinement_library, inherited)
