"""Shadow exact profiles at a geometry-selected subset of real observed epochs."""

from collections import Counter, defaultdict
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
STATES = {
    "dense": (Path("/dev/shm/leo-v3-catalogue-block-dense-pair01"),
              "4b6d07ea28051a4ac70030bd20f5da7e8f3bb8187dc84ea4b73fbbb6d04f94f5",
              "35089fce82d440548cebda8eb547f2fcf20b6120030f9480ce13615af3a951c5"),
    "medium": (Path("/dev/shm/leo-v3-catalogue-block-medium02"),
               "5979abd188cbd22c734b3be2fa7381a5c25152e69b07d30a60e2ee42db9503a0",
               "f8ed4fd43956ae5ae0deec09471a591bf1b68bb2f4bfcd0e386ba5cec6f985aa"),
}
TRAIN = 16
KEEP = 16
SIZES = (4, 8)


def geometry_epochs(times, rival_predictions):
    import numpy as np

    t = np.asarray(times, float)
    rivals = np.asarray(rival_predictions, float)
    if (t.ndim != 1 or len(t) < max(SIZES) or rivals.ndim != 2 or rivals.shape[0] < 1 or rivals.shape[1] != len(t)
            or not np.isfinite(rivals).all() or not np.isfinite(t).all() or np.any(np.diff(t) <= 0)):
        raise ValueError("Expected original ordered real epochs and finite rival predictions")
    center = rivals - rivals.mean(axis=1, keepdims=True)
    norms = np.sqrt(np.mean(center**2, axis=1, keepdims=True))
    unit = np.divide(center, norms, out=np.zeros_like(center), where=norms > 0.)
    features = np.column_stack(((t - t[0]) / (t[-1] - t[0]), unit.T / np.sqrt(len(rivals))))
    chosen, distance = [0], np.full(len(t), np.inf)
    for _ in range(1, max(SIZES)):
        distance = np.minimum(distance, np.sum((features - features[chosen[-1]])**2, axis=1))
        distance[chosen] = -np.inf
        chosen.append(int(np.argmax(distance)))
    return np.asarray(chosen)


def shortlist(cost, visible):
    import numpy as np

    elected = np.flatnonzero(visible)
    order = np.argsort(cost[elected], kind="stable")[:KEEP]
    return np.unique(np.r_[0, elected[order]])


def winner(cost, valid):
    import numpy as np

    if not valid.any():
        return 0
    return int(np.argmin(np.where(valid, cost, np.inf)))


def horizon_rows(elevations, rows, columns):
    import numpy as np
    from tools.pipeline_eval.variants.algo08_sparse_rank_projection import ProjectedRows

    if isinstance(elevations, ProjectedRows) and elevations.materialized is None:
        selected = elevations.base[np.ix_(rows, columns)]
        has_shift = np.isin(rows, elevations.changed_rows)
        shifts = np.searchsorted(elevations.changed_rows, rows[has_shift])
        selected[has_shift] = elevations.values[np.ix_(shifts, columns)]
    else:
        selected = elevations[np.ix_(rows, columns)]
    return (selected >= 0.).all(axis=1)


