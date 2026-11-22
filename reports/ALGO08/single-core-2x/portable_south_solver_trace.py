"""Record stage evidence on the published southern portable-v5 matched offer."""

import argparse
import json
import os
import runpy
import subprocess
from collections import Counter
from contextlib import ExitStack, contextmanager
from functools import wraps
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SOURCE = Path(__file__).resolve()
TRANSFER = SOURCE.with_name("covariance_transfer_trial.py")
CASE = "0ea3bb46005a423fcdf0239e"
NATIVE = "17dbb334d49e37ad439b4170aed3174ba485059e04ef6121ce8968c4f72f77e9"
SPEC = "sha256:375895c3afda3abd3a916f90bbd63248b5e792f70c78a0e4f136c9bf1a79d423"
ARMS = ("c0", "fitted_c")


def identity(scan, node, keep=None):
    tracks = {row["key"]: row for row in scan.tracks}
    rows = [row for row in node["seed"]["rows"] if row["active_curvature"]]
    supports, start = [], 0
    for row, alias in zip(rows, node["aliases"], strict=True):
        name = row["component"]
        track = tracks[name]
        items = track["observation_ids"]
        end = start + len(items)
        if keep is not None:
            items = [oid for oid, active in zip(items, keep[start:end], strict=True) if active]
        supports.append(dict(component=name, norad=row["candidate_norad"], alias=alias,
                             receiver=track["receiver"], channel=track["channel"], points=len(items),
                             observations=sha256("\n".join(items).encode()).hexdigest()))
        start = end
    if keep is not None and len(keep) != start:
        raise ValueError("Curved mask exceeds captured track rows")
    return sorted(supports, key=lambda row: row["component"])


def fits(arms):
    result = {}
    for arm, item in (arms or {}).items():
        record = item.get("record", item)
        endpoint = record.get("endpoint_east_north_km")
        if endpoint is None:
            endpoint = record["fit"]["parameters"]
        result[arm] = dict(endpoint=endpoint, phase_reference=record.get("phase_reference"),
                           objective=record.get("negative_twice_elbo"),
                           rf_rms_hz=record.get("RMS_hz", record.get("fit", {}).get("residual_rms_hz")),
                           failed=sorted(row["component"] for row in
                                         item.get("metrics", record.get("gates", {})).get("tracks", [])
                                         + record.get("linear_gates", []) if not row["compatible"]))
    return result


def entries(items):
    return [{key: row[key] for key in ("component", "candidate_norad", "alias", "points") if key in row}
            | {"norad": row.get("norad", row.get("candidate_norad"))} for row in items]


def selected(context):
    return dict(curved=identity(context["scan"], context["node"], context["keep"]),
                predictive=entries(context["entries"]), arms=fits(context["arms"]),
                powers=list(context["powers"]), means=list(context["means"]), model=context["model"])


