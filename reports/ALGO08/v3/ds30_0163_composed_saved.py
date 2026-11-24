"""Transfer the clean DS30-0359 composition to the original DS30-0163 packet."""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from ds30_0359_cairo_saved import digest, read


@dataclass(frozen=True)
class Transfer:
    case: str
    original: Path
    control_pin: str
    seal_pin: str
    ready: Path
    ready_pin: str
    job_pin: str
    archive_bytes: int

    @property
    def protocol(self):
        return HERE / (self.case.lower() + "-composed-saved-protocol.md")


TRANSFER_0163 = Transfer(
    "DS30-0163", Path("/dev/shm/leo-v3-combined-0163-blind02"),
    "76121104353dfad92fe5f325a57bf0f8bcc10adc915a44093a3182970eb9c40e",
    "4bbdf56939b61b106603a2687865f2fd981ce31a475ef285e0627d6e94856541",
    Path("/dev/shm/leo-v3-ds30-0163-ready01"),
    "dfbcde4feb942fc95c2ec8ff9d26fe30fe238bb570413dd03b19b97de11a7cd7",
    "3b79aefb7f540ec55193a5e54b3ee57cb60f0a27a3371b64c2e5504be15be7d3", 91_146_270,
)
TRANSFER_0173 = Transfer(
    "DS30-0173", Path("/dev/shm/leo-v3-combined-0173-blind01"),
    "e2a7eb8a10886c3de720e1ab97d7efbdfd706161b67f06aa6249417083c4c180",
    "5d0986b9ca7feb19e209044dada76d62d933f5851eae4fd86a9a872f8a173d3b",
    Path("/dev/shm/leo-v3-combined-0173-blind01-ready"),
    "441a1fc5a3cda13031d25e5d0fd06725f8d087836bc70b1e9c7583f21d693627",
    "13051f25aac57199e2c7de21b811f205cff3eb12056eaab32bc832dad2e59cec", 91_144_362,
)
TRANSFERS = {transfer.case: transfer for transfer in (TRANSFER_0163, TRANSFER_0173)}
DONOR = Path("/dev/shm/leo-v3-0359-composed-saved-result01")
DONOR_PIN = "8cf7d2053ae88597c390739990c849e33c755412d86303eafd7cae5170251166"
DONOR_ADMISSION = "a37356faa7f27d355edbd60141bccc9156ddac5a106699cfb3f643e74ca43842"
HEADROOM = 128 * 1024**2  # Prior complete positive output used 18 MiB.


def donor_sources():
    from empty_bootstrap import checked
    from ds30_0359_composed_saved import sources

    candidate = json.loads(checked(DONOR / "result.json", DONOR_PIN))
    reference = json.loads(checked(DONOR / "admission.json", DONOR_ADMISSION))
    active = sources()
    if (not candidate["qualified"] or candidate["admission"] != reference
            or any(reference[key] != value for key, value in active.items())):
        raise ValueError("The active renderer and predictor sources must equal the actual 0359 run")
    return active, reference


def original_entry(transfer, action, root=None):
    import ds30_0359_composed_saved as composed

    with patch.multiple(composed, READY=transfer.ready, READY_PIN=transfer.ready_pin, JOB_PIN=transfer.job_pin):
        if action == "probe":
            return composed.probe()
        book = read(root / "admission.json")
        if (book["case"] != transfer.case or book["transfer_code_sha256"] != digest(Path(__file__))
                or book["transfer_protocol_sha256"] != digest(transfer.protocol)
                or book["job_sha256"] != transfer.job_pin or book["donor_result_sha256"] != DONOR_PIN):
            raise ValueError("The launched case differs from the frozen one-recording transfer")
        return composed.worker(root)


def controls(transfer):
    from empty_bootstrap import checked

    prior = json.loads(checked(transfer.original / "result.json", transfer.control_pin))
    checks = {k: v for k, v in prior["checks"].items() if k != "equal_terminal"}
    if prior["case"] != transfer.case or prior["prediction_seal_sha256"] != transfer.seal_pin or not all(checks.values()):
        raise ValueError("Expected the complete sealed original matched-input comparisons")
    return prior


