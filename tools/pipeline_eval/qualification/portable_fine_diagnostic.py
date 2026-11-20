"""Explain the extra guarded conditioned acquisition on DS29-0519 visit 153."""

import argparse
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants import conditioned_cfo_bank, fine_search, portable_fine, prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import capture_exact_trial as exact
from . import original_kernel_trial as original
from . import prepared_hotpath_trial as prepared
from .full_v5_check import _load_case, _sha
from .portable_fine_fixture import REPORT, parent_lock
from .portable_fine_host import compare


def diagnose(library, output):
    from leo.analysis.starlink import acquisition

    ident, visit = "DS29-0519", 153
    parent = parent_lock()
    cfg = parent["cases"][ident]
    if not Path(acquisition.__file__).is_relative_to(cfg["root"]):
        raise ValueError("diagnosis must run inside the authenticated producer")
    libraries = {
        name: whole_iq.checked(Path(info["path"]), info["sha256"])
        for name, info in parent["libs"].items()
    }
    parent_class = conditioned_cfo_bank.ConditionedBank
    built = []

    def capture_bank(*args, **kwargs):
        bank = parent_class(*args, **kwargs)
        built.append(bank)
        return bank

    grid = PersistentGrid(libraries["prepared"])
    fallback = fine_search.FineSearch(libraries["fine"], acquisition)
    fine = portable_fine.PortableFine(library, acquisition, fallback.score)
    case = _load_case(ident)
    _, policy, _ = exact.lineage.source_lineage(case)
    _, _, window = original.decode(case, visit)
    locked = next(row for row in cfg["rows"] if row["visit"] == visit)
    if window.iq_sha256 != locked["iq_sha256"]:
        raise ValueError("diagnostic input changed from the authenticated panel")
    outcomes, signatures, deltas = {}, [], Counter()
    try:
        for label, route in (("installed", nullcontext), ("portable", fine.route)):
            with (
                patch.object(conditioned_cfo_bank, "ConditionedBank", capture_bank),
                exact.refiners(libraries),
                grid.route(acquisition, exact.starts.screen_module()),
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                ),
                route(),
            ):
                packet, _ = prepared.sample(window, policy)
            signatures.append(packet)
            paths = Counter(r["fallback"] or "bounded" for r in built[-1].receipts)
            outcomes[label] = dict(
                conditioned_calls=len(built[-1].receipts),
                conditioned_paths=dict(paths),
                equivalent_ties=built[-1].equivalent_ties,
            )
    finally:
        grid.clear_cache()
    compare(*signatures, deltas)
    save_json(
        output,
        dict(
            case=ident,
            visit=visit,
            source_iq_sha256=window.iq_sha256,
            waveform_manifest_sha256=_sha(REPORT / "manifest.json"),
            paths=outcomes,
            fine_c_calls=fine.calls,
            fine_c_guarded=fine.guarded,
            max_absolute_float_delta_by_field=dict(deltas),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("output", type=local_output)
    args = parser.parse_args()
    diagnose(args.library, args.output)
