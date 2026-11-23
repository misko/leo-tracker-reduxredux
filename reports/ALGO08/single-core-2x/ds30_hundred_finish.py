"""Independently reopen the 100 archived pairs and publish a final, atomic report."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from . import ds30_hundred as study
from . import ds30_hundred_review as reviewer
from . import ds30_stage as stage


def decision(result):
    if result["verified"] != study.COUNT:
        raise ValueError("A version decision requires all 100 verified recording pairs")
    elapsed = result["timing"]["all_verified"]["elapsed_s"]
    total = result["builds"]
    failures = result["solver_failures"]
    prior = result.get("prior_candidate_failures", {})
    gates = dict(median_time=elapsed["median_candidate_over_baseline"] <= .5,
                 summed_time=elapsed["summed_candidate_over_baseline"] <= .5,
                 fix_rate=total["candidate"]["fixes"] >= total["baseline"]["fixes"],
                 accuracy_and_decisions=result["quality"]["preserved"],
                 no_new_solver_failures=not ((set(failures["candidate"]) | set(prior)) - set(failures["baseline"])))
    return dict(gates=gates, qualifies=all(gates.values()))


def verify_preflight(receipt):
    if (receipt["runs"] or receipt["cache_observation"]["arms"] or
            receipt.get("failure") != "ValueError: Cache observation recording differs from its assigned sealed manifests"):
        raise ValueError("Expected a path preflight stop before either timed launch")


def shared_error(quality, arm):
    pairs = [pair for site in quality["by_site"]
             for pair in site["arms"][arm]["error_by_case_km"].values()
             if pair["baseline"] is not None and pair["candidate"] is not None]
    differences = [abs(pair["candidate"] - pair["baseline"]) for pair in pairs]
    return len(pairs), max(differences, default=None)


def report(result, verdict):
    counts = result["builds"]
    ratios = result["timing"]["all_verified"]["elapsed_s"]
    def metric(label, field):
        value = counts[label][field]
        return "—" if value["p50"] is None else f'{value["p50"]:.3f} / {value["p90"]:.3f}'
    rows = [
        f'| {name} | {counts[method]["fixes"]}/100 | {metric(method, "elapsed_s")} | '
        f'{metric(method, "c0_error_km")} | {metric(method, "fitted_c_error_km")} |'
        for method, name in (("baseline", "Deployed ALGO08v2"), ("candidate", "ALGO08v3"))
    ]
    verdict_text = ("ALGO08v3 met the original 2× qualification criteria on DS30." if
                    verdict["qualifies"] else "ALGO08v3 missed the following original DS30 qualification criteria: " +
                    ", ".join(key for key, ok in verdict["gates"].items() if not ok) + ".")
    shared = []
    for field, name in (("c0", "Fixed-zero"), ("fitted_c", "Fitted")):
        count, largest = shared_error(result["quality"], field)
        if count:
            shared.append(f"{name} calibration had {count} shared fixes. The largest absolute difference "
                          f"in their horizontal errors was {largest * 1000:.3f} m.")
    speed_rows = []
    for name, timing in (("All assigned recordings", result["timing"]),
                         ("Both returned a fix", result["shared_fix_timing"]),
                         ("ALGO08v2 ran first", result["by_first_build"]["baseline"]),
                         ("ALGO08v3 ran first", result["by_first_build"]["candidate"])):
        group = timing["all_verified"]
        if group["cases"]:
            elapsed = group["elapsed_s"]
            speed_rows.append(f'| {name} | {len(group["cases"])} | '
                              f'{1 / elapsed["median_candidate_over_baseline"]:.2f}× | '
                              f'{1 / elapsed["summed_candidate_over_baseline"]:.2f}× | '
                              f'{1 / group["cpu_s"]["summed_candidate_over_baseline"]:.2f}× |')
    return "\n".join([
        "# ALGO08v3 and deployed ALGO08v2 on 100 DS30 recordings", "", verdict_text, "",
        "The frozen candidate was named ALGO08v3 at the user's request during the panel. "
        "The benchmark uses the original build, criteria and recordings throughout.", "",
        f'The median paired elapsed ratio was **{ratios["median_candidate_over_baseline"]:.5f}** and '
        f'the summed elapsed ratio was **{ratios["summed_candidate_over_baseline"]:.5f}**. '
        'Each compares candidate seconds with deployed seconds, with a 0.50 threshold.', "",
        f'These ratios correspond to **{1 / ratios["median_candidate_over_baseline"]:.2f}×** and '
        f'**{1 / ratios["summed_candidate_over_baseline"]:.2f}×** speedups respectively.', "",
        "| Build | Fixes | Elapsed median / P90 (s) | Fixed-zero error median / P90 (km) | Fitted error median / P90 (km) |",
        "|---|---:|---:|---:|---:|", *rows, "",
        *shared, "",
        "| Recordings | Pairs | Median paired elapsed speedup | Summed elapsed speedup | Summed CPU speedup |",
        "|---|---:|---:|---:|---:|", *speed_rows, "",
        "The second arm can read input pages cached by the first. The run-order rows contain different "
        "recordings, so their difference cannot isolate the effect of caching.", "",
        "Both runs started from the same sealed I/Q on one low-priority Gauss core and ended after "
        "publication or an observed solver exit. Run order alternated. Error histograms count returned fixes.",
        "", "Solver failures retained in the 100 assigned pairs: " +
        ", ".join(f"{label} {len(names)} ({', '.join(names) or 'none'})"
                  for label, names in result["solver_failures"].items()) + ".",
        "DS30-0022 first stopped before the original timing harness recorded elapsed time. "
        "The archived first attempt remains in the decision audit. The timed recovery pair counts once.",
        "For DS30-0447, a private read-only mount gave the archived recording its original path. "
        "The session identity and all 14 ordered segment manifest digests matched. "
        "The first path check stopped before either timer started.",
        "", "![Runtime distributions](runtime.png)", "",
        "![Horizontal position-error distributions](position-error.png)", "",
        "All 100 recordings came from one roof. Both algorithms previously returned false fixes when the "
        "receiver lay 100 m outside the offered region at two simulated sites. Geographic qualification "
        "and deployment are separate from naming a version on this DS30 comparison.", "",
        "[Recording-level CSV](recordings.csv) · [Gate and receipt audit](decision.json)", "",
    ])


def finish(archive, destination):
    progress = stage.read(archive / "progress.json")
    if progress["verified"] != study.COUNT or progress["assigned"] != study.COUNT:
        raise ValueError("The published progress marker is incomplete")
    region = study.Algo08Region.parse(stage.read(study.OFFER)).document()
    rows = []
    with stage.pair.single_core_slot(2):
        assignments = stage.frozen_assignments(study.COUNT, region)
        if study.panel_manifest(assignments) != stage.read(archive / "panel.json"):
            raise ValueError("Archive panel does not match the 100 original input assignments")
        spec = stage.verify_build(study.LAUNCHER, study.CONFIG, stage.EXACT_CURVED_LOOKAHEAD)
        for a in assignments:
            original = archive / "publications" / a.name / "pair.json"
            checked = stage.verify_pair(original, a, study.LAUNCHER, spec, 2)
            row = dict(checked, case=a.name, rank=a.rank, expected_order=a.order)
            if row["state"] != "verified" or row != stage.read(archive / "audits" / (a.name + ".json")):
                raise ValueError(f"Reopened publication differs from the recorded audit for {a.name}")
            rows.append(row)
        reference = stage.pinned(stage.OUT / "reference-audit.json", stage.REFERENCE_SHA256)
        refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
                for r in reference["cases"] if r["authority_eligible"]}
        _, rebuilt = study.summarize(rows, refs)
        if rebuilt != progress:
            raise ValueError("The final aggregate changed when recalculated from the archived publications")
        result = reviewer.describe(rows, refs)
        first = archive / "attempts/DS30-0022-01/pair.json"
        original_attempt = stage.pinned(first, "5618c40b162600443fb523a5967b2ded1c8b7a512af8e71712525c5780516684")
        if (original_attempt["order"][0] != "candidate" or original_attempt["runs"] or
                not stage.pair.orbit_solver_failure(original_attempt["failure"])):
            raise ValueError("Unexpected first DS30-0022 failure receipt")
        result["prior_candidate_failures"] = {"DS30-0022": stage.file_sha(first)}
        preflight = archive / "attempts/DS30-0447-path-preflight/pair.json"
        verify_preflight(stage.pinned(preflight, "5cf956997b108f180545988d0b191232f3490aa4ea8768e3bb729a5e3af617b4"))
        result["untimed_path_preflight"] = {"DS30-0447": stage.file_sha(preflight)}
        verdict = decision(result)
        receipt = dict(candidate=stage.EXACT_CURVED_LOOKAHEAD, candidate_name="ALGO08v3", baseline=str(stage.pair.BASELINE),
                       order_sha256=study.ORDER_SHA256, result=result, **verdict,
                       pair_sha256={r["case"]: r["pair_sha256"] for r in rows})
        if destination.exists():
            if stage.read(destination / "decision.json") != receipt:
                raise ValueError("A different report already exists at the final destination")
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=destination.parent) as work:
            folder = Path(work) / "report"
            folder.mkdir()
            study.write_report(rows, refs, folder, candidate_label="ALGO08v3")
            (folder / "decision.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
            (folder / "README.md").write_text(report(result, verdict))
            folder.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    finish(args.archive, args.destination)
