"""Cross saved visit coverage and native winner choice with one signed route."""

import argparse
from functools import partial
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from aperture_trial import ARMS, read, write
from full_family_amortized_trial import SHARED_RANK, run as fit
from mixed_aperture_availability import CONTROL_SHA, MODE as OLD_REDUCED_PRIMARY, select
from mixed_stereo_paid import checked_exterior
from paid_certified_trial import GRAPH, PAIRED_FIELDS, check_binding, sealed
from paid_graph_trial import prepare_paid
from sparse_consensus_trial import CASES, bound_inputs


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
AVAILABILITY_SHA = "55a2a50b7025b39eff4f243e3eae972a64f8f24f838e7779c386a030de9b345f"
SHORT_CPU_S = {"dense": .0010733641875, "weak": .001734976}
FACTORS = {"all-both": (True, True), "reduced-both": (False, True),
           "all-primary": (True, False), "reduced-primary": (False, False)}
CONTAINING = CASES[:2]


def sealed_runs(name, pin):
    blob = (MEASUREMENTS / (name + ".json.gz")).read_bytes()
    if sha256(blob).hexdigest() != pin:
        raise ValueError(f"The archived {name} receipts changed")
    return json.loads(gzip.decompress(blob))


def prepare(case, mode):
    from leo.contracts.digests import canonical_digest

    native, rows, _, clocks, archive, offer, identity = bound_inputs(case)
    complete = canonical_digest(native)
    identity.update(native_sha256=complete)
    check_binding(identity, sealed("complete")[case]["complete"]["identity"], "complete")
    all_times, all_ranks = FACTORS[mode]
    selector_start = process_time()
    native, _, stats = prepare_paid(native, rows, clocks, identity, mode, select_paid=partial(
        select, all_times=all_times, all_ranks=all_ranks))
    stats["charged_selection_cpu_s"] = process_time() - selector_start
    identity.update(mode=mode, graph_parameters=GRAPH, selection=stats,
                    complete_native_sha256=complete, native_sha256=canonical_digest(native),
                    all_native_cpu_s=sum(clocks) / 1e9)
    return native, archive, offer, identity, True


def reuse_reduced_primary(case, identity):
    archived = sealed_runs("mixed-aperture-availability", AVAILABILITY_SHA)[case]
    previous = archived["identity"]
    if (previous["mode"] != OLD_REDUCED_PRIMARY or archived["mode"] != "control" or not archived["single_attempt"]
            or len(archived["attempts"]) != 1 or previous["selection"]["mask_sha256"] != identity["selection"]["mask_sha256"]
            or any(previous[k] != identity[k] for k in (*PAIRED_FIELDS, "complete_native_sha256", "native_sha256",
                                                       "graph_parameters", "all_native_cpu_s"))):
        raise ValueError("Archived reduced-primary input and solver graph differ")
    for name, digest in archived["source_sha256"].items():
        source = SHARED_RANK if name == SHARED_RANK.name else HERE / name
        if sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("Archived reduced-primary solver sources changed")
    return dict(archived, identity=identity, reuse=dict(archive_sha256=AVAILABILITY_SHA, prior_identity=previous))


def run(case, mode, output, *, gate=None):
    from aperture_trial import configuration, machine

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared Gauss slot with one numerical thread")
    if case not in CONTAINING and (gate is None or read(gate)["advance_missing_mode"] != mode):
        raise ValueError("The missing-region extension requires the prespecified containing gate")
    if mode == "reduced-primary":
        configuration()
        _, _, _, identity, _ = prepare(case, mode)
        write(output, reuse_reduced_primary(case, identity))
    else:
        fit(case, "control", output, load_saved_inputs=partial(prepare, mode=mode), single_attempt=True)


def charge(row, matched, prior):
    identity = row["identity"]
    selection = identity["selection"]
    acquisition = identity["ledger"]["acquisition_cpu_s"]
    outside = acquisition - identity["all_native_cpu_s"]
    lower = outside + row["cpu_s"]
    full = selection["full_call_cpu_s_by_slot"].get("full", 0.)
    floor = lower + full + selection["charged_selection_cpu_s"]
    primary = selection["counts"].get("primary", 0)
    targets = {key: (acquisition + comparator["cpu_s"]) / 2
               for key, comparator in (("matched", matched), ("prior", prior))}
    projected = {panel: floor + primary * rate for panel, rate in SHORT_CPU_S.items()}
    return dict(outside_native_cpu_s=outside, measured_full_slot_cpu_s=full, short_primary_lanes=primary,
                free_all_native_and_selector_floor_cpu_s=lower, zero_short_floor_cpu_s=floor,
                projected_cpu_s=projected, targets_cpu_s=targets,
                maximum_short_cpu_ms_per_lane=None if not primary else 1000 * (min(targets.values())-floor)/primary,
                passes_dense_projection=projected["dense"] <= min(targets.values()))


