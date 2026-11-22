"""Run or verify one nested DS30 single-core qualification stage."""

import argparse
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
import json
from math import isfinite
from pathlib import Path
from types import SimpleNamespace

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification import cache_residency
from tools.pipeline_eval.qualification import paired_publication as pair
from tools.pipeline_eval.qualification.ds30_full_inputs import BULK, INPUTS, OUT, WORK
from tools.pipeline_eval.qualification.reverse_glrt_reference import read_bound
from tools.pipeline_eval.qualification.score_paired_holdout import elapsed_ratios, face_clearance_km, pinned
from tools.pipeline_eval.scoring import ARMS, distance_km, distribution, thresholds

from .audit_shared_publication import audit
from .compare_publications import compare


PANEL = Path(__file__).resolve().parents[1] / "ds30-optimized/panel.json"
PANEL_SHA256 = "ce2b293c67295f91c927ab35739c73d5bf73c7ed9708169861bdf3dbf1394379"
LOCK_SHA256 = "932f149caf053c835d80057d74489089d63476fcbd0511ababf18d8b562769c4"
REFERENCE_SHA256 = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
BASELINE_SHA256 = "fd5e2cd3e220998a48219d7f8a7f0710c0b41269906da3b3c6ad0e49b6f92370"
BASELINE_DETECTOR = "sha256:f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809"
CONDITIONAL_RESIDUAL = "sha256:65b664d49a5e91baf1fb593c19808f4cf32921d0c17ffe6145d61189570089c6"
Q15_COLLAPSED_REPAIR = "sha256:a32a945a1e6d9e602f02fa636e83761d47e2992d7da4b0c4aa55eba6927cd9ca"
FULL_PHASE_SIGNED = "sha256:50d30065095e5a354ec589c31b615a0d1d38194b72335864431e3f63be403879"
COVARIANCE_POSTERIOR = "sha256:375895c3afda3abd3a916f90bbd63248b5e792f70c78a0e4f136c9bf1a79d423"
SCREENED_TILED = "sha256:c803a30087a9c23e00aa4fa30e6a2b87a4d682cd941a3f3d870ce9277dbc90d6"
RESTORED_SCOUT_GRAPH = "sha256:ad417aaa51a49edf1a36aca571683bbc0479317c06b821030373656461a28acd"
TERMINAL_FRAME_PLANE = "sha256:977e7dd61c23622cc05365f0a7743a0042a7edd590d88173faeace8590ca8fe3"
WRAPPED_SPECTRAL = "sha256:445744b4401d14d42a62130dca85882fd9062eb32627a9046e62205650dddb28"
APPROXIMATE_MODES = ("conditional-residual", "full-scan-signed", "full-scan-screened")
EVIDENCE_FIELDS = ("raw_authority", "arms", "owners", "reason", "artifacts", "scientific_digests")
BUILDS = ("baseline", "candidate")


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
    segment_manifests: tuple[tuple[Path, str], ...] = ()

    @property
    def order(self):
        return ["candidate", "baseline"] if self.rank % 2 else ["baseline", "candidate"]


def read(path):
    return json.loads(path.read_bytes())


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def comparison_mode(spec):
    if spec.get("solver") == "screened-tiled-finish":
        if canonical_digest(spec) not in (SCREENED_TILED, RESTORED_SCOUT_GRAPH, TERMINAL_FRAME_PLANE, WRAPPED_SPECTRAL):
            raise ValueError("Only the frozen screened-tiled candidate may use approximate comparison")
        return "full-scan-screened"
    if spec.get("schedule") == "all" and spec.get("solver") == "collapsed-signed":
        if canonical_digest(spec) not in (FULL_PHASE_SIGNED, COVARIANCE_POSTERIOR):
            raise ValueError("Only the frozen full-scan signed candidate may use approximate comparison")
        return "full-scan-signed"
    if spec.get("schedule") == "conditional-residual":
        if canonical_digest(spec) not in (CONDITIONAL_RESIDUAL, Q15_COLLAPSED_REPAIR):
            raise ValueError("Only the frozen conditional-residual candidates may use approximate comparison")
        return "conditional-residual"
    return "exact"


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
        manifests = tuple((BULK / s["path"], "sha256:" + s["sha256"])
                          for s in case["recording"]["segments"])
        recording, = {segment.parent.parent for segment, _ in manifests}
        assignments.append(Assignment(name, rank, recording, station, archive,
                                      canonical_digest(request["causal_snapshots"]), case["session_id"],
                                      case["raw_authority"], case["recording"]["window_count"],
                                      case["valid_visits"], manifests))
    if len({a.raw_authority for a in assignments}) != size:
        raise ValueError("Frozen prefix repeats a raw recording")
    return assignments


