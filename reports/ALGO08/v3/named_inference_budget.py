"""Reconcile disjoint named-inference CPU on the existing exact saved route."""

import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import exact_named_route as route
from named_roster_0155 import Ledger


CONTROL = Path("/dev/shm/leo-v3-exact-named-0316-result02")
CONTROL_SHA = "f53bfaad5a6b849398dce78bd7669c6d845f6bd886474a96ce71981c49464bc8"
DECISIONS = ("status", "initial_branches", "initial_arm_fits", "cavity_offered", "observations", "tracks")


def wall_and_decisions(result, stages):
    metrics = result["metrics"]
    return dict(original_stage_wall_s=dict(stages),
                stages={name: (result if name == "status" else metrics).get(name) for name in DECISIONS})


def disjoint(amounts, top_level):
    total = amounts["infer"]["inclusive_cpu_ns"]
    subsets = {label: amounts.get(label, {}).get("inclusive_cpu_ns", 0) for label in top_level}
    between = total - sum(subsets.values())
    if between < 0:
        raise ValueError("Inference's top-level clocks overlap")
    return subsets | {"between_ports": between}


TOP_LEVEL = (
    "scan_context", "rank", "initial_screen", "conservative", "history", "signed", "nomination", "cavity", "evidence",
)


@contextmanager
def attribution(audit):
    from leo.analysis.localization_v3 import conservative_recovery, family_cavity, history_policy, signed_context
    from leo.analysis.localization_v4.native_bound import NativeBound
    from tools import algo08_position
    from tools.pipeline_eval.variants import algo08_cavity_projection, v5_core, v5_screen_winner, v5_tiled_salvage

    infer = v5_core.infer
    ledger = Ledger()

    def measured(prepared, region, bound, stage_s, **kwargs):
        with ExitStack() as active:
            for owner, name, label in (
                (v5_core, "scan_context", "scan_context"),
                (v5_core, "ranked_initial_nodes", "rank"),
                (v5_screen_winner, "screen_nodes", "initial_screen"),
                (conservative_recovery, "conservative_recovery", "conservative"),
                (conservative_recovery, "fit_and_gate", "conservative_fit_and_gate"),
                (conservative_recovery, "salvage", "salvage"),
                (conservative_recovery, "repaired_fit", "salvage_initial_fit"),
                (v5_tiled_salvage, "fine_alternatives", "salvage_fine"),
                (conservative_recovery, "extend_associations", "conservative_extension"),
                (history_policy, "history_policy", "history"),
                (history_policy, "history_fit", "history_curved"),
                (history_policy, "linear_refit", "history_linear"),
                (history_policy, "confidence_for", "history_confidence"),
                (history_policy, "select_entries", "history_select_entries"),
                (history_policy, "validate_history", "history_validation"),
                (signed_context, "signed_context", "signed"),
                (signed_context, "refit", "signed_refit"),
                (family_cavity, "nominate_families", "nomination"),
                (family_cavity, "family_data", "nomination_calibration"),
                (algo08_cavity_projection, "held_times", "nomination_times"),
                (algo08_cavity_projection.SharedPhaseGrid, "__init__", "nomination_projection_setup"),
                (algo08_cavity_projection.SharedPhaseGrid, "__call__", "nomination_projection"),
                (algo08_cavity_projection.SharedPhaseGrid, "tabulate", "nomination_table_build"),
                (family_cavity, "coarse_phase_scores", "nomination_coarse"),
                (family_cavity, "candidate_prediction", "nomination_predict"),
                (family_cavity, "cavity_policy", "cavity"),
                (family_cavity, "fit_configuration", "cavity_configuration"),
                (algo08_position, "selected_packet", "evidence"),
                (algo08_position, "baseline_pair", "evidence_replay"),
                (algo08_position, "prepare_packet", "evidence_packet"),
                (NativeBound, "__call__", "likelihood"),
            ):
                active.enter_context(ledger.measure(owner, name, label))
            with ledger.scope("infer"):
                result = infer(prepared, region, bound, stage_s, **kwargs)
        audit["completed"].append(wall_and_decisions(result, stage_s))
        return result

    try:
        with patch.object(v5_core, "infer", measured):
            yield
    finally:
        audit["cpu_ns"] = dict(ledger.amounts)
        if audit["completed"]:
            audit["exclusive_inference_partition_cpu_ns"] = disjoint(ledger.amounts, TOP_LEVEL)


