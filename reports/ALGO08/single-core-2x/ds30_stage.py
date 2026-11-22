"""Run or verify one nested DS30 single-core qualification stage."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
import json
from math import isfinite
from pathlib import Path
from statistics import median
from types import SimpleNamespace

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification import paired_publication as pair
from tools.pipeline_eval.qualification.ds30_full_inputs import BULK, INPUTS, OUT, WORK
from tools.pipeline_eval.qualification.reverse_glrt_reference import read_bound
from tools.pipeline_eval.qualification.score_paired_holdout import pinned
from tools.pipeline_eval.scoring import ARMS, distance_km, distribution, thresholds

from .audit_shared_publication import audit


PANEL = Path(__file__).resolve().parents[1] / "ds30-optimized/panel.json"
PANEL_SHA256 = "ce2b293c67295f91c927ab35739c73d5bf73c7ed9708169861bdf3dbf1394379"
LOCK_SHA256 = "932f149caf053c835d80057d74489089d63476fcbd0511ababf18d8b562769c4"
REFERENCE_SHA256 = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
BASELINE_SHA256 = "fd5e2cd3e220998a48219d7f8a7f0710c0b41269906da3b3c6ad0e49b6f92370"
BASELINE_DETECTOR = "sha256:f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809"
EVIDENCE_FIELDS = ("raw_authority", "arms", "owners", "reason", "artifacts", "scientific_digests")


@dataclass(frozen=True)
class Assignment:
    name: str
    rank: int
    recording: Path
    region: dict
    archive: Path
    snapshots_sha256: str
    session: str
    raw_authority: str
    windows: int
    visits: int

    @property
    def order(self):
        return ["candidate", "baseline"] if self.rank % 2 else ["baseline", "candidate"]


def read(path):
    return json.loads(path.read_bytes())


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def frozen_assignments(size, station):
    panel = pinned(PANEL, PANEL_SHA256)["cases"]
    lock = pinned(OUT / "prediction-lock.json", LOCK_SHA256)
    select = import_module("reports.ALGO08.ds30-optimized.panels").select_panel
    roster = select(lock["predictions"], "triage")
    if [row["case"] for row in roster] != panel:
        raise ValueError("Nested panel differs from the frozen DS30 order")
    assignments = []
    for rank, row in enumerate(roster[:size], 1):
        name = row["case"]
        case = pinned(WORK / "bindings" / (name + ".json"), row["input_binding_sha256"])["case"]
        request = read_bound(case["request"])
        job = request["job"]
        original, = case["regions"]
        archive = INPUTS / name / "tle"
        if (case["id"] != name or case["raw_authority"] != row["raw_authority"]
                or request["role"] != "baseline" or job["evaluation_reference"] is not None
                or job["scan_identities"] != [case["session_id"]] or Path(job["tle_root"]) != archive
                or station != dict(center=job["search_center"], screen_center=job["screen_center"],
                                   width_km=original.get("width_km", 25.))
                or original["center"] != station["center"]):
            raise ValueError(f"Incorrect frozen recording, orbit archive or region for {name}")
        segments = [BULK / s["path"] for s in case["recording"]["segments"]]
        recording, = {segment.parent.parent for segment in segments}
        assignments.append(Assignment(name, rank, recording, station, archive,
                                      canonical_digest(request["causal_snapshots"]), case["session_id"],
                                      case["raw_authority"], case["recording"]["window_count"], case["valid_visits"]))
    if len({a.raw_authority for a in assignments}) != size:
        raise ValueError("Frozen prefix repeats a raw recording")
    return assignments


def verify_build(candidate, config, expected):
    spec = read(config)
    if canonical_digest(spec).removeprefix("sha256:") != expected.removeprefix("sha256:"):
        raise ValueError("Candidate specification differs from its supplied digest")
    if file_sha(pair.BASELINE) != BASELINE_SHA256:
        raise ValueError("Pinned baseline launcher changed")
    pair.verify_sources(candidate, spec["sources"])
    pins = {spec["detector"]: spec["detector_sha256"]}
    for entry in spec.values():
        if isinstance(entry, dict) and "library" in entry:
            pins[entry["library"]] = entry["sha256"]
    for filename, digest in pins.items():
        if file_sha(Path(filename)) != digest:
            raise ValueError(f"Frozen candidate binary changed: {filename}")
    return spec


def verify_pair(path, assigned, candidate, spec, cpu):
    original = path.read_bytes()
    data = json.loads(original)
    if "failure" in data:
        return dict(state="failed", reason=data["failure"])
    digest = canonical_digest(spec)
    if (data["candidate_specification_digest"] != digest or data["candidate_specification"] != spec
            or read(path.parent / "candidate-config.json") != spec):
        raise ValueError("Frozen candidate specification does not match the recorded pair")
    if (data["cpu"] != cpu or data["order"] != assigned.order
            or data["recording"] != str(assigned.recording.resolve())
            or Algo08Region.parse(read(Path(data["region"]))).document() != assigned.region):
        raise ValueError("CPU, pair order, recording or offer differs from its assignment")
    if set(data["runs"]) != {"baseline", "candidate"}:
        raise ValueError("Pair must contain exactly one run for each arm")
    for label, launcher in (("baseline", pair.BASELINE), ("candidate", candidate)):
        run = data["runs"][label]
        receipt = run["receipt"]
        if (run["launcher"] != str(launcher.resolve()) or run["raw_authority"] != assigned.raw_authority
                or receipt["session_id"] != assigned.session or receipt["window_count"] != assigned.windows
                or receipt["region"] != assigned.region or receipt["counts"] != {
                    "processed": assigned.visits, "invalid_capture": assigned.windows - assigned.visits,
                    "skipped_fast_score": 0}):
            raise ValueError(f"{label} launcher, raw authority or terminal receipt differs from the assignment")
        if any(type(run[metric]) not in (int, float) or not isfinite(run[metric]) or run[metric] <= 0
               for metric in ("elapsed_s", "cpu_s")):
            raise ValueError(f"Invalid positive timings for {label}")
        restored = pair.evidence(path.parent / label, receipt, 0, read_only=True)
        if any(restored[key] != run[key] for key in EVIDENCE_FIELDS):
            raise ValueError(f"{label} pair receipt differs from its persisted publication")
    before, after = (data["runs"][label] for label in ("baseline", "candidate"))
    if data["elapsed_ratio"] != after["elapsed_s"] / before["elapsed_s"]:
        raise ValueError("Recorded pair elapsed ratio does not match its timings")
    measured = audit(path, lossless_png=spec.get("rendering") == "lossless-raster", read_only=True, bind_native=True)
    detectors = dict(baseline=BASELINE_DETECTOR, candidate="sha256:" + spec["detector_sha256"])
    if measured["session"] != assigned.session or measured["detector_sha256"] != detectors:
        raise ValueError("Audit consumed the wrong session or detector build")
    if path.read_bytes() != original:
        raise ValueError("Pair receipt changed during its artifact audit")
    audit_digest = canonical_digest(dict(pair_sha256=sha256(original).hexdigest(), audit=measured))
    evidence = dict(audit_sha256=audit_digest, pair_sha256=sha256(original).hexdigest(),
                    audit=dict(probe_rows=measured["probe_rows"], selected=measured["selected"],
                               figures=len(measured["image_dimensions"])),
                    decision=before["receipt"]["decision"],
                    elapsed_s={k: v["elapsed_s"] for k, v in data["runs"].items()},
                    cpu_s={k: v["cpu_s"] for k, v in data["runs"].items()},
                    arms={k: v["arms"] for k, v in data["runs"].items()},
                    raw_authority=assigned.raw_authority, actual_order=data["order"],
                    expected_archive=str(assigned.archive))
    if "archive" not in data:
        return dict(evidence, state="development", reason="Pair lacks recorded causal archive identity")
    expected_archive = dict(root=str(assigned.archive.resolve()), snapshots_sha256=assigned.snapshots_sha256)
    if data["archive"] != expected_archive or pair.archive_identity(assigned.archive) != expected_archive:
        raise ValueError("Recorded or current causal archive differs from the frozen assignment")
    return dict(evidence, state="verified", archive=data["archive"])


def inventory(workspace, assignments, candidate, spec, cpu):
    cases = []
    for assigned in assignments:
        directory = workspace / assigned.name
        path = directory / "pair.json"
        try:
            if path.is_file():
                status = verify_pair(path, assigned, candidate, spec, cpu)
            elif directory.exists() or directory.is_symlink():
                status = dict(state="failed", reason="Attempt directory has no sealed pair receipt")
            else:
                status = dict(state="missing")
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
            status = dict(state="invalid", reason=str(error))
        cases.append(dict(case=assigned.name, rank=assigned.rank, expected_order=assigned.order, **status))
    coverage = {state: [row["case"] for row in cases if row["state"] == state]
                for state in ("verified", "missing", "failed", "invalid", "development")}
    return dict(assigned=len(cases), candidate_specification_digest=canonical_digest(spec), cpu=cpu,
                coverage=coverage, cases=cases)


def next_case(stage, requested):
    coverage = stage["coverage"]
    if coverage["failed"] or coverage["invalid"] or coverage["development"]:
        raise ValueError("The stage contains an existing unqualified attempt")
    if not coverage["missing"]:
        raise ValueError("Every assigned case already has a verified pair")
    next_missing = coverage["missing"][0]
    if requested is not None and requested != next_missing:
        raise ValueError(f"The next unmeasured assigned case is {next_missing}")
    return next_missing


def run_next(workspace, assignments, stage, requested, candidate, config, region_file):
    name = next_case(stage, requested)
    assigned = next(case for case in assignments if case.name == name)
    pair.run_pair(SimpleNamespace(recording=assigned.recording, region=region_file,
                                  archive=assigned.archive, archive_inventory_sha256=assigned.snapshots_sha256,
                                  output=workspace / name, baseline=pair.BASELINE, candidate=candidate,
                                  candidate_config=config, blind_panel=None, first=assigned.order[0],
                                  cpu=stage["cpu"], timeout=1200))


def score(stage):
    cases = stage["cases"]
    if len(stage["coverage"]["verified"]) != stage["assigned"]:
        return dict(stage, elapsed_gates=None, position=None)
    times = [(row["elapsed_s"]["baseline"], row["elapsed_s"]["candidate"]) for row in cases]
    paired = median(after / before for before, after in times)
    summed = sum(after for _, after in times) / sum(before for before, _ in times)
    truth = pinned(OUT / "reference-audit.json", REFERENCE_SHA256)["cases"]
    refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
            for r in truth if r["authority_eligible"]}
    position = {}
    for label in ("baseline", "candidate"):
        position[label] = {}
        for arm in ARMS:
            errors = [distance_km(row["arms"][label][arm]["latlon"], refs[row["case"]]) for row in cases]
            position[label][arm] = dict(error_km=distribution(errors), within_km_count=thresholds(errors),
                                        assigned=len(cases))
    gates = dict(median_candidate_over_baseline=paired, summed_candidate_over_baseline=summed,
                 median_pass=paired <= .5, summed_pass=summed <= .5, passed=max(paired, summed) <= .5)
    return dict(stage, elapsed_gates=gates, position=position)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "inventory", "score"))
    for name in ("workspace", "candidate", "config"):
        parser.add_argument(name, type=Path)
    parser.add_argument("spec_digest")
    parser.add_argument("--size", type=int, choices=(4, 16), default=4)
    parser.add_argument("--case", help="Require the next assigned case to have this DS30 ID")
    args = parser.parse_args()
    if args.case and args.action != "run":
        parser.error("--case applies to run")
    spec = verify_build(args.candidate, args.config, args.spec_digest)
    region_file = pair.BASELINE.parent / "station/region.json"
    assignments = frozen_assignments(args.size, Algo08Region.parse(read(region_file)).document())
    stage = inventory(args.workspace, assignments, args.candidate, spec, cpu=2)
    if args.action == "run":
        run_next(args.workspace, assignments, stage, args.case, args.candidate, args.config, region_file)
        stage = inventory(args.workspace, assignments, args.candidate, spec, cpu=2)
    print(json.dumps(score(stage) if args.action == "score" else stage, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
