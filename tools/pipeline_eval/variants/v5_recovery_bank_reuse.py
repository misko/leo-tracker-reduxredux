"""Hand off one already validated causal recovery bank to final reassociation."""

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_lean

METHOD = "v5_recovery_bank_reuse"
BOUNDARY = "Complete compact v5 with one immutable causal recovery bank"


def ledger_key(records):
    return tuple((n, tuple(records[str(n)]["lines"])) for n in sorted(map(int, records)))


def grid_key(times):
    values = np.asarray(times)
    return values.shape, values.dtype, values.tobytes()


class RecoveryBank:
    """A single handoff within one scan. The ECEF bank owns immutable bytes."""

    def __init__(self):
        self.entry = None
        self.counts = dict(captured=0, reused=0, frozen_in_admission=0, retained_bytes=0)

    def capture(self, ledger, origin, knots, good, bank):
        usable = np.array(good, dtype=bool, copy=True)
        if usable.shape != (len(ledger),):
            raise ValueError("propagation eligibility does not match the ordered catalogue")
        if grid_key(bank["time_s"]) != grid_key(knots):
            raise ValueError("immutable residual bank has a different propagation grid")
        usable.setflags(write=False)
        self.entry = ledger, origin, grid_key(knots), usable, bank
        self.counts["captured"] += 1
        self.counts["retained_bytes"] = sum(
            bank[key].nbytes for key in ("time_s", "position_km", "velocity_km_s")
        )

    def take(self, records, origin, knots):
        saved, self.entry = self.entry, None
        if saved is None:
            return None
        ledger, original_origin, grid, good, bank = saved
        if original_origin != origin or grid_key(knots) != grid or ledger_key(records) != ledger:
            return None
        numbers = np.array([n for n, _ in ledger])
        self.counts["reused"] += 1
        return numbers[good], bank, numbers[~good].tolist()


@contextmanager
def reuse_recovery_bank():
    from leo.analysis.localization_v3 import (
        reassociation_admission,
        reassociation_catalogue,
        residual_screen,
    )

    handoff = RecoveryBank()
    residual = residual_screen.screen_candidates
    prepare = reassociation_admission.prepare_catalogue
    original_bank = reassociation_catalogue.bank_for
    frozen_bank = residual_screen.FrozenOrbitBank

    def screen(packet, catalogue, region, **kwargs):
        key = ledger_key(catalogue["elements"])
        states = residual_screen.ecef_states
        propagated = None

        def capture_states(cat, origin, knots):
            nonlocal propagated
            result = states(cat, origin, knots)
            if tuple(cat.satellite_numbers) == tuple(n for n, _ in key):
                propagated = origin, knots, result[2]
            return result

        def freeze(bank):
            immutable = frozen_bank(bank)
            if propagated is not None:
                handoff.capture(key, *propagated, immutable)
            return immutable

        with (
            patch.object(residual_screen, "ecef_states", capture_states),
            patch.object(residual_screen, "FrozenOrbitBank", freeze),
        ):
            return residual(packet, catalogue, region, **kwargs)

    def prepare_once(catalogue, scan_receipt):
        def bank_for(records, origin):
            cached = handoff.take(records, origin, reassociation_catalogue.GRID)
            return original_bank(records, origin) if cached is None else cached

        with patch.object(reassociation_catalogue, "bank_for", bank_for):
            prepared = prepare(catalogue, scan_receipt)
        bank = prepared["bank"]
        if prepared["eligible"] and not isinstance(bank, frozen_bank):
            prepared["bank"] = frozen_bank(bank)
            handoff.counts["frozen_in_admission"] += 1
        return prepared

    with (
        patch.object(residual_screen, "screen_candidates", screen),
        patch.object(reassociation_admission, "prepare_catalogue", prepare_once),
    ):
        yield handoff.counts


def worker(request, output, library):
    with reuse_recovery_bank() as counts:
        compact_finish.worker(request, output, library)
    output = Path(output)
    result = json.loads(output.read_bytes())
    result["boundary"] = BOUNDARY
    result["metrics"]["causal_bank_reuse"] = counts
    save_json(output, result)


def run(case, work_dir):
    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