def verify_build(candidate, config, expected):
    spec = read(config)
    if canonical_digest(spec).removeprefix("sha256:") != expected.removeprefix("sha256:"):
        raise ValueError("Candidate specification differs from its supplied digest")
    comparison_mode(spec)
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


def approximate_audit(path):
    measured = compare(path)
    before, after = (measured[name] for name in BUILDS)
    baseline_figures, candidate_figures = set(before["figures"]), set(after["figures"])
    return measured, dict(
        probe_rows={name: measured[name]["probe_rows"] for name in BUILDS},
        selected={key: measured[key] for key in ("selected_common", "selected_lost", "selected_added")},
        decisions={name: measured[name]["decision"] for name in BUILDS},
        reasons={name: measured[name]["reason"] for name in BUILDS},
        owners_equal={arm: before["owners"].get(arm) == after["owners"].get(arm) for arm in ARMS},
        scientific_evidence_equal={key: before["scientific_digests"].get(key) == after["scientific_digests"].get(key)
                                   for key in ("grid", "path")},
        figures_changed=sorted(name for name in baseline_figures & candidate_figures
                               if not measured["same_rendered_figures"][name]),
        figures_added=sorted(candidate_figures - baseline_figures),
        figures_lost=sorted(baseline_figures - candidate_figures),
        displacement_km=measured["displacement_km"],
    )


def verify_pair(path, assigned, candidate, spec, cpu):
    original = path.read_bytes()
    data = json.loads(original)
    if "failure" in data:
        return dict(state="failed", reason=data["failure"])
    mode = comparison_mode(spec)
    digest = canonical_digest(spec)
    if (data["candidate_specification_digest"] != digest or data["candidate_specification"] != spec
            or read(path.parent / "candidate-config.json") != spec):
        raise ValueError("Frozen candidate specification does not match the recorded pair")
    if (data["cpu"] != cpu or data["order"] != assigned.order
            or data["recording"] != str(assigned.recording.resolve())
            or Algo08Region.parse(read(Path(data["region"]))).document() != assigned.region):
        raise ValueError("CPU, pair order, recording or offer differs from its assignment")
    if set(data["runs"]) != set(BUILDS):
        raise ValueError("Pair must contain exactly one run for each build")
    cache = data.get("cache_observation")
    if cache is not None and (not assigned.segment_manifests
            or cache["manifests"] != cache_residency.manifest_pins(assigned.segment_manifests)
            or set(cache["arms"]) != set(BUILDS)):
        raise ValueError("Cache observation differs from the assigned recording or arms")
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
        if "input_blocks" in run and (type(run["input_blocks"]) is not int or run["input_blocks"] < 0):
            raise ValueError(f"Invalid filesystem input block count for {label}")
        if mode == "exact":
            restored = pair.evidence(path.parent / label, receipt, 0, read_only=True)
            if any(restored[key] != run[key] for key in EVIDENCE_FIELDS):
                raise ValueError(f"{label} pair receipt differs from its persisted publication")
    before, after = (data["runs"][label] for label in BUILDS)
    if data["elapsed_ratio"] != after["elapsed_s"] / before["elapsed_s"]:
        raise ValueError("Recorded pair elapsed ratio does not match its timings")
    if mode in APPROXIMATE_MODES:
        measured, summary = approximate_audit(path)
        actual_detectors = {name: measured[name]["detector_sha256"] for name in BUILDS}
    else:
        measured = audit(path, lossless_png=spec.get("rendering") == "lossless-raster", read_only=True, bind_native=True)
        actual_detectors = measured["detector_sha256"]
        summary = dict(probe_rows=measured["probe_rows"], selected=measured["selected"],
                       figures=len(measured["image_dimensions"]))
    detectors = dict(baseline=BASELINE_DETECTOR, candidate="sha256:" + spec["detector_sha256"])
    if measured["session"] != assigned.session or actual_detectors != detectors:
        raise ValueError("Audit consumed the wrong session or detector build")
    if path.read_bytes() != original:
        raise ValueError("Pair receipt changed during its artifact audit")
    audit_digest = canonical_digest(dict(pair_sha256=sha256(original).hexdigest(), audit=measured))
    evidence = dict(audit_sha256=audit_digest, pair_sha256=sha256(original).hexdigest(),
                    audit=summary,
                    elapsed_s={k: v["elapsed_s"] for k, v in data["runs"].items()},
                    cpu_s={k: v["cpu_s"] for k, v in data["runs"].items()},
                    input_blocks={k: v.get("input_blocks") for k, v in data["runs"].items()},
                    arms={k: v["arms"] for k, v in data["runs"].items()},
                    raw_authority=assigned.raw_authority, actual_order=data["order"],
                    expected_archive=str(assigned.archive))
    if mode in APPROXIMATE_MODES:
        evidence["region"] = assigned.region
    else:
        evidence["decision"] = before["receipt"]["decision"]
    if cache is not None:
        evidence["cache_observation"] = cache
    if "archive" not in data:
        return dict(evidence, state="development", reason="Pair lacks recorded causal archive identity")
    expected_archive = dict(root=str(assigned.archive.resolve()), snapshots_sha256=assigned.snapshots_sha256)
    if data["archive"] != expected_archive or pair.archive_identity(assigned.archive) != expected_archive:
        raise ValueError("Recorded or current causal archive differs from the frozen assignment")
    return dict(evidence, state="verified", archive=data["archive"])


