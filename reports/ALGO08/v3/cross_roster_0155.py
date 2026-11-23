"""Replay owned likelihoods and cross their original final numerical routines."""

import argparse
from contextlib import ExitStack
from functools import partial, wraps
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter, process_time
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from prospective_0155_solver import ARCHIVE_SHA, CUTOFF, PINS, SETTINGS, invoke, pinned
from prospective_small_physical import checked


HERE = Path(__file__).resolve().parent
STAGE = Path("/dev/shm/leo-v3-saved-0155-pair-01")
BASELINE = STAGE.with_name("leo-v3-saved-0155-result.json")
BASELINE_SHA = "63efc82d3c0fa0889f3c85e630ddb427f041b6174a7c9f175676c1f0fec64d75"
REQUEST_SHA = "c0533ae6b92b66593d59a2f9a7aaf2b64194563c18ef8038ec2afdfc66c1da79"
RESEARCH = {"stock": "732670de7744987d520538c6e07449fb939afc5c88502fac2ba394e577a0fc54",
            "cumulative": "b82d5b1aa6c86109646eae0666779fe72b2457c487b8437f3e21ebeecd99325f"}
ARMS = ("c0", "fitted_c")
DIAGONALS = [("stock", "stock"), ("cumulative", "cumulative")]
OFF_DIAGONALS = [("stock", "cumulative"), ("cumulative", "stock")]


def now():
    return process_time(), perf_counter()