def position_passes(result, comparisons):
    deltas = [comparison["arms"][arm]["delta_error_km"] for comparison in comparisons for arm in ARMS]
    return result["status"] == "ok" and all(delta is not None and delta <= .25 for delta in deltas)


def compare(row, matched, prior, truth):
    from mixture_score import section
    from signed_0374_transfer import owner_changes

    evidence = row["attempts"][0]
    by_authority = {key: section(row["arms"], truth, baseline["arms"])
                    for key, baseline in (("matched", matched), ("prior", prior))}
    return dict(status=row["status"], reason=row["reason"], route=evidence["decision"],
                contract_exterior=checked_exterior(row), scores=by_authority,
                passes_position=position_passes(row, by_authority.values()),
                owners=owner_changes(matched, row), owners_vs_prior=owner_changes(prior, row),
                selection=row["identity"]["selection"], prepared=row["prepared"], native_sha256=row["identity"]["native_sha256"],
                solver_cpu_s=row["cpu_s"], solver_elapsed_s=row["elapsed_s"],
                fallback_cpu_s=evidence.get("fallback_clocks", {}).get("cpu_s", 0.),
                charge=charge(row, matched, prior), reused=bool(row.get("reuse")))


def score(directory, summary, archive):
    from aperture_score import PHYSICAL, SIMULATED, references

    paths = {case: {mode: directory / f"{case}-{mode}.json" for mode in FACTORS} for case in CONTAINING}
    rows = {case: {mode: read(path) for mode, path in modes.items()} for case, modes in paths.items()}
    earlier = sealed_runs("mixed-stereo-paid", CONTROL_SHA)["runs"]
    for case, cells in rows.items():
        previous = earlier[case]["complete"]["identity"]
        for mode, row in cells.items():
            identity = row["identity"]
            if (identity["mode"] != mode or row["mode"] != "control" or not row["single_attempt"]
                    or len(row["attempts"]) != 1 or identity["graph_parameters"] != GRAPH
                    or any(identity[k] != previous[k] for k in PAIRED_FIELDS)
                    or identity["complete_native_sha256"] != previous["native_sha256"]):
                raise ValueError("The replay changed the mode, archive, offer or known native packet")
    pins = {path.name: sha256(path.read_bytes()).hexdigest() for modes in paths.values() for path in modes.values()}

    truth = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == CASES[0] and r["authority_eligible"]]
    truth[CASES[0]] = [physical["reference"][key] for key in ("latitude_deg", "longitude_deg")]
    outcomes = {case: {mode: compare(row, cells["all-both"], earlier[case]["complete"], truth[case])
                      for mode, row in cells.items()} for case, cells in rows.items()}
    eligible = [mode for mode in ("reduced-primary", "all-primary") if all(
        cells[mode]["passes_position"] and cells[mode]["charge"]["passes_dense_projection"]
        for cells in outcomes.values())]
    advance = eligible[0] if eligible else None
    missing = None
    if advance is not None:
        missing_path = directory / f"south-far-{advance}.json"
        if missing_path.exists():
            far = read(missing_path)
            inside = rows["south-containing"][advance]["identity"]
            if (far["identity"]["native_sha256"] != inside["native_sha256"]
                    or far["identity"]["mode"] != advance or far["identity"]["graph_parameters"] != GRAPH
                    or not far["single_attempt"] or len(far["attempts"]) != 1):
                raise ValueError("The missing offer changed the selected receiver packet or route")
            missing = compare(far, earlier["south-far"]["complete"], earlier["south-far"]["complete"], truth["south-far"])
            pins[missing_path.name] = sha256(missing_path.read_bytes()).hexdigest()
            rows["south-far"] = {advance: far}
    check = dict(cases=outcomes, advance_missing_mode=advance, missing=missing, receipt_sha256=pins,
                 reference_sha256={path.name: sha256(path.read_bytes()).hexdigest() for path in (PHYSICAL, SIMULATED)},
                 prior_complete_archive_sha256=CONTROL_SHA, reused_archive_sha256=AVAILABILITY_SHA,
                 short_projected_cpu_s_per_lane=SHORT_CPU_S)
    write(summary, check)
    with archive.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    runner, scorer = (actions.add_parser(name) for name in ("run", "score"))
    runner.add_argument("case", choices=CASES)
    runner.add_argument("mode", choices=FACTORS)
    runner.add_argument("output", type=Path)
    runner.add_argument("--gate", type=Path)
    for name in ("directory", "summary", "archive"):
        scorer.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    {"run": run, "score": score}[args.pop("action")](**args)
