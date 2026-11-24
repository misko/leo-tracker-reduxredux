"""Compare the two-centre search on two authenticated physical saved inputs."""

import argparse
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from time import time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import history_risk_0138 as representative
from exact_grid_0138 import deny_backing, grid_body
from two_centre_seeds import elapsed, now, two_seeds


PROTOCOL = HERE/"two-centre-seeds-protocol.md"
REFERENCES = {
    "0138": ("leo-v3-history-risk-0138-pair02", "8bd0bbd2b6f2d9382f4bb9bd4ac0fdd216a16f38de73cdc2b68b2bb75f9f9b68",
             "routed/risk-route.json", "1ce09cff6155d2cdf3efbad8344bc51def0ee1c7e435cd1b5acb2d08ca408d58"),
    "0169": ("leo-v3-history-risk-0169-01", "ceac57a6be8d37df09c7ddab72ff326f4dd3f6fdc5ff00878d560674c453851b",
             "risk-route.json", "6922f4bb992a339fae2bc532c69618d41243dbc24e6e3ddf8952410805421b30"),
}
ORDERS = {"0138": ("ordinary", "candidate"), "0169": ("candidate", "ordinary")}


class RanCold(BaseException):
    """Stop the saved diagnostic before a downstream fit or publication."""


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def reference(case):
    folder, pin, route_path, route_pin = REFERENCES[case]
    root = Path("/dev/shm")/folder
    result = json.loads(representative.checked(root/"result.json", pin))
    route = json.loads(representative.checked(root/route_path, route_pin))["solves"]
    solved, = route
    fit, = solved["lean_attempts"]
    if solved["choice"]["route"] != "lean" or fit["decision"] != "complete":
        raise ValueError("Expected the pre-enrolled healthy physical comparisons")
    return root, result, fit


def cold_measure(refine, mode, prep, region, bound, *, candidate):
    from leo.analysis.localization_v3.discovery import signature
    from tools.pipeline_eval.variants import v5_core

    original = v5_core.ranked_initial_nodes
    audit = {}

    def rank(scan):
        start = now()
        with two_seeds(audit) if candidate else nullcontext():
            nodes = original(scan)
        if candidate and len(nodes) < 3 and audit.get("paid_centres") == 2:
            audit["fallback"] = "insufficient_distinct_ranked_assignments"
            nodes = original(scan)
        audit["rank"] = elapsed(start)
        audit["catalogue"] = len(scan.norads)
        audit["ranked"] = [signature(node) for node in nodes]
        return nodes

    start = now()
    with patch.object(v5_core, "ranked_initial_nodes", rank):
        value = refine(mode, prep, region, bound)
    audit["cold"] = elapsed(start)
    audit["winner"] = signature(value[0])
    audit["finalists"] = value[3]
    return value, audit


@contextmanager
def observe(boot, case, probe, audit):
    from contextlib import ExitStack

    ordinary = boot.load_runtime
    with ExitStack() as current:
        def load():
            runtime = ordinary()
            import cold_finalist_race as race

            refine = race.refine

            def cold(mode, prepared, region, bound):
                if audit:
                    raise ValueError("Expected one native cold-stage request")
                if not probe:
                    value, audit["candidate"] = cold_measure(refine, mode, prepared, region, bound, candidate=True)
                    return value
                for arm in ORDERS[case]:
                    _, audit[arm] = cold_measure(refine, mode, prepared, region, bound, candidate=arm == "candidate")
                raise RanCold

            current.enter_context(patch.object(race, "refine", cold))
            return runtime

        current.enter_context(patch.object(boot, "load_runtime", load))
        yield


def worker(root, case, probe):
    import empty_bootstrap as boot

    sys.addaudithook(deny_backing)
    metadata = read(root/"trial-binding.json")
    if metadata["case"] != case or metadata["probe"] != probe:
        raise ValueError("Wrong physical benchmark boundary")
    for name, expected in metadata["sources"].items():
        if digest(HERE/name) != expected:
            raise ValueError(f"Unfrozen benchmark source {name}")
    from aperture_trial import write
    import history_risk_route_trial

    observed = {}
    try:
        with observe(boot, case, probe, observed):
            if case == "0138":
                representative.worker(root, "routed")
            else:
                history_risk_route_trial.worker(case, root)
    except RanCold:
        if not probe or set(observed) != {"ordinary", "candidate"}:
            raise
    else:
        if probe:
            raise ValueError("Rank-only worker did not reach the frozen cold boundary")
    if not observed:
        raise ValueError("Candidate did not run through original cold discovery")
    write(root/"cold-audit.json", observed)