@contextmanager
def traced(notes, candidate):
    from leo.analysis.localization_v3 import acceptance, conservative_recovery, family_cavity
    from leo.analysis.localization_v3 import history_policy, position, signed_context
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    def inspect(original, readout):
        @wraps(original)
        def observed(*args, **kwargs):
            answer = original(*args, **kwargs)
            readout(args, answer)
            return answer
        return observed

    def scan_context(args, scan):
        prior = args[4]
        notes[prior] = dict(norads=scan.norads, snapshot_sha256=scan.previous_tle_sha256,
                            tracks=[dict(key=t["key"], points=len(t["times"]),
                                         observations=sha256("\n".join(t["observation_ids"]).encode()).hexdigest(),
                                         frequency=sha256(t["values"].tobytes()).hexdigest())
                                    for t in scan.tracks])

    def ranks(args, nodes):
        notes["ranked"] = [identity(args[0], node) for node in nodes]

    def refresh(args, output):
        scan, _, node, arm = args[:4]
        _, _, history = output
        notes.setdefault("initial_branch_fits", []).append(dict(arm=arm, rows=identity(scan, node),
            rounds=[dict(endpoint=row["fit"]["parameters"], score=row["fit"]["score"],
                         rf_rms_hz=row["fit"]["residual_rms_hz"]) for row in history]))

    def initial(args, output):
        problem, _, arm, point = args
        notes["initial_gate"] = dict(arm=arm, endpoint=point, accepted=output["accepted_points"],
                                     failed=sorted(row["component"] for row in output["tracks"]
                                                   if not row["compatible"]),
                                     owners=[(row["component"], row["candidate_norad"], alias)
                                             for row, alias in zip(problem.rows, problem.alias, strict=True)])

    def gate(args, output):
        scan, node, incoming, stage = args[:4]
        _, keep, pair, rounds, stable = output
        notes.setdefault("conservative_gates", []).append(dict(stage=stage, stable=stable,
            incoming=identity(scan, node, incoming), curved=identity(scan, node, keep),
            rounds=rounds, arms=fits(pair)))

    def salvage(args, output):
        scan, old, incoming = args[:3]
        node, keep, report = output
        notes.setdefault("salvage", []).append(dict(incoming=identity(scan, old, incoming),
            curved=identity(scan, node, keep), selected=[r for r in report if r["selected"] is not None]))

    def family(args, output):
        scan, old = args[:2]
        notes["family"] = dict(status=output["status"],
            curved=identity(scan, old["final_node"], output["mask"]),
            curved_arms=fits(output["curved_arms"]), predictive=entries(output["linear_entries"]),
            linear_valid=output["linear_paired_valid"], chosen_arms=fits(output["policy_arms"]))

    def signed(_args, output):
        notes["signed"] = dict(selected(output), qualified=output["signed"]["selection"]["qualified"],
                               accepted=output["signed"]["accepted"], selection=output["signed"]["selection"])

    def cavity(_args, output):
        notes["cavity"] = dict(status=output["status"],
            offers=[dict(target=row["original_norad"], alternative=row["best"]["norad"],
                         gain=row["predictive_gain"]) for row in output.get("families", [])
                    if row["best"] is not None and row["predictive_gain"] > 0])

    def cavity_policy(_args, output):
        notes["cavity"]["accepted"] = output["accepted"]
        notes["cavity"]["arms"] = fits(output["policy_arms"])

    def packet(args, output):
        _, context, cavity_result = args
        notes["selection_used_cavity"] = bool(cavity_result and cavity_result["accepted"])
        notes["selected_before_cavity"] = selected(context)
        notes["published_points"] = {
            arm: {row["observation_id"]: [row["component"], row["norad"], row["role"]]
                  for row in output["rows"][arm]} for arm in ARMS}
        notes["objective_replay"] = output["objective_replay"]

    routes = [
        (v5_core, "scan_context", scan_context), (v5_core, "ranked_initial_nodes", ranks),
        (position, "refreshed", refresh), (acceptance, "actual_metrics", initial),
        (conservative_recovery, "fit_and_gate", gate), (conservative_recovery, "salvage", salvage),
        (history_policy, "history_policy", family), (signed_context, "signed_context", signed),
        (family_cavity, "nominate_families", cavity), (family_cavity, "cavity_policy", cavity_policy),
        (algo08_position, "selected_packet", packet),
    ]
    if candidate:
        from tools.pipeline_eval.variants import algo08_collapsed, algo08_collapsed_signed_finish

        def paired(args, output):
            scan, node, keep, arm, *_ = args
            notes.setdefault("collapsed_pairs", []).append(dict(
                curved=identity(scan, node, keep), arms=fits({arm: output[0]})))

        def pre_signed(args, _output):
            notes["collapsed_post_recovery"] = selected(args[1])

        routes.extend(((algo08_collapsed, "refit", paired),
                       (algo08_collapsed_signed_finish, "apply_signed", pre_signed)))
    with ExitStack() as stack:
        for module, name, readout in routes:
            stack.enter_context(patch.object(module, name, inspect(getattr(module, name), readout)))
        yield