def launch(transfer, root):
    import ds30_0359_composed_saved as composed
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    import combined_successor_0289 as combined
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, checked, clock, now
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from reports.ALGO08.v3 import ds30_0163_combined as original
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    began = now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs publication root")
    filesystem = os.statvfs(root.parent)
    free = filesystem.f_bavail * filesystem.f_frsize
    if free < HEADROOM:
        raise ValueError("Insufficient tmpfs headroom for the expected 18 MiB publication")
    prior = controls(transfer)
    sealed = json.loads(checked(transfer.original / "prediction-seal.json", transfer.seal_pin))
    old = prior["admission"]
    active, donor = donor_sources()
    machine, release = host(), verified_v3(NAMED_V3)
    pins, libraries = original.pinned_sources(), combined.admitted_libraries()
    ready = original.ready(check_assignment=False, job_root=transfer.ready, admission_pin=transfer.ready_pin,
                           job_pin=transfer.job_pin)
    if (old["machine"] != machine or old["installed_release"] != release or donor["installed_release"] != release
            or old["job_sha256"] != transfer.job_pin or old["ready_admission_sha256"] != transfer.ready_pin
            or old["sources"] != pins or donor["sources"] != pins or old["libraries"] != libraries
            or donor["libraries"] != libraries or sealed != output_seal(transfer.original)):
        raise ValueError("The identical scientific build, previous controls or shared native assets changed")
    bound, req = load_job(resident_path(transfer.ready / "job.json"), transfer.job_pin)
    _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    if (ready["assignment"]["case"] != transfer.case or len(refs) != 51
            or sum(ref.byte_size for ref in refs) != transfer.archive_bytes):
        raise ValueError("The original signed causal scope changed")
    paths = [*(ref.path for ref in refs), *map(Path, bound["packets"]), *map(Path, libraries)]
    cache = resident(paths)
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts", "routed"):
        (root / name).mkdir()
    for path in (transfer.ready / "fonts").glob("fontlist-*.json"):
        os.link(resident_path(path), root / "fonts" / path.name)
    write(root / "routed/binding.json", {"input": bound})
    source = Path(__file__).resolve()
    argv = [str(RELEASE / "venv/bin/python"), "-IB", str(source), "--case", transfer.case]
    prefix = ["/usr/bin/timeout", "--kill-after=2s"]
    command = [*prefix, "45s", *argv, "worker", str(root)]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    setup = clock(began)
    before, children = now(), resource.getrusage(resource.RUSAGE_CHILDREN)
    probe = subprocess.run([*prefix, "15s", *argv, "probe"], env=env, capture_output=True, text=True, check=False)
    smoke = clock(before)
    end = resource.getrusage(resource.RUSAGE_CHILDREN)
    smoke["cpu_s"] += end.ru_stime + end.ru_utime - children.ru_stime - children.ru_utime
    write(root / "admission.json", dict(case=transfer.case, command=command, sources=pins, libraries=libraries,
          protocol_sha256=digest(composed.PROTOCOL), transfer_protocol_sha256=digest(transfer.protocol),
          transfer_code_sha256=digest(source), job_sha256=transfer.job_pin, ready_sha256=transfer.ready_pin,
          original_comparators_sha256=transfer.control_pin, original_comparators_seal_sha256=transfer.seal_pin,
          donor_result_sha256=DONOR_PIN, donor_admission_sha256=DONOR_ADMISSION, machine=machine,
          installed_release=release, resident=cache, tmpfs_free_bytes_at_admission=free,
          archive_bodies=len(refs), archive_bytes=sum(ref.byte_size for ref in refs), setup=setup,
          smoke=dict(clock=smoke, exit_code=probe.returncode, stdout=probe.stdout, stderr=probe.stderr),
          waveform_reads=0, backing_archive_reads=0, planned_candidate_children=1, **active))
    probe.check_returncode()
    verified = json.loads(probe.stdout)
    if verified != dict(composed_ready=True, early_leo_import=False, guarded_worker_available=True, worker_available=True):
        raise ValueError("The same isolated original loader and native decoder must pass")
    write(root / "routed/clock.json", measure(command, env, root / "routed/candidate"))
    write(root / "prediction-seal.json", output_seal(root))


def route_signature(document):
    solved, = document["solves"]
    lean, = solved["lean_attempts"]
    return dict(choice={k: solved["choice"][k] for k in ("route", "reason")},
                ranks={k: solved["two_centre_rank"][k] for k in ("ranked_nodes", "distinct_finalists", "paid_centres")},
                handoff={k: v for k, v in solved["nomination_handoff"].items() if not k.endswith("_ns")},
                decision=lean["decision"],
                cold=(lean["cold"]["routing"], lean["cold"]["branch"]),
                used_named_finish=bool(solved["lean_final_fit"]), inference_calls=solved["inference_calls"])


def own_endpoint_scores(grid):
    return {arm: next(p["scores"][arm].hex() for p in grid["points"]
                      if [p["east_km"], p["north_km"]] == coordinates)
            for arm, coordinates in grid["endpoints"].items()}