def prepare(root, case, probe, prior):
    from aperture_trial import RELEASE, write
    from exact_named_route import checked_catalogue
    from history_risk_route_trial import request_binding, sources
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    sys.addaudithook(deny_backing)
    if root.parent.resolve(strict=True) != Path("/dev/shm") or root.exists():
        raise ValueError("Use a fresh saved comparison in tmpfs")
    if not probe and (case != "0138" or prior is None
                      or not read(prior/"score.json")["advances"]):
        raise ValueError("The 0138 matched cold comparison must pass first")
    previous, _, fit = reference(case)
    bound, req = representative.bound_request() if case == "0138" else request_binding(case)
    _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    files = [Path(req["native_file"]), Path(bound["portable"][0]), *(ref.path for ref in refs)]
    resident = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *files]))["fincore"]
    if len(files) != len(resident) or any(row["res"] < row["size"] for row in resident):
        raise ValueError("All enrolled saved packet and catalogue pages must already be resident")
    root.mkdir(mode=0o700)
    for name in ("fonts", "tmp"):
        (root/name).mkdir()
    for path in (previous/"fonts").glob("fontlist-*.json"):
        os.link(path, root/"fonts"/path.name)
    source = {p.name: digest(p) for p in (Path(__file__), HERE/"two_centre_seeds.py", PROTOCOL)}
    command = ["/usr/bin/timeout", "--kill-after=2s", "60s", str(RELEASE/"venv/bin/python"), "-IB",
               str(Path(__file__).resolve()), "probe-worker" if probe else "active-worker", str(root), case]
    write(root/"trial-binding.json", dict(case=case, probe=probe, sources=source, command=command,
          offered_region_sha256=req["offer_sha256"], signed_native_sha256=req["native_sha256"],
          resident_tle_snapshots=len(refs), resident_inputs_bytes=sum(row["size"] for row in resident),
          earlier_pins=REFERENCES[case], earlier_cold_sha256=canonical_digest(fit["cold"])))
    write(root/"binding.json", dict(input=bound))
    write(root/"route-binding.json", dict(cutoff_utc_ns=req["causal_cutoff_utc_ns"], sources=sources(case)))
    return command


def launch(root, case, probe, prior):
    from aperture_trial import write
    from full_short_physical import environment

    command = prepare(root, case, probe, prior)
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    before = getrusage(RUSAGE_CHILDREN)
    started, start = time_ns(), now()
    with (root/"candidate.stdout").open("x") as stdout, (root/"candidate.stderr").open("x") as stderr:
        child = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, check=False)
    finish, after = elapsed(start), getrusage(RUSAGE_CHILDREN)
    write(root/"clock.json", dict(started_unix_ns=started, elapsed_s=finish["elapsed_ns"]/1e9, exit_code=child.returncode,
          cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime, input_blocks=after.ru_inblock-before.ru_inblock,
          major_faults=after.ru_majflt-before.ru_majflt))
    if child.returncode:
        raise ValueError("Saved worker failed; paid stderr and clock are sealed")
    score(root)


def signatures(row):
    return [tuple(map(tuple, node)) for node in row["ranked"]]


def cold_gate(ordinary, candidate):
    projected = signatures(candidate)
    left = ordinary["finalists"]
    right = candidate["finalists"]
    minimum = left["scores"][left["branch"]-1]
    score = right["scores"][right["branch"]-1]
    gain = (ordinary["cold"]["cpu_ns"]-candidate["cold"]["cpu_ns"])/1e9
    return dict(cpu_gain_s=gain, baseline_score=minimum, candidate_score=score,
                passes=gain >= 1.0 and score <= minimum*1.01 and len(set(projected[:3])) == 3
                and candidate.get("paid_centres") == 2 and not candidate.get("fallback"),
                exact_overlap=len(set(signatures(ordinary)[:3]) & set(projected[:3])),
                ordinary_winner_in_candidate_top3=tuple(map(tuple, ordinary["winner"])) in projected[:3])


def score(root):
    from aperture_trial import write

    sys.addaudithook(deny_backing)
    binding, paid, observed = [read(root/name) for name in ("trial-binding.json", "clock.json", "cold-audit.json")]
    case = binding["case"]
    archive, original, fit = reference(case)
    if paid["exit_code"]:
        raise ValueError("Only completed and sealed workers are scoreable")
    result = dict(binding=binding, clock=paid, cold=observed, waveform_reads=0)
    if binding["probe"]:
        stored = fit["cold"]
        measured = observed["ordinary"]["finalists"]
        if any(stored[key] != measured[key] for key in ("catalogue", "scores", "branch", "east_north_km")):
            raise ValueError("Ordinary cold control changed from the original publication")
        gate = cold_gate(observed["ordinary"], observed["candidate"])
        result.update(gate=gate, advances=case == "0138" and gate["passes"], order=ORDERS[case])
    else:
        result.update(publication=publication(root, archive, original))
    write(root/"score.json", result)