def inventory(workspace, assignments, candidate, spec, cpu):
    mode = comparison_mode(spec)
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
                coverage=coverage, cases=cases, comparison=mode, geographic_confirmation=False)


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


def run_next(workspace, assignments, stage, requested, candidate, config, region_file,
             *, cache_library=None):
    name = next_case(stage, requested)
    assigned = next(case for case in assignments if case.name == name)
    pair.run_pair(SimpleNamespace(recording=assigned.recording, region=region_file,
                                  archive=assigned.archive, archive_inventory_sha256=assigned.snapshots_sha256,
                                  output=workspace / name, baseline=pair.BASELINE, candidate=candidate,
                                  candidate_config=config, blind_panel=None, first=assigned.order[0],
                                  cache_library=cache_library, cache_manifests=assigned.segment_manifests,
                                  cpu=stage["cpu"], timeout=1200))


def local_quality(cases, refs):
    sites = defaultdict(list)
    for row in cases:
        sites[refs[row["case"]]].append(row)
    summaries = []
    for site, rows in sorted(sites.items()):
        times = [(r["elapsed_s"]["baseline"], r["elapsed_s"]["candidate"]) for r in rows]
        paired, summed = elapsed_ratios(times)
        summary = dict(site=site, assigned=len(rows), median_elapsed_ratio=paired, summed_elapsed_ratio=summed,
                       arms={})
        containing = {r["case"] for r in rows if face_clearance_km(r["region"], site) >= 0}
        for arm in ARMS:
            errors = {r["case"]: tuple(distance_km(r["arms"][name][arm]["latlon"], site) for name in BUILDS)
                      for r in rows}
            fixes = {name: {case for case, value in errors.items() if value[i] is not None}
                     for i, name in enumerate(BUILDS)}
            lost, added = fixes["baseline"] - fixes["candidate"], fixes["candidate"] - fixes["baseline"]
            retained = fixes["baseline"] & fixes["candidate"]
            lost_containing, added_false = sorted(lost & containing), sorted(added - containing)
            stats = {name: distribution([errors[case][i] for case in containing])
                     for i, name in enumerate(BUILDS)}
            control, candidate = (stats[name] for name in BUILDS)
            no_worse = {k: not control["n"] or bool(candidate["n"] and candidate[k] <= control[k])
                        for k in ("p50", "p90")}
            summary["arms"][arm] = dict(
                matched_fixes=sorted(retained), lost_fixes=sorted(lost), added_fixes=sorted(added),
                both_withheld=sorted(errors.keys() - (fixes["baseline"] | fixes["candidate"])),
                lost_containing_fixes=lost_containing, additional_false_fixes=added_false,
                false_fixes={name: sorted(fixed_cases - containing) for name, fixed_cases in fixes.items()},
                containing_error_km=stats, no_worse=no_worse,
                error_by_case_km={case: dict(zip(BUILDS, value, strict=True)) for case, value in errors.items()},
                preserved=not lost_containing and not added_false and all(no_worse.values()))
        summaries.append(summary)
    return dict(by_site=summaries,
                preserved=all(arm["preserved"] for site in summaries for arm in site["arms"].values()))


