"""Price the original 20 ms receiver against the measured charted saved solver."""

import argparse
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path


UNITS = ("elapsed_s", "cpu_s")
ARMS = {"c0", "fitted_c"}
SCOPE = "raw_launcher_through_exit_plus_common_publication_verification"
CLOCK_SLACK_S = 0.010
PLAN = "9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
REVISION = "a8f2ddd471923a8d367c89e980498c24fee1feef12df6eeb1786aa8848f7cb3c"
BUILD = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
DETECTOR = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
MIXED = "sha256:ce13caaadf150f474a024fda7da31a33f9e293e9bb9e4d91613c552c3cd7335a"
SOURCE = {
    "scanner": "573d6608597f1619785688769e7504a4ad8ac30dd71fecd37876c678ed4aca53",
    "immutable_writer": "db79b4e50c10a3b948c69c86a464fb57a226b0dbb2955cf90d8ae83db3f39527",
    "charted_publisher": "0495af4960cf0dc7df62034fa66fcdfa41798fc1dc2a7c035e2e6eeec5994186",
    "saved_adapter": "748efc75ca9381129580c106779caddfc3d97f694f0b6c73ed68ba22ccf60c69",
}
# Pair generation and digest, original mixed bootstrap and named witness, and
# the complete saved score, full-detector worker receipt, and named witness.
CASES = {
    "DS30-0049": (2, "7514497ea681194487e8d85aecf2d739e996abf2b90566d446f81fe38875c36b",
                  "01e2eb141201e8ec02a67d5ce2ce44d74e8c7262952c2e8cf61c8593ef0b845e",
                  "02d9a0273e0ed19bac1e531e09f8d4fca323f2c09db6e1aeb6c9798a161732ad",
                  "c1fd49b28d0a90370ecf056ac7c0bf90b01af094a9377bfff5c38db39da7b7f3",
                  "f1348b4da7838ab69f68cbaf2347a6fd45b70bb2bcc23956594ff816bedfc0f9",
                  "25b0ad93596e328e143602c18acf1996c0f474b49461fde007a3767155af2e42"),
    "DS30-0086": (1, "407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439",
                  "d21da2bd2e7b37428a696f24079a1753297228d1e3bba1fe8ad20c3df07c6c27",
                  "5d775bbb9ff01ca9943c8001ed316cd2d65925da8348368452ddd8c0855ae084",
                  "97540c32d9d1940457f28015e230f5bd0071d632a4968aa51e2b947807eefdb4",
                  "36c964fe7e2cf12ed2d322bf85dc52f82f3f67877fbeb929ce35873f63b2bcf5",
                  "915ddc6e1c49e4725bef885ca418e7aff3e4a938464a4c2a9a1e58e14e3d06a9"),
    "DS30-0220": (1, "d307ff5f4a02fe144eb1547574728a46bf19b4365d971687c471adea65aa4755",
                  "c9dacc53e748d67d9e923bf86240a74eb9e144210bce554882ef3acccd7ffcaa",
                  "b8be7fef63a425d3fd15de1ca206f6ec40be65b96afa8d114fb0e8808c8a36eb",
                  "329693cc9562cf7dc9e4828199003d4c332994ff9ee5a1f47b7d1e332c3e3eb3",
                  "4d73fca4e001f27faf92106bb0180f7f7bfc31d093f6a11e734061de4b8bee2a",
                  "982156b3591877e1f875d11dd7fc9e13618cb6fc5db013d37051a955ec83ff4b"),
}
ADMISSIONS = {
    "DS30-0086": "e107c4c60c2db6fdeea0f75419835cef2605b16f90456ef14b27d5e9b9d90fde",
    "DS30-0220": "41f1d38215156a95deebf06bfe10237f477daa9c5b07d4eca8b09b3fdc4e137a",
}


def sealed(path, expected):
    body = path.read_bytes()
    if sha256(body).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"Input seal changed at {path}")
    return json.loads(body)