def publication(root, archive, previous):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km

    request = json.loads(representative.checked(representative.STAGE/"request.json", representative.REQUEST_PIN))
    ref_db = json.loads(representative.checked(representative.REFERENCE, representative.REFERENCE_PIN))
    reference_row, = [r for r in ref_db["cases"] if r["dataset_label"] == request["case"]]
    if not reference_row["authority_eligible"] or not reference_row["sealed_metadata_digests_verified"]:
        raise ValueError("Original operator reference is ineligible")
    truth = [reference_row["reference"][name] for name in ("latitude_deg", "longitude_deg")]
    evidence = {}
    for mode, output in (("candidate", root/"candidate"), ("routed", archive/"routed/candidate"),
                         ("named", archive/"named/candidate")):
        worker = read(output/"worker.json")
        joint = read(output/"joint-research-receipt.json")
        receipt = worker["receipt"]
        run_id = receipt["run_id"]
        workspace = output/"fast-scan-automatic-work"
        native_file, = workspace.glob("*/detections.json")
        terminal = read(workspace/run_id/"terminal.json")
        if (not worker["no_waveform"] or worker["handoffs"] != 1 or joint["receipt"] != receipt
                or digest(native_file) != request["native_sha256"] or receipt["session_id"] != request["session"]
                or canonical_digest(terminal) != receipt["terminal_sha256"]):
            raise ValueError("Expected one confirmed original saved handoff")
        store = FastStandardAnalysisStore(output)
        figures = artifacts(output, receipt)["images"]
        grid, path = store.position_grid(run_id), store.position_path(run_id)
        if receipt["decision"] == "complete":
            if (len(figures) != 8 or len(grid["points"]) != 179 or not grid["complete"]
                    or any(x["binding"]["position_png_sha256"] != figures["position"]["sha256"] for x in (grid, path))):
                raise ValueError("Expected original grid and eight independently decoded standard products")
        elif figures or grid or path:
            raise ValueError("Withholding cannot have position products")
        detail = store.detail(run_id)
        arms = {
            key: dict(endpoint=val["latlon"], conditional_rf_rms_hz=val.get("rf_rms_hz"),
                      all_owned_rf_rms_hz=detail["arms"].get(key, {}).get("residual_rms_hz"),
                      horizontal_error_km=None if val["latlon"] is None else distance_km(truth, val["latlon"]),
                      owners=len(joint["selected_rows"].get(key, [])))
            for key, val in terminal["arms"].items()
        }
        evidence[mode] = dict(receipt=receipt, terminal=terminal, arms=arms, figures=figures,
                              grid=None if grid is None else canonical_digest(grid_body(grid)),
                              path=None if path is None else canonical_digest(path), rows=joint["selected_rows"])
    proposed = evidence["candidate"]
    solves, = read(root/"risk-route.json")["solves"]
    branch, = solves["lean_attempts"]
    tolerance = proposed["receipt"]["decision"] == "complete" and all(
        proposed["arms"][arm]["horizontal_error_km"] <= evidence[mode]["arms"][arm]["horizontal_error_km"] + .25
        for mode in ("routed", "named") for arm in ("c0", "fitted_c"))
    changes = {
        mode: {arm: owner_delta(evidence[mode]["rows"].get(arm, []), proposed["rows"].get(arm, []))
               for arm in ("c0", "fitted_c")} for mode in ("routed", "named")
    }
    for entry in evidence.values():
        entry.pop("rows")
    return dict(science=evidence, position_gate=tolerance, owner_changes=changes, signed_route=solves["choice"]["route"],
                solver_decision=branch["decision"], exterior=branch.get("exterior"), charged_fallback=branch.get("fallback_clocks"),
                routed_clock=previous["clock"], named_clock=previous["archive_stock_clock"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("probe", "active", "probe-worker", "active-worker", "score"))
    p.add_argument("root", type=Path)
    p.add_argument("case", choices=tuple(REFERENCES))
    p.add_argument("--prior", type=Path)
    args = p.parse_args()
    if args.action.endswith("worker"):
        worker(args.root, args.case, args.action == "probe-worker")
    elif args.action == "score":
        score(args.root)
    else:
        launch(args.root, args.case, args.action == "probe", args.prior)