def elapsed(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


class Captured(BaseException):
    """Stop the private diagnostic at valid selected evidence before publication."""


def family_phase(norads, phases):
    return dict(zip(map(int, norads), map(float, phases), strict=True))


def transport(start, norads):
    import numpy as np

    return np.array([start.get(int(n), 0.) for n in norads], dtype=float)


def row_data(context, arm):
    """Preserve model input order as curve mask and then predictive entry order."""
    p, _ = context["problems"][arm]
    scan = p.scan
    rows = []
    for row, member, section, alias, group in zip(p.rows, p.members, p.slices, p.alias, range(len(p.rows)), strict=True):
        t = scan.tracks[member]
        values = zip(t["observation_ids"], p.keep[section], p.values[section], p.point_noise[section], strict=True)
        for oid, keep, y, sigma in values:
            if keep:
                rows.append([oid, int(row["candidate_norad"]), "conditional", t["key"], int(alias),
                             float(y), float(sigma), float(context["powers"][group])])
    for entry in context["entries"]:
        t = scan.tracks[entry["track_index"]]
        if list(t["observation_ids"]) != list(entry["observation_ids"]):
            raise ValueError("The predictive arc changed the captured track order")
        for oid, y in zip(entry["observation_ids"], t["values"], strict=True):
            rows.append([oid, int(entry["norad"]), "predictive", t["key"], int(entry["alias"]), float(y), None, None])
    return rows


def witnessed_roles(rows):
    mapped = {row[0]: tuple(row[1:3]) for row in rows}
    if len(mapped) != len(rows):
        raise ValueError("A captured fitter cannot own one observation twice")
    return mapped


def clocked_refitter(function, tag, witness):
    @wraps(function)
    def record(*args, **kwargs):
        result = function(*args, **kwargs)
        witness[id(result["history"])] = (result["history"], tag)
        return result
    return record


def capture(root, route, historical, expected, *, job=STAGE / "request.json", invoke_job=invoke, cutoff=CUTOFF):
    import numpy as np
    from leo.analysis.localization_v3 import family_cavity, history_policy, signed_context
    from leo.contracts.digests import canonical_digest
    from tools import algo08_position as port
    import blind_joint_finish as finish
    import blind_joint_repair as repair

    official_packet, recover, assemble = port.selected_packet, port.recovery_context, port.prepare_packet
    refit = finish.arm_finish
    results, warm, cold = {}, {}, {}

    def warm_fit(scan, node, keep, arm, reference, powers, means, model, entries, seed):
        record = refit(scan, node, keep, arm, reference, powers, means, model, entries, seed)
        ids = [int(scan.norads[j]) for j in sorted({r["candidate_index"] for r in node["seed"]["rows"]})]
        warm[id(record["history"])] = (record["history"], np.array(seed, copy=True), family_phase(ids, reference))
        return record

    def remember_recovery(*args):
        ctx = recover(*args)
        results["context"] = ctx
        return ctx

    def remember_selection(prepared, signed, fit):
        results["selection_clock"] = elapsed(start)
        verify = now()
        with (patch.object(port, "recovery_context", remember_recovery),
              patch.object(port, "prepare_packet", partial(assemble, include_grid=False))):
            packet = official_packet(prepared, signed, fit)
        arms = results["context"]["saved"]["policy_arms"]
        rows = {a: [[v["observation_id"], v["norad"], v["role"]] for v in packet["rows"][a]] for a in ARMS}
        if rows != expected["selected_rows"] or rows != historical["selected_rows"]:
            raise ValueError("Released ordered ownership in the captured context changed from the complete publication")
        for arm, value in arms.items():
            reported = historical["terminal"]["arms"][arm]
            if (not np.allclose(value["endpoint_latlon"], reported["latlon"], rtol=0, atol=1e-10)
                    or abs(value["RMS_hz"]-reported["rf_rms_hz"]) > 1e-8):
                raise ValueError("Captured published endpoint or fit quality changed")
            if witnessed_roles(row_data(results["context"], arm)) != witnessed_roles(rows[arm]):
                raise ValueError("Published owner rows do not equal the executable selected observations")
        results.update(rows=rows, packet_replay=packet["objective_replay"], capture_clock=elapsed(verify),
                       phase_history=canonical_digest(prepared["phase_history"]), forecast=canonical_digest(prepared["phase_forecast"]),
                       cutoff=prepared["sky"]["metadata"]["cutoff_utc_ns"])
        results["warm"] = {arm: warm.get(id(row["history"])) for arm,row in arms.items()}
        results["cold"] = {arm: cold.get(id(row["history"])) for arm,row in arms.items()}
        raise Captured()

    with ExitStack() as scope:
        scope.enter_context(patch.object(port, "selected_packet", remember_selection))
        for module, name, tag in ((history_policy, "linear_refit", "predictive_linear"),
                                  (history_policy, "refit", "history_curved"),
                                  (signed_context, "refit", "event_position"),
                                  (family_cavity, "refit", "event_position")):
            scope.enter_context(patch.object(module, name, clocked_refitter(getattr(module, name), tag, cold)))
        for module in (finish, repair):
            scope.enter_context(patch.object(module, "arm_finish", warm_fit))
        start = now()
        try:
            invoke_job(job, route, root / ("capture-"+route))
        except Captured:
            pass
    if results.get("cutoff") != cutoff or "rows" not in results:
        raise ValueError("The captured route did not reach signed selected evidence")
    return results


def brief(context, arm, record):
    from leo.analysis.localization_v3.history_policy import pair_passes

    scan, region = context["scan"], context["scan"].search_region
    gates = record["gates"]["tracks"] + record.get("linear_gates", [])
    ok = pair_passes({a: record for a in ARMS}, include_linear=bool(context["entries"]), half_width_km=region.half_width_km)
    return dict(east_north_km=record["endpoint_east_north_km"], latlon=record["endpoint_latlon"],
                rf_rms_hz=record["RMS_hz"], elbo=record["negative_twice_elbo"],
                refits=len(record.get("history", [])), final_phase_change_s=record.get("final_phase_change_s"),
                in_domain_gate=bool(ok), failed_tracks=[row["component"] for row in gates if not row["compatible"]],
                rf_calibration=arm, phase_family_columns=len({int(scan.norads[j]) for j in context["problems"][arm][0].labels}))


def diagonal_agreement(original, refitted):
    import numpy as np

    diff = np.asarray(original["east_north_km"]) - np.asarray(refitted["east_north_km"])
    return dict(position_km=float(np.linalg.norm(diff)), rf_hz=abs(original["rf_rms_hz"]-refitted["rf_rms_hz"]),
                elbo=abs(original["elbo"]-refitted["elbo"]))


def refit(roster, fitter_name, stored):
    from leo.analysis.localization_v3 import event_position, history_position, predictive_linear
    from blind_joint_finish import arm_finish

    ctx, fitter = stored[roster]["context"], stored[fitter_name]
    scan, node, keep, powers, means, model, entries = (ctx[key] for key in ("scan", "node", "keep", "powers", "means", "model", "entries"))
    start = now()
    pairs = {}
    for arm in ARMS:
        stamp = now()
        if fitter_name == "cumulative":
            _, point, phases = fitter["warm"][arm]
            ids = [scan.norads[j] for j in ctx["problems"][arm][0].labels]
            result = arm_finish(scan, node, keep, arm, transport(phases, ids), powers, means, model, entries, point)
        else:
            _, route = fitter["cold"][arm]
            if route == "predictive_linear":
                result = predictive_linear.refit(scan, node, keep, powers, means, model, arm, entries)
            elif route == "event_position":
                result = event_position.refit(scan, node, keep, arm, powers, means, model, [], entries)
            elif route == "history_curved" and not entries:
                result = history_position.refit(scan, node, keep, arm, powers, means, model["multiplier"], model["nu"])
                result.setdefault("linear_gates", [])
            else:
                raise ValueError("The captured stock refit cannot represent both fixed arc designs")
        seen_ids = [oid for group in result["gates"]["tracks"]+result.get("linear_gates", []) for oid in group["observation_ids"]]
        owned_ids = [row[0] for row in row_data(ctx, arm)]
        if seen_ids != owned_ids:
            raise ValueError("An identified final refitter altered the frozen likelihood support or order")
        pairs[arm] = dict(**brief(ctx, arm, result), clock=elapsed(stamp), ordered_support_count=len(seen_ids))
    return dict(arms=pairs, clock=elapsed(start), fixed_roster=roster, original_refitter=fitter_name)


def deletion(stored):
    import numpy as np
    from leo.analysis.localization_v3 import event_position, position

    candidate = stored["cumulative"]
    ctx = candidate["context"]
    stock = witnessed_roles(stored["stock"]["rows"]["c0"])
    own = witnessed_roles(candidate["rows"]["c0"])
    dropped = sorted(own.keys() - stock.keys())
    if not dropped or any(own[k][1] != "conditional" for k in dropped) or any(
            v != stock[k] for k,v in own.items() if k in stock):
        raise ValueError("Cannot isolate conditional deletions on the captured candidate design")
    answers = {}
    for arm in ARMS:
        p0, seed = ctx["problems"][arm]
        mask = ctx["keep"].copy()
        for member, section in zip(p0.members, p0.slices, strict=True):
            identifiers = p0.scan.tracks[member]["observation_ids"]
            mask[section] &= ~np.isin(identifiers, dropped)
        if int(ctx["keep"].sum()-mask.sum()) != len(dropped):
            raise ValueError("A deletion could not be mapped to one exact curved design row")
        answers[arm] = {}
        for stride, keep in (("original", ctx["keep"]), ("common", mask)):
            start = now()
            p = event_position.make_event_problem(ctx["scan"], ctx["node"], keep, arm, p0.reference, ctx["powers"], ctx["means"], ctx["model"], [])
            event_position.attach_event_predictive(p, ctx["entries"], ctx["powers"])
            event_position.cached(p)
            if p.labels != p0.labels or p.hardware.shape != p0.hardware.shape or p.smooth.shape != p0.smooth.shape:
                raise ValueError("Deletion changed the formerly retained nuisance dimensions")
            score = float(p.calculate(seed)["negative_twice_elbo"])
            if stride == "original" and abs(score-ctx["saved"]["policy_arms"][arm]["negative_twice_elbo"]) > 1e-4:
                raise ValueError("The unmasked fixed phase original score no longer reproduces")
            fitted = position.fit(p, seed, iterations=48)
            row = event_position.summary(p, fitted["parameters"], ctx["entries"])
            answers[arm][stride] = dict(**brief(ctx, arm, row), initial_same_support_elbo=score, clock=elapsed(start))
    return dict(arms=answers, dropped=dropped, conditional_only=True)


def context_witness(stored):
    from leo.contracts.digests import canonical_digest

    briefs, all_rows = {}, {}
    for route, item in stored.items():
        context = item["context"]
        scan, owner_arms = context["scan"], context["saved"]["policy_arms"]
        arms, all_rows[route] = {}, {}
        for arm, r in owner_arms.items():
            p, _ = context["problems"][arm]
            ids = [scan.norads[j] for j in p.labels]
            data = all_rows[route][arm] = row_data(context, arm)
            arms[arm] = dict(**brief(context, arm, r), phase_reference=family_phase(ids, p.reference),
                             reported_phase_reference=family_phase(ids, r["phase_reference"]),
                             phase_prior_means=family_phase(ids, context["means"]),
                             ordered_row_and_likelihood_sha256=canonical_digest(data),
                             ordered_public_rows_sha256=canonical_digest(item["rows"][arm]),
                             hardware_design_sha256=sha256(p.hardware.tobytes()).hexdigest(),
                             receiver_smooth_design_sha256=sha256(p.smooth.tobytes()).hexdigest(),
                             column_counts=dict(hardware=p.hardware.shape[1], smooth=p.smooth.shape[1],
                                                phase=len(p.labels), orbit_modes=len(p.supported)*3))
        briefs[route] = dict(arms=arms, model=context["model"], noise_sha256=scan.fixed_window_noise_sha256,
                             phase_history_sha256=item["phase_history"], phase_forecast_sha256=item["forecast"],
                             selection_clock=item["selection_clock"], capture_clock=item["capture_clock"],
                             objective_replay=item["packet_replay"], actual_cold={a:v[1] if v is not None else None for a,v in item["cold"].items()},
                             actual_warm={a:dict(start=v[1], reference=v[2]) if v is not None else None for a,v in item["warm"].items()},
                             predictive_entries_sha256=canonical_digest(context["entries"]))
    comparison = {}
    for arm in ARMS:
        before, after = ({row[0]: row[1:] for row in all_rows[key][arm]} for key in ("stock", "cumulative"))
        common = before.keys() & after.keys()
        curves = {o for o in common if before[o][1] == after[o][1] == "conditional"}
        comparison[arm] = dict(shared=len(common), shared_conditional=len(curves),
                               changed_norad=sum(before[o][0]!=after[o][0] for o in common),
                               changed_role=sum(before[o][1]!=after[o][1] for o in common),
                               changed_component=sum(before[o][2]!=after[o][2] for o in common),
                               changed_signed_alias=sum(before[o][3]!=after[o][3] for o in common),
                               changed_graph_lifted_value=sum(before[o][4]!=after[o][4] for o in common),
                               changed_conditional_point_noise=sum(before[o][5]!=after[o][5] for o in curves),
                               changed_conditional_family_powers=sum(before[o][6]!=after[o][6] for o in curves))
    return briefs, comparison, all_rows


def run(root):
    import empty_bootstrap as staged

    all_stage = now()
    runtime = staged.load_runtime()
    from aperture_trial import write
    from dense_geographic_trial import host
    from tools.pipeline_eval.variants import orbit_projector
    from tools.pipeline_eval.variants.v5_direct_cavity import numerical_bindings

    machine = host()
    request = pinned(STAGE/"request.json", REQUEST_SHA)
    archived = pinned(BASELINE, BASELINE_SHA)
    if Path(request["local_archive"]["root"]) != STAGE/"tle" or request["causal_cutoff_utc_ns"] != CUTOFF:
        raise ValueError("The archival binding must point at the exact already staged causal snapshot roster")
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    refs = TleArchiveReader(STAGE/"tle").list_snapshots("space-track")
    if canonical_digest({r.path.name: r.sha256 for r in refs}) != ARCHIVE_SHA:
        raise ValueError("Tmpfs archive names no longer match the original prepared cutoff")
    checked(Path(request["native_file"]), SETTINGS["native_sha"])
    root.mkdir()
    with patch.object(staged, "load_runtime", return_value=runtime):
        captured = {route: capture(root, route, archived["runs"][route], pinned(STAGE/route/"joint-research-receipt.json", pin))
                    for route,pin in RESEARCH.items()}
    contexts, design, rows = context_witness(captured)
    write(root / "captured-contexts.json", dict(contexts=contexts, shared_design=design, exact_ordered_likelihood_rows=rows,
         original_native_sha256=SETTINGS["native_sha"], prior_publication_sha256=BASELINE_SHA, source_pins=PINS))
    cells, agreement, failure, restricted = {}, {}, None, None
    with numerical_bindings(orbit_projector.Projector(staged.RELEASE/"assets/projector.so")):
        try:
            if (len({contexts["stock"]["actual_cold"][a] for a in ARMS}) != 1
                    or not all(captured["stock"]["cold"].values()) or not all(captured["cumulative"]["warm"].values())):
                raise ValueError("One published refitter lacks the source-bound final fit identity")
            for roster, fitter in DIAGONALS:
                cell = cells[f"{roster}/{fitter}"] = refit(roster, fitter, captured)
                agreement[roster] = {arm: diagonal_agreement(contexts[roster]["arms"][arm], cell["arms"][arm]) for arm in ARMS}
            if any(row["position_km"] > 1e-8 or row["rf_hz"] > 1e-6 or row["elbo"] > 1e-4
                   for arms in agreement.values() for row in arms.values()):
                raise ValueError("Original same-roster refitter did not reproduce its diagonal")
            for roster, fitter in OFF_DIAGONALS:
                cells[f"{roster}/{fitter}"] = refit(roster, fitter, captured)
        except (ValueError, AssertionError) as exc:
            failure = str(exc)
            restricted = deletion(captured)
    outcome = dict(original_native_sha256=SETTINGS["native_sha"], wet_waveform_calls=0, case="DS30-0155",
                   sources=PINS, input_sha256={"request":REQUEST_SHA, "saved_pair":BASELINE_SHA, **RESEARCH},
                   driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                   protocol_sha256=sha256((HERE/"cross-roster-0155-protocol.md").read_bytes()).hexdigest(),
                   archived_full={name: archived["runs"][name]["process"] for name in RESEARCH},
                   machine=machine, context_capture_sha256=sha256((root/"captured-contexts.json").read_bytes()).hexdigest(),
                   contexts=contexts, shared_design=design, cells=cells, diagonal_differences=agreement,
                   crossed_failure=failure, fallback_fixed_phase=restricted, charged_through_results=elapsed(all_stage))
    write(root / "diagnostic.json", outcome)


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    host()
    env = environment(STAGE)
    env["TMPDIR"] = str(root.parent)
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "run", root]
    clock = measure(command, env, root)
    write(root.with_name(root.name+"-clock.json"), clock)
    if clock["exit_code"]:
        raise RuntimeError("The sole diagnostic process failed; its independent exit clock remains sealed")