def worker(mode, site, frozen, output):
    from leo.application.localization_v3_engine import _json_value
    from tools import algo08_position

    transfer = runpy.run_path(str(TRANSFER))
    solve = algo08_position.solve
    notes = {}

    def collect(*args, **kwargs):
        with traced(notes, mode == "covariance"):
            decision, packet, policy = solve(*args, **kwargs)
        metrics = decision["metrics"]
        for key in ("initial_rejected_tracks", "paired_gate_rounds", "salvage_addback", "cavity_offered"):
            if key in metrics:
                notes[key] = metrics[key]
        return decision, packet, policy

    spec = frozen / "spec.json" if mode == "covariance" else None
    with TemporaryDirectory() as temporary, patch.object(algo08_position, "solve", collect):
        final = Path(temporary) / "final.json"
        transfer["worker"](site / "native.json", site / "tle", site / "matched-tile.json", final, spec)
        result = json.loads(final.read_bytes())
    with output.open("x") as stream:
        json.dump(dict(result=result, stages=notes), stream, default=_json_value, allow_nan=False)


def owner_audit(baseline, candidate):
    def groups(owned, ids):
        return sorted([list(key) + [n] for key, n in Counter(tuple(owned[oid]) for oid in ids).items()])

    common = baseline.keys() & candidate.keys()
    unchanged = {key for key in common if baseline[key] == candidate[key]}
    relabelled = {key for key in common if baseline[key][1] != candidate[key][1]}
    return dict(common=len(common), unchanged=len(unchanged), satellite_changes=len(relabelled),
                changed_owner_or_role=len(common - unchanged),
                installed_only=groups(baseline, baseline.keys() - common),
                covariance_only=groups(candidate, candidate.keys() - common),
                other_common_changes=groups(candidate, common - unchanged))


def run(root, frozen, output):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity, verify_sources

    transfer = runpy.run_path(str(TRANSFER))
    release = transfer["RELEASE"]
    spec = json.loads((frozen / "spec.json").read_bytes())
    if canonical_digest(spec) != SPEC or Path("/opt/leo-algo08/current").resolve() != release:
        raise ValueError("Expected the installed release and original covariance freeze")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    site = root / CASE
    plans = [row for row in json.loads((root / "plan.json").read_bytes())
             if row["case"] == CASE and row["mode"] == "matched-tile"]
    plan, = plans
    if (sha256((site / "native.json").read_bytes()).hexdigest() != NATIVE
            or plan["document_sha256"] != NATIVE
            or json.loads((site / "matched-tile.json").read_bytes()) != plan["offer"]):
        raise ValueError("Saved southern containing inputs differ from the released plan")
    archive = archive_identity(site / "tle")
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    os.mkdir(output)
    outcomes = {}
    for mode in ("installed", "covariance"):
        roots = [release / "src", release]
        if mode == "covariance":
            roots.insert(0, frozen)
        env["PYTHONPATH"] = os.pathsep.join(map(str, roots))
        trace = output / f"{mode}.json"
        subprocess.run([str(release / "venv/bin/python"), "-BPs", str(SOURCE), "worker", mode,
                        *map(str, (site, frozen, trace))], env=env, check=True, timeout=110)
        traced_result = json.loads(trace.read_bytes())
        original = json.loads((site / f"matched-tile-{mode}.json").read_bytes())
        keys = ("status", "reason", "arms", "associated", "owners", "orbit_policy")
        if any(traced_result["result"][key] != original[key] for key in keys):
            raise ValueError(f"{mode} trace differs from its saved control")
        outcomes[mode] = traced_result
    if archive_identity(site / "tle") != archive:
        raise ValueError("Causal archive changed during attribution")
    audits = {}
    for arm in ARMS:
        values = [build["stages"]["published_points"].pop(arm) for build in outcomes.values()]
        audits[arm] = owner_audit(*values)
    with (output / "attribution.json").open("x") as stream:
        json.dump(dict(plan=plan, archive=archive, specification_sha256=SPEC, installed_release=release.name,
                       results=outcomes, owner_differences=audits), stream, indent=2, sort_keys=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    trial = commands.add_parser("run")
    for name in ("root", "frozen", "output"):
        trial.add_argument(name, type=Path)
    child = commands.add_parser("worker")
    child.add_argument("mode", choices=("installed", "covariance"))
    for name in ("site", "frozen", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    {"run": run, "worker": worker}[args.pop("action")](**args)