def clocks(row):
    values = {key: row[key] for key in UNITS}
    if any(not isfinite(value) or value < 0 for value in values.values()):
        raise ValueError("Expected nonnegative finite elapsed and CPU clocks")
    return values


def native_boundary(process, native_write_ns, terminal_write_ns, *, one_cpu=False):
    start, finish = (process[key] for key in ("started_unix_ns", "finished_unix_ns"))
    if not start < native_write_ns < terminal_write_ns <= finish:
        raise ValueError("Native data write must precede the terminal in the original worker")
    prefix = (native_write_ns - start) / 1e9
    suffix = (finish - native_write_ns) / 1e9
    capacity = None
    if one_cpu and abs(prefix + suffix - process["elapsed_s"]) <= CLOCK_SLACK_S:
        used = process["cpu_s"]
        capacity = (max(0., used - suffix - CLOCK_SLACK_S), min(used, prefix + CLOCK_SLACK_S))
        if capacity[0] > capacity[1]:
            raise ValueError("Child CPU exceeds its assumed one-processor capacity")
    return dict(write_elapsed_s=prefix, measured_cpu_s=None, conditional_cpu_capacity_s=capacity,
                started_unix_ns=start, native_write_unix_ns=native_write_ns,
                terminal_write_unix_ns=terminal_write_ns, finished_unix_ns=finish)


def necessary_budget(baseline, solve, render, analyze, full_publication, stock_prefix):
    target = {key: value / 2 for key, value in clocks(baseline).items()}
    useful = {key: solve[key] + render[key] for key in UNITS}
    if any(not 0 < useful[key] <= analyze[key] <= full_publication[key] for key in UNITS):
        raise ValueError("Expected disjoint solve and render inside analyze and saved publication")
    outer = {key: target[key] - useful[key] for key in UNITS}
    whole_block = {key: target[key] - full_publication[key] for key in UNITS}
    result = dict(half_baseline=target, solver_plus_render=useful, all_other_at_most=outer,
                  receiver_allowance_if_whole_saved_block_charged=whole_block)
    if stock_prefix is not None:
        prefix = stock_prefix["write_elapsed_s"]
        capacity = stock_prefix["conditional_cpu_capacity_s"]
        result.update(remaining_wall_after_observed_prefix_s=outer["elapsed_s"] - prefix,
                      required_prefix_wall_saving_s=max(0., prefix - outer["elapsed_s"]),
                      excess_if_entire_charted_solver_and_render_free_s=prefix - target["elapsed_s"],
                      conditional_prefix_cpu_excess_s=(None if capacity is None else
                                                      max(0., capacity[0] - outer["cpu_s"])))
    return result


def individual_saved_cell(root, case, stock, pair, score_pin):
    if case == "DS30-0049":
        result = sealed(root / "final-evidence.json", score_pin)
        cell = result["cells"]["successor-installed"]
        comparison = result["cells"]["installed-installed"]
        delta = {arm: cell["arms"][arm]["error_m"] - comparison["arms"][arm]["error_m"] for arm in ARMS}
        child = dict(elapsed_s=cell["clocks"]["wall_s"], cpu_s=cell["clocks"]["cpu_s"])
        if (result["authority_sha256"] != pair["authority_sha256"] or result["raw_metadata"] != stock["raw_identity"]
                or any(not all(checks.values()) for checks in result["raw_diagonal_equivalence"].values())
                or cell["decision"] != "complete" or len(cell["figures"]) != 8):
            raise ValueError("0049 crossover lost its raw diagonal or qualification evidence")
        return root / "successor-installed", result, cell["native_sha256"], delta, child
    result = sealed(root / "score.json", score_pin)
    admission = sealed(root / "admission.json", ADMISSIONS[case])
    if (admission["authority_sha256"] != pair["authority_sha256"] or admission["raw_authority"] != stock["raw_identity"]
            or admission["build_sha256"] != BUILD or admission["native_sha256"] != result["native_sha256"]
            or admission["installed_result_sha256"] != result["installed_result_sha256"]
            or admission["installed_result_sha256"] != pair["attempt_result_sha256"]["installed"]
            or not result["qualification"]["qualified"] or not result["qualification"]["same_decision"]
            or result["process"]["exit_code"] or len(result["candidate_pngs"]) != 8
            or result["candidate_grid_points"] != 179):
        raise ValueError("Saved crossover lost its original admission or qualification")
    return (root / "candidate", result, result["native_sha256"], result["qualification"]["error_delta_m"],
            clocks(result["process"]))