def score(transfer, root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from ds30_0359_composed_score import grid_evidence
    from ds30_0359_predictive_score import image_identity
    from history_risk_cairo_physical import clean
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect

    seal = root / "prediction-seal.json"
    if read(seal) != output_seal(root):
        raise ValueError("Candidate products changed after the prediction seal")
    archive = controls(transfer)
    timing, adoption = read(root / "routed/clock.json"), read(root / "admission.json")
    historical = {mode: row["clock"] for mode, row in archive["jobs"].items()}
    result = dict(case=transfer.case, qualified=False, process=timing, controls=historical, admission=adoption,
                  prediction_sha256=digest(seal), measured_children=1, waveform_reads=0,
                  historical_admission=archive["paid_setup_and_time"], historical_geography=archive["geographic"])
    if timing["exit_code"]:
        write(root / "result.json", result | {"status": "candidate_failed"})
        return
    bound, request = load_job(transfer.ready / "job.json", transfer.job_pin)
    directory = root / "routed/candidate"
    receipt = read(directory / "worker.json")["receipt"]
    current = inspect(directory, transfer.case + "-composed", receipt, timing, request, native_sha=request["native_sha256"],
                      windows=bound["issued"], admitted=bound["admitted"], audit_name="worker.json")
    ordinary = archive["jobs"]["routed"]["publication"]
    installed = archive["jobs"]["installed"]["publication"]
    previous = FastStandardAnalysisStore(transfer.original / "routed/candidate").position_grid(ordinary["science"]["receipt"]["run_id"])
    grid = FastStandardAnalysisStore(directory).position_grid(receipt["run_id"])
    grids, images = grid_evidence(previous, grid), image_identity(ordinary["figures"], current["figures"])
    telemetry, ports = read(root / "composition.json"), read(directory / "ports.json")
    agg, png, predictive = (telemetry[key] for key in ("agg", "native_png", "predictive"))
    native_grid = read(root / "routed/combined-grid.json")
    route = route_signature(read(root / "routed/risk-route.json"))
    checks = dict(terminal=ordinary["terminal"] == current["terminal"],
        both_arms=ordinary["science"]["arms"] == current["science"]["arms"],
        owners=ordinary["selected_rows"] == current["selected_rows"] and all(
            (installed["selected_rows"][arm] == rows) == archive["owner_changes"][arm]["identical_ordered_rows"]
            for arm, rows in current["selected_rows"].items()),
        graph=clean(ports["graph"]) == clean(archive["candidate_traces"]["ports"]["graph"])
              and ordinary["worker"]["graph_proof"] == current["worker"]["graph_proof"],
        route=route == route_signature(archive["candidate_traces"]["risk-route.json"]),
        path=ordinary["sidecars"]["path"] == current["sidecars"]["path"],
        complete_grid=grid["complete"] and grid["evaluated_points"] == 179 and all(item["qualified"] for item in grids.values()),
        endpoints=own_endpoint_scores(grid) == own_endpoint_scores(previous), figures=len(images) == 8 and all(images.values()),
        native_grid=(native_grid["assembly"]["assembly_calls"], native_grid["projection"]["native_selection"]) == (356, 356),
        agg=(agg.get("figures"), agg.get("axes"), agg.get("first_restores_elided")) == (2, 16, 2)
            and "ordinary_fallback" not in agg,
        native_png=(png["native"], png["fallback"], ports["png"]["verified"], ports["png"]["reused"]) == (8,0,8,8),
        predictive=(predictive.get("grid_calls"), predictive.get("reduced_calls")) == (1,356)
            and not predictive.get("original_fallback_calls") and not predictive.get("unsupported_binding"))
    costs = {}
    for metric in ("elapsed_s", "cpu_s"):
        setup = adoption["setup"][metric] + adoption["smoke"]["clock"][metric]
        baseline, routed = historical["installed"][metric], historical["routed"][metric]
        child = timing[metric]
        costs[metric] = dict(installed=baseline, earlier_routed=routed, child=child, setup=setup, charged=child+setup,
                             saved_vs_routed=routed-child, speedup=baseline/child, remaining_to_half=child-baseline/2)
    write(root / "result.json", result | dict(qualified=all(checks.values()), checks=checks, cost=costs,
          candidate=current, grid=grids, images=images, telemetry=telemetry, route=route, native_grid=native_grid,
          renderer=read(root / "routed/render-usage.json"), prior_publications=archive["publication_clocks"],
          prior_owner_comparison={arm: {key: value for key, value in row.items() if not isinstance(value, list)}
                                  for arm, row in archive["owner_changes"].items()}))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=TRANSFERS, default=TRANSFER_0163.case)
    parser.add_argument("action", choices=("probe", "worker", "launch", "score"))
    parser.add_argument("root", type=Path, nargs="?")
    args = parser.parse_args()
    transfer = TRANSFERS[args.case]
    if args.action in ("probe", "worker"):
        original_entry(transfer, args.action, args.root)
    else:
        {"launch": launch, "score": score}[args.action](transfer, args.root)
