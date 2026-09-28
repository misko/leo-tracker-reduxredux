"""Run all controls under ASan/UBSan before physical target execution."""
import argparse
import json
from pathlib import Path
import subprocess
from evaluate import compare_case, summarize

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
args = parser.parse_args()
bundle = args.bundle.resolve()
manifest = json.loads((bundle / "manifest.json").read_text())
out = bundle / "host-check"
out.mkdir(exist_ok=False)
assessments = []
for case in [c for c in manifest["cases"] if c["split"] == "control"]:
    t = manifest["templates"][case["template_key"]]
    results = {}
    for method in "ABCD":
        run = subprocess.run([str(bundle / "host-asan" / method),
            str(bundle / "data" / case["raw_file"]), str(bundle / "data" / t["exact"]),
            str(bundle / "data" / t["control"]), str(case["rate_hz"]), case["edge"], case["case_id"]],
            capture_output=True, timeout=20)
        name = f"{case['case_id']}-{method}"
        (out / (name+".stderr")).write_bytes(run.stderr)
        (out / (name+".json")).write_bytes(run.stdout)
        if run.returncode:
            raise RuntimeError(f"{name}: return code {run.returncode}; see stderr")
        results[method] = json.loads(run.stdout)
    assessment = compare_case(case, results)
    assessments.append(assessment)
    (out / "assessments.json").write_text(json.dumps(assessments, indent=2))
    print(case["case_id"], assessment["passed"], flush=True)
    if not assessment["passed"]:
        raise RuntimeError("control scientific gate failed; retained receipt")
(out / "summary.json").write_text(json.dumps(summarize(assessments), indent=2))