def worker(output):
    from aperture_trial import write

    binding = route.read(output/"study-binding.json")
    if (binding["driver_sha256"] != route.digest(HERE/Path(__file__).name)
            or binding["protocol_sha256"] != route.digest(HERE/"named-inference-budget-protocol.md")):
        raise ValueError("Observer sources changed after enrollment")
    original = route.exact_ports
    measurements = dict(completed=[])

    @contextmanager
    def ports(*args, **kwargs):
        with original(*args, **kwargs), attribution(measurements):
            yield

    try:
        with patch.object(route, "exact_ports", ports):
            route.worker("0316", output)
    finally:
        write(output/"inference-attribution.json", measurements)


def launch(output):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure

    machine = host()
    case = route.bind("0316")
    reference = route.resident_path(CONTROL/"result.json")
    if (route.digest(reference) != CONTROL_SHA or not route.read(reference)["exact"]
            or route.read(reference)["source_bindings"] != case["sources"]):
        raise ValueError("Expected the exact sealed 0316 control on the same sources")
    if route.resident_path(output.parent) != Path("/dev/shm") or output.exists():
        raise ValueError("Expected a fresh tmpfs output")
    _, refs = route.checked_catalogue(case, route.read(Path(case["request"])), TleArchiveReader, canonical_digest)
    residence = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(ref.path for ref in refs)], text=True))["fincore"]
    if len(residence) != len(refs) or any(row["res"] < row["size"] for row in residence):
        raise ValueError("A previously staged causal body is no longer fully resident")
    output.mkdir(mode=0o700)
    (output/"fonts").mkdir()
    (output/"tmp").mkdir()
    for file in (Path(case["stage"])/"fonts").glob("fontlist-*.json"):
        os.link(route.resident_path(file), output/"fonts"/file.name)
    command = ["/usr/bin/timeout", "--kill-after=2s", "55s", RELEASE/"venv/bin/python", "-IB", __file__, "worker", output]
    write(output/"binding.json", dict(input=case, machine=machine, command=list(map(str, command)),
          resident_bytes=sum(row["size"] for row in residence), resident_snapshots=len(refs)))
    write(output/"study-binding.json", dict(control=[str(reference), CONTROL_SHA],
          driver_sha256=route.digest(HERE/Path(__file__).name),
          protocol_sha256=route.digest(HERE/"named-inference-budget-protocol.md")))
    env = environment(output) | {"TMPDIR": str(output/"tmp"), "XDG_CACHE_HOME": str(output/"tmp")}
    write(output/"clock.json", measure(command, env, output/"candidate"))


def score(output):
    from aperture_trial import write
    from exact_named_route_score import verify

    verify("0316", output)
    observed = route.read(output/"result.json")
    original = route.read(CONTROL/"result.json")
    if (route.digest(CONTROL/"result.json") != CONTROL_SHA or not observed["exact"]
            or observed["ordered_owner_sha256"] != original["ordered_owner_sha256"]
            or observed["geography"] != original["geography"]):
        raise ValueError("The observer did not preserve the original exact science")
    audit = route.read(output/"inference-attribution.json")
    if len(audit["completed"]) != 1 or audit["cpu_ns"].get("infer", {}).get("calls") != 1:
        raise ValueError("This budget requires a single completed inference")
    write(output/"study-result.json", dict(attribution=audit, parity=observed["parity"],
          clocks=dict(original=original["clocks"], observed=observed["clocks"]["candidate"]),
          solve=dict(original=original["artifacts"]["candidate"]["worker"]["solve"],
                     observed=observed["artifacts"]["candidate"]["worker"]["solve"]),
          science={key: observed[key] for key in ("geography", "ordered_owner_sha256")},
          bindings={name: route.digest(output/name) for name in
                    ("binding.json", "study-binding.json", "clock.json", "result.json", "inference-attribution.json")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "score"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"launch": launch, "worker": worker, "score": score}[args.action](args.output)