def planned_unresolved(y, predictions, sample, taken, taken_pred, sampled_visible, full_visible, exact, diagonal):
    import numpy as np
    from representative_contrast_bound import RELATIVE_MARGIN, centered_lower, incumbent_upper
    from leo.analysis.research.retained_track_likelihood import NOISE

    k = len(sample)
    offsets = np.arange(k // 2)
    scatter = centered_lower(y[sample], predictions, (offsets, (k - 1) - offsets))
    # Even the all-hidden stock fallback has row zero in the shortlist.
    omitted = sampled_visible.copy()
    omitted[taken] = False
    if not omitted.any():
        return 0
    if not full_visible.any():
        return int(omitted.sum())
    leader = winner(exact["cost"], full_visible)
    upper = incumbent_upper(y, taken_pred[leader], diagonal)
    if upper is None:
        return int(omitted.sum())
    cost_lower = scatter / NOISE**2 * (1 - RELATIVE_MARGIN)
    rms_impossible = scatter > len(y) * 450.**2 * (1 + RELATIVE_MARGIN)
    return int(np.count_nonzero(omitted & ~((cost_lower > upper) & rms_impossible)))


def prices(clock):
    replaced = clock["exact_stock_cpu_ns"]
    shadow = clock["domain_check_cpu_ns"] + clock["sparse_cpu_ns"] + clock["exact_shortlist_cpu_ns"] + clock["selection_cpu_ns"]
    return {"shadow_subset_plus_exact_cpu_ns": shadow,
            "oracle_net_cpu_ns": replaced - shadow - clock["oracle_replay_cpu_ns"],
            "conservative_net_cpu_ns": replaced - shadow - clock["conservative_replay_cpu_ns"] - clock["certificate_cpu_ns"]}


@contextmanager
def observe(scan, audit):
    import numpy as np
    from catalogue_block_bound_trial import SCAN_PIN, SPARSE_PIN, WHITE_PIN, read_checked
    from leo.analysis.localization_v3 import scan as kernel
    from leo.analysis.research import retained_track_likelihood as white
    from representative_contrast_bound import ERROR_HZ, support
    from tools.pipeline_eval.variants import algo08_sparse_rank_projection as sparse

    for module, digest in ((kernel, SCAN_PIN), (white, WHITE_PIN), (sparse, SPARSE_PIN)):
        read_checked(Path(module.__file__), digest)
    if kernel.profile is not white.profile or scan.curve.__func__ is not kernel.ScanLikelihood.curve:
        raise ValueError("The rank census requires the original exact white profile")
    original, predict = scan.curve, scan.predictions
    rank_order = np.argsort(scan.norads, kind="stable")
    training = rank_order[np.linspace(0, len(rank_order)-1, min(TRAIN, len(rank_order)), dtype=np.intp)]
    counts = defaultdict(Counter)
    exact_seen = set()
    available = defaultdict(set)
    sample_receipts = []
    phase = None

    def predictions(*args, **kwargs):
        nonlocal phase
        phase = predict(*args, **kwargs)
        return phase

    def curve(i, y, expected, method, **options):
        begin = process_time_ns()
        terms = original(i, y, expected, method, **options)
        stock_ns = process_time_ns() - begin
        audit["stock_calls"] = audit.get("stock_calls", 0) + 1
        audit["stock_curve_cpu_ns"] = audit.get("stock_curve_cpu_ns", 0) + stock_ns
        start = process_time_ns()
        track, indexes = scan.tracks[i], scan.index[i]
        if (phase is None or len(y) < 8 or options or method not in ("shared_phase", "receiver_smooth")
                or not support(scan, i, y, expected) or not np.isfinite(track["times"]).all()
                or np.any(np.diff(track["times"]) <= 0.)):
            audit["unsupported_calls"] = audit.get("unsupported_calls", 0) + 1
            return terms
        domain_ns = process_time_ns() - start
        elevations = phase[1]
        full_horizon = (elevations[:, indexes] >= 0.).all(axis=1)
        passing = terms["passing"] & full_horizon
        ungated = winner(terms["cost"], full_horizon)
        chosen = winner(terms["cost"], passing) if passing.any() else ungated
        required = passing.copy()
        required[ungated] = required[chosen] = True
        needed = np.flatnonzero(required)
        original_keys = {j: (track["key"], int(j), int(scan.norads[j]), int(terms["alias"][j])) for j in needed}
        exact_seen.update(original_keys.values())
        start = process_time_ns()
        nested = geometry_epochs(track["times"], expected[training])
        select_ns = process_time_ns() - start
        if len(sample_receipts) < 3:
            sample_receipts.append(dict(component=track["key"], times_s=track["times"].tolist(), selected_rows=nested.tolist()))
        for kind, size in ((kind, size) for kind in ("geometry", "uniform") for size in SIZES):
            tally = counts[kind, size]
            begin = process_time_ns()
            sample = (np.sort(nested[:size]) if kind == "geometry"
                      else np.linspace(0, len(y)-1, size, dtype=np.intp))
            sparse_cfo = expected[:, sample]
            visible = (elevations[:, indexes[sample]] >= 0.).all(axis=1)
            proxy = white.profile(y[sample], sparse_cfo, np.eye(size) / white.NOISE)
            taken = shortlist(proxy["cost"], visible)
            tally["sparse_cpu_ns"] += process_time_ns() - begin
            kept = np.zeros(len(expected), bool)
            kept[taken] = True
            misses = int(np.count_nonzero(~kept[needed]))
            tally.update(calls=1, exact_stock_cpu_ns=stock_ns, domain_check_cpu_ns=domain_ns, stock_cells=expected.size,
                         sample_cells=len(expected)*size, shortlisted=len(taken), compatible=int(passing.sum()),
                         compatible_dropped=int(np.count_nonzero(passing & ~kept)), any_required_missed=int(misses > 0),
                         misses_ungated=int(not kept[ungated]), misses_chosen=int(not kept[chosen]),
                         exact_visible=int(full_horizon.sum()), sparse_false_visible=int((visible & ~full_horizon).sum()),
                         shortlisted_false_visible=int((visible & ~full_horizon & kept).sum()),
                         shortlisted_alias_changed=int(np.count_nonzero(proxy["alias"][taken] != terms["alias"][taken])),
                         chosen_sparse_alias_changed=int(proxy["alias"][chosen] != terms["alias"][chosen]),
                         alias_halfway_close=int(np.count_nonzero(np.abs(np.abs(-(y[sample]-sparse_cfo).mean(axis=1)
                             / white.PERIOD - proxy["alias"]) - .5) <= ERROR_HZ/white.PERIOD)),
                         oracle_replay_cpu_ns=stock_ns if misses else 0)
            available[kind, size].update(key for j, key in original_keys.items() if kept[j])
            if kind != "geometry":
                continue
            tally["selection_cpu_ns"] += select_ns
            start = process_time_ns()
            subset_full = expected[taken]
            if expected.flags.f_contiguous:
                subset_full = np.asfortranarray(subset_full)
            exact = original(i, y, subset_full, method)
            full_visible = horizon_rows(elevations, taken, indexes)
            actual_valid = full_visible & exact["passing"]
            full_nominee = taken[winner(exact["cost"], full_visible)]
            full_winner = taken[winner(exact["cost"], actual_valid)] if actual_valid.any() else full_nominee
            tally["exact_shortlist_cpu_ns"] += process_time_ns() - start
            tally["exact_shortlist_cells"] += subset_full.size
            if not np.array_equal(full_visible, full_horizon[taken]):
                raise ValueError("Compact horizon does not match the original all-epoch horizon")
            start = process_time_ns()
            unresolved = planned_unresolved(y, sparse_cfo, sample, taken, subset_full, visible, full_visible, exact,
                                            np.diag(scan.white[i][0]))
            proof_ns = process_time_ns() - start
            parity = all(np.array_equal(exact[field], terms[field][taken]) for field in (
                "rms", "bias", "cost", "alias", "passing", "residual", "innovations"))
            tally.update(certificate_cpu_ns=proof_ns, conservative_unresolved_rows=unresolved,
                         exact_rerank_misses_chosen=int(full_winner != chosen), exact_rerank_misses_ungated=int(full_nominee != ungated),
                         compact_diagnostics_differ=int(not parity))
            if not unresolved and misses:
                raise ValueError("Conservative sampled proof discarded a required full observation rival")
            if unresolved or not parity:
                tally.update(conservative_fallback_calls=1, conservative_replay_cpu_ns=stock_ns)
        return terms

    with patch.object(scan, "predictions", predictions), patch.object(scan, "curve", curve):
        yield
    audit.update(training_norads=scan.norads[training].tolist(), epochs=sample_receipts,
                 methods=[dict(method=name, epochs=size, totals=dict(rows),
                               **(prices(rows) if name == "geometry" else {})) for (name, size), rows in counts.items()])
    # The enclosing pinned validator checks the held ordered finalist signatures.
    audit["available"] = (exact_seen, available)


def worker(case, root):
    import catalogue_block_bound_trial as base

    archived, request_pin, binding_pin = STATES[case]
    request_file = archived / "request.json"
    request = json.loads(base.read_checked(request_file, request_pin))
    binding = json.loads(base.read_checked(archived / "binding.json", binding_pin))
    inventory = Path(binding["inventory"])
    base.read_checked(inventory, request["inventory"][7:])
    for raw_path in (Path(request["local_archive"]["root"]), Path(request["native_file"]), inventory):
        if not raw_path.resolve(strict=True).is_relative_to(Path("/dev/shm")):
            raise ValueError("This rank-only audit requires local recorded inputs")
    control = json.loads(base.read_checked(base.BASE/(case+"-control")/"result.json", base.BASELINES[case]))
    signatures = control["stages"]["work"]["ordered"]

    @contextmanager
    def record(scan, audit):
        with observe(scan, audit):
            yield
        exact_seen, available = audit.pop("available")
        def witness(members):
            return [dict(rows=len(rows), witnessed=sum(tuple(row) in members for row in rows)) for rows in signatures]

        audit.update(ranks_seen_in_exact_tape=witness(exact_seen),
                     ranks_seen_in_each_shortlist_tape={f"{kind}{size}": witness(rows)
                                                       for (kind, size), rows in available.items()},
                     archived_request_sha256=request_pin, archived_binding_sha256=binding_pin, original_raw_reads=0)

    with patch.object(base, "observe_curves", record):
        base.worker(case, request_file, inventory, root)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    worker(sys.argv[1], Path(sys.argv[2]))