def score(root, output):
    from aperture_trial import write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    path = root / "diagnostic.json"
    data = json.loads(path.read_bytes())
    clock = json.loads(root.with_name(root.name+"-clock.json").read_bytes())
    if clock["exit_code"] or data["case"] != "DS30-0155" or data["wet_waveform_calls"]:
        raise ValueError("Score only the completed saved diagnostic")
    point, = (row["reference"] for row in pinned(REFERENCE, REFERENCE_SHA256)["cases"] if row["dataset_label"] == data["case"]
              and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [point[key] for key in ("latitude_deg", "longitude_deg")]
    errors = {key: {a:distance_km(truth, v["latlon"]) for a,v in item["arms"].items()} for key,item in data["cells"].items()}
    if data["fallback_fixed_phase"]:
        errors["conditioned_deletion"] = {a:{key: distance_km(truth,r["latlon"]) for key,r in row.items()}
                                          for a,row in data["fallback_fixed_phase"]["arms"].items()}
    write(output, dict(diagnostic=data, process=clock, scored_errors_km=errors,
                       reference_sha256=REFERENCE_SHA256, diagnostic_sha256=sha256(path.read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("run").add_argument("root", type=Path)
    modes.add_parser("launch").add_argument("root", type=Path)
    post = modes.add_parser("score")
    post.add_argument("root", type=Path)
    post.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        run(args.root)
    elif args.mode == "launch":
        launch(args.root)
    else:
        score(args.root, args.output)