def observed_timing(cases):
    verified = [row for row in cases if row["state"] == "verified"]
    zero_reads = [row for row in verified if all(row.get("input_blocks", {}).get(k) == 0 for k in BUILDS)]
    reports = {}
    for label, rows in (("all_verified", verified), ("both_zero_input_blocks", zero_reads)):
        result = {"cases": [row["case"] for row in rows]}
        for metric in ("elapsed_s", "cpu_s"):
            times = [(r[metric]["baseline"], r[metric]["candidate"]) for r in rows]
            median_ratio, summed_ratio = elapsed_ratios(times)
            result[metric] = dict(median_candidate_over_baseline=median_ratio,
                                  summed_candidate_over_baseline=summed_ratio)
        reports[label] = result
    return reports


def score(stage):
    cases = stage["cases"]
    stage = dict(stage, observed_timing=observed_timing(cases))
    approximate = stage.get("comparison") in APPROXIMATE_MODES
    if len(stage["coverage"]["verified"]) != stage["assigned"]:
        result = dict(stage, elapsed_gates=None, position=None)
        if approximate:
            result["quality"] = None
        return result
    times = [(row["elapsed_s"]["baseline"], row["elapsed_s"]["candidate"]) for row in cases]
    paired, summed = elapsed_ratios(times)
    truth = pinned(OUT / "reference-audit.json", REFERENCE_SHA256)["cases"]
    refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
            for r in truth if r["authority_eligible"]}
    position = {}
    for label in BUILDS:
        position[label] = {}
        for arm in ARMS:
            errors = [distance_km(row["arms"][label][arm]["latlon"], refs[row["case"]]) for row in cases]
            position[label][arm] = dict(error_km=distribution(errors), within_km_count=thresholds(errors),
                                        assigned=len(cases))
    gates = dict(median_candidate_over_baseline=paired, summed_candidate_over_baseline=summed,
                 median_pass=paired <= .5, summed_pass=summed <= .5, passed=max(paired, summed) <= .5)
    result = dict(stage, elapsed_gates=gates, position=position)
    if approximate:
        result["quality"] = local_quality(cases, refs)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "inventory", "score"))
    for name in ("workspace", "candidate", "config"):
        parser.add_argument(name, type=Path)
    parser.add_argument("spec_digest")
    parser.add_argument("--size", type=int, choices=(4, 16), default=4)
    parser.add_argument("--case", help="Require the next assigned case to have this DS30 ID")
    parser.add_argument("--cache-library", type=Path,
                        help="Observe the assigned file cache before each timed arm")
    args = parser.parse_args()
    if args.case and args.action != "run":
        parser.error("--case applies to run")
    if args.cache_library is not None and args.action != "run":
        parser.error("--cache-library applies to run")
    spec = verify_build(args.candidate, args.config, args.spec_digest)
    region_file = pair.BASELINE.parent / "station/region.json"
    assignments = frozen_assignments(args.size, Algo08Region.parse(read(region_file)).document())
    stage = inventory(args.workspace, assignments, args.candidate, spec, cpu=2)
    if args.action == "run":
        run_next(args.workspace, assignments, stage, args.case, args.candidate, args.config,
                 region_file, cache_library=args.cache_library)
        stage = inventory(args.workspace, assignments, args.candidate, spec, cpu=2)
    print(json.dumps(score(stage) if args.action == "score" else stage, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
