"""Plan or explicitly run supplemental cold-process and persistent stress evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shlex
from pathlib import Path

from execute import HERE, connection, digest, save


def calls_by_context(folder: Path) -> tuple[dict, dict]:
    execution = json.loads((HERE / "execution-panel.json").read_text())
    results, cases = {}, {}
    for group in execution["groups"]:
        path = folder / (group["id"] + ".jsonl")
        documents = [json.loads(line) for line in path.read_text().splitlines()]
        rows = {d["result"]["sequence"]: d["result"] for d in documents[1:-1]}
        for call in group["calls"]:
            context = call["case"]["context"]
            key = (context["session_id"], context["visit_index"])
            cases[key] = call["case"]
            results.setdefault(key, []).append(rows[call["sequence"]])
    return cases, results


def identity(call: dict) -> str:
    # The published CLI serializes glrt_complete as 0/1; the diagnostic
    # client uses false/true. Normalize only that established representation.
    rows = []
    for row in call["rows"]:
        candidates = []
        for candidate in row["candidates"]:
            assert candidate["glrt_complete"] in (0, 1)
            candidates.append({**candidate, "glrt_complete": bool(candidate["glrt_complete"])})
        rows.append(candidates)
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def plan(args) -> None:
    cases, results = calls_by_context(args.control)
    primary = [key for key, case in cases.items() if case["context"]["rate_hz"] == 2_500_000]
    ranked = sorted(primary, key=lambda key: sum(c["call_cpu_ms"] for c in results[key]) /
                    len(results[key]), reverse=True)
    worst_edge = cases[ranked[0]]["context"]["target"]["edge"]
    edge = [key for key in ranked if cases[key]["context"]["target"]["edge"] == worst_edge][:16]
    assert len(edge) == 16
    template_pairs = {tuple(sorted(cases[key]["template_files"].items())) for key in edge}
    assert len(template_pairs) == 1
    assert all(len({identity(call) for call in results[key]}) == 1 for key in edge)
    no_hits = [key for key in ranked if not any(
        candidate for call in results[key] for row in call["rows"]
        for candidate in row["candidates"]
    )]
    cold = list(dict.fromkeys(ranked[:3] + no_hits[:2]))
    rng = random.Random(args.seed)
    order = []
    for repeat in range(100):
        shuffled = edge.copy()
        rng.shuffle(shuffled)
        order.extend({"repeat": repeat, "key": list(key)} for key in shuffled)
    document = {
        "schema": "org.leo.native-glrt-stress-plan/v1",
        "seed": args.seed,
        "execution_panel_sha256": digest(HERE / "execution-panel.json"),
        "control_manifest_sha256": digest(args.control / "manifest.json"),
        "qualification_limits": {"unique_inputs": 16, "preloaded_bytes": 38_400_000,
                                 "client_caps": {"unique_inputs": 32,
                                                 "preload_bytes": 134_217_728}},
        "stress": {
            "selection": (
                "16 slowest control contexts sharing the worst context's edge and template pair"
            ),
            "edge": worst_edge,
            "template_files": dict(next(iter(template_pairs))),
            "unique_contexts": [list(key) for key in edge],
            "calls": order,
        },
        "cold": {"contexts": [list(key) for key in cold], "runs_each": 1,
                 "timing": (
                     "BusyBox time -p: device process real/user/sys; excludes SSH and transfers"
                 )},
        "expected_candidate_hashes": {"|".join(map(str, key)): identity(results[key][0])
                                      for key in set(edge + cold)},
    }
    save(args.output, document)


def run(args) -> None:
    plan_doc = json.loads(args.plan.read_text())
    assert plan_doc["execution_panel_sha256"] == digest(HERE / "execution-panel.json")
    assert plan_doc["control_manifest_sha256"] == digest(args.control / "manifest.json")
    cases, _ = calls_by_context(args.control)
    remote, upload = connection(args)
    execution = json.loads((HERE / "execution-panel.json").read_text())
    root = execution["remote_root"]
    binary_hash = digest(args.binary)
    executable = root + "/stress-" + binary_hash[:16]
    upload(args.binary, executable)
    remote("chmod +x " + shlex.quote(executable))
    output = HERE / "local" / args.label
    output.mkdir(parents=True, exist_ok=args.cold_only)
    rows = []
    for sequence, item in enumerate(plan_doc["stress"]["calls"]):
        case = cases[tuple(item["key"])]
        rows.append("\t".join(map(str, (sequence, 2_500_000, 120, 120,
            root + "/" + case["template_files"]["exact"],
            root + "/" + case["template_files"]["control"], root + "/" + case["raw_file"]))))
    manifest = output / "stress.tsv"
    manifest.write_text("\n".join(rows) + "\n")
    upload(manifest, root + "/stress.tsv")
    command = [executable, "--manifest", root + "/stress.tsv", "--thermal-path",
               "/sys/bus/iio/devices/iio:device1/in_temp0_raw", "--thermal-offset", "-2219",
               "--thermal-scale", "123.040771484"]
    if args.cold_only:
        text = (output / "stress.jsonl").read_text()
    else:
        text = remote(shlex.join(command), timeout=3600)
        (output / "stress.jsonl").write_text(text)
    documents = [json.loads(line) for line in text.splitlines()][1:-1]
    for item, document in zip(plan_doc["stress"]["calls"], documents, strict=True):
        expected = plan_doc["expected_candidate_hashes"]["|".join(map(str, item["key"]))]
        assert identity(document["result"]) == expected
    cold_results = []
    for index, key_list in enumerate(plan_doc["cold"]["contexts"]):
        case = cases[tuple(key_list)]
        time_path = root + f"/cold-{index}.time"
        # Cold evidence uses the separately uploaded public CLI supplied by --cli.
        cli_remote = root + "/cold-cli-" + digest(args.cli)[:16]
        if index == 0:
            upload(args.cli, cli_remote)
            remote("chmod +x " + shlex.quote(cli_remote))
        command = [cli_remote, "--rate-hz", "2500000", "--dwell-ms", "120",
            "--probe-stride-ms", "120", "--exact-template", root + "/" +
            case["template_files"]["exact"], "--control-template", root + "/" +
            case["template_files"]["control"], "--input-ci16", root + "/" + case["raw_file"]]
        result = remote("{ time -p " + shlex.join(command) + "; } 2>" + shlex.quote(time_path))
        timing = remote("cat " + shlex.quote(time_path))
        parsed = json.loads(result)
        expected = plan_doc["expected_candidate_hashes"]["|".join(map(str, key_list))]
        assert identity(parsed) == expected
        cold_results.append({"context": key_list, "time_p": timing, "result": parsed})
    save(output / "cold.json", cold_results)
    save(output / "manifest.json", {"plan_sha256": digest(args.plan),
        "binary_sha256": binary_hash, "cli_sha256": digest(args.cli),
        "receipt_sha256": digest(args.receipt), "stress_sha256": digest(output / "stress.jsonl"),
        "cold_sha256": digest(output / "cold.json")})


def summarize_stress(args) -> None:
    from summarize import distribution

    folder = HERE / "local" / args.label
    binding = json.loads((folder / "manifest.json").read_text())
    assert binding["stress_sha256"] == digest(folder / "stress.jsonl")
    assert binding["cold_sha256"] == digest(folder / "cold.json")
    rows = [json.loads(line) for line in (folder / "stress.jsonl").read_text().splitlines()]
    calls = [row["result"] for row in rows[1:-1]]
    assert len(calls) == 1600 and rows[0]["entries"] == 1600
    result = {key: distribution([c[key] for c in calls])
              for key in ("call_cpu_ms", "call_wall_ms")}
    result.update({
        "binding": binding,
        "e2e_wall_ms": distribution(rows[-1]["e2e_wall_ms"]),
        "temperature_after_mdeg": distribution(
            [c["thermal_millidegrees_after"] for c in calls], deadlines=False),
        "max_peak_rss_kib": max(c["peak_rss_kib_after"] for c in calls),
        "rss_after_first_round_kib": calls[15]["peak_rss_kib_after"],
        "setup": rows[0], "summary": rows[-1],
        "cold": json.loads((folder / "cold.json").read_text()),
    })
    save(args.summary_output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "run", "summarize"))
    parser.add_argument("--control", type=Path, default=HERE / "local/sparse-cached")
    parser.add_argument("--output", type=Path, default=HERE / "stress-plan.json")
    parser.add_argument("--summary-output", type=Path, default=HERE / "stress-summary.json")
    parser.add_argument("--seed", type=int, default=2026092902)
    parser.add_argument("--plan", type=Path, default=HERE / "stress-plan.json")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--cli", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--label")
    parser.add_argument("--cold-only", action="store_true")
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--target", default="root@192.168.1.15")
    arguments = parser.parse_args()
    {"plan": plan, "run": run, "summarize": summarize_stress}[arguments.action](arguments)