def stage_witness(witness):
    (solve,), (render,), (analyze,) = (witness["timing"][key] for key in ("solve", "render", "analyze"))
    lean, = witness["ports"]["history_risk"]["lean_attempts"]
    return dict(solve=clocks(solve), render=clocks(render), analyze=clocks(analyze),
                lean_decision=lean["decision"], lean_reason=lean.get("reason"), fallback=lean.get("fallback_clocks"))


def study_case(campaign, root, case, pins, *, one_cpu):
    generation, pair_pin, bootstrap_pin, mixed_pin, saved_pin, worker_pin, full_pin = pins
    base = campaign / "cases" / case
    pair = sealed(base / "pair.json", pair_pin)
    paths = {arm: base / arm / f"attempt-{generation:06d}" for arm in ("installed", "successor")}
    results = {arm: sealed(path / "result.json", pair["attempt_result_sha256"][arm]) for arm, path in paths.items()}
    stock, mixed = results.values()
    if (not pair["verified_pair"] or not pair["chronological"] or pair["generation"] != generation
            or stock["raw_identity"] != mixed["raw_identity"] or stock["native_sha256"] == mixed["native_sha256"]):
        raise ValueError("Expected the verified original-file pair and two distinct detector packets")
    for result in results.values():
        if (result["timing_scope"] != SCOPE or result["generation"] != generation or result["outcome"] != "complete"
                or result["authority_sha256"] != pair["authority_sha256"] or result["process"]["exit_code"]
                or len(result["figures"]) != 8 or result["grid_points"] != 179 or set(result["evidence"]["arms"]) != ARMS
                or any(not isclose(result[key], result["process"][key] + result["validation"][key]) for key in UNITS)):
            raise ValueError("Original-file result lacks the complete verified boundary")
    stock_output = paths["installed"] / "publication/fast-scan-automatic-work"
    native_file, = stock_output.glob("*/detections.json")
    terminal_file = stock_output / stock["evidence"]["receipt"]["run_id"] / "terminal.json"
    prefix = native_boundary(stock["process"], native_file.stat().st_mtime_ns, terminal_file.stat().st_mtime_ns,
                             one_cpu=one_cpu)
    folder = paths["successor"] / "publication"
    raw_recipe = sealed(folder / "unified-short-bootstrap.json", bootstrap_pin)
    mixed_witness = sealed(folder / "exact-named-raw-witness.json", mixed_pin)
    raw_phases = raw_recipe["phases"]
    if (raw_recipe["native_sha256"] != mixed["native_sha256"] or raw_recipe["detector_recipe_sha256"] != MIXED
            or raw_recipe["receiver_recipe"]["installed_sha256"] != DETECTOR
            or raw_recipe["receiver_recipe"]["aperture_samples"] != [200000, 80000]
            or raw_recipe["raw_acquisitions"] != 1 or raw_recipe["verified_handoffs"] != 1
            or mixed_witness["evidence"]["detail"]["input_sha256"] != mixed["native_sha256"]):
        raise ValueError("Expected the genuine charted mixed-aperture raw timing source")

    leaf, saved, native, delta, child = individual_saved_cell(root, case, stock, pair, saved_pin)
    worker = sealed(leaf / "crossover-worker.json", worker_pin)
    witness = sealed(leaf / "exact-named-raw-witness.json", full_pin)
    detail = witness["evidence"]["detail"]
    if (len({detail["input_sha256"], native, stock["native_sha256"]}) != 1 or saved["waveform_reads"] != 0
            or detail["raw_authority"] != stock["raw_identity"]["raw_authority_sha256"]
            or detail["region"] != stock["evidence"]["receipt"]["region"]
            or worker["waveform_reads"] != 0 or worker["verified_handoffs"] != 1
            or detail["terminal_sha256"] != worker["receipt"]["terminal_sha256"]
            or len(witness["evidence"]["images"]) != 8 or witness["evidence"]["grid"] != 179
            or set(delta) != ARMS or max(delta.values()) > 250.0
            or witness["source_sha256"] != mixed_witness["source_sha256"]
            or witness["source_sha256"]["reports/ALGO08/v3/exact_named_raw.py"] != SOURCE["charted_publisher"]):
        raise ValueError("Full-detector saved timing or qualification does not match the original source and offer")
    observed = stage_witness(witness)
    audit = worker["audit"]
    publication = dict(elapsed_s=audit["saved_scientific_elapsed_s"], cpu_s=audit["saved_scientific_cpu_s"])
    budget = necessary_budget(stock, observed["solve"], observed["render"], observed["analyze"], publication, prefix)
    return dict(case=case, generation=generation, pair_same_lease=pair["same_lease"], original_order=pair["actual_order"],
                installed_native_sha256=native, mixed_native_sha256=mixed["native_sha256"],
                raw={arm: dict(verified=clocks(result), child=clocks(result["process"]),
                               verifier=clocks(result["validation"])) for arm, result in results.items()},
                original_full_prefix=prefix, mixed_acquisition=clocks(raw_phases["authenticated_raw_acquisition"]),
                mixed_decision_publication=clocks(raw_phases["decision_and_publication"]),
                mixed_solver=stage_witness(mixed_witness), charted_on_full_saved={
                    **observed, "child": child, "scientific_publication": publication, "position_error_delta_m": delta},
                hybrid_unmeasured=True, budget=budget,
                pins=dict(pair=pair_pin, original_results=pair["attempt_result_sha256"], mixed_bootstrap=bootstrap_pin,
                          mixed_publisher=mixed_pin, saved_score=saved_pin, saved_worker=worker_pin, saved_publisher=full_pin,
                          saved_admission=ADMISSIONS.get(case)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("saved_0049", type=Path)
    parser.add_argument("saved_0086", type=Path)
    parser.add_argument("saved_0220", type=Path)
    args = parser.parse_args()
    plan = sealed(args.campaign / "plan.json", PLAN)
    revision = sealed(args.campaign / "validation-revision.json", REVISION)
    if (plan["stock"]["detector_sha256"] != DETECTOR or plan["candidate"]["sha256"] != "sha256:" + BUILD
            or plan["cpu"] != 2 or revision["plan_sha256"] != "sha256:" + PLAN
            or revision["original_driver_sources"] != plan["driver_sources"]):
        raise ValueError("Original campaign and validation revision changed")
    for name in ("ds30_paired_evaluation.py", "ds30_paired_worker.py"):
        if "sha256:" + sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != revision["current_driver_sources"][name]:
            raise ValueError("Reviewed one-CPU driver source changed")
    paths = (args.saved_0049, args.saved_0086, args.saved_0220)
    result = dict(plan_sha256=PLAN, validation_revision_sha256=REVISION, timing_scope=SCOPE,
                  charted_build_sha256=BUILD, installed_detector_sha256=DETECTOR, sources=SOURCE,
                  cases=[study_case(args.campaign, root, case, pins, one_cpu=True)
                         for (case, pins), root in zip(CASES.items(), paths, strict=True)])
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
