"""Compare one physical ARM dwell using the reviewed DS9 science comparator."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[3]
base = root / "reports/2026_09_30_native_adaptive_deployment"
harness = base / "ds9/corrected-full-replay-v1/run_slice.py"
spec = importlib.util.spec_from_file_location("reviewed_ds9_comparator", harness)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
host_path = base / "ds9/receiver-authority-ablation-v1/wideband-research/retention-audit-v1/visit-0301.jsonl"
arm_path = here / "visit-0301.arm.jsonl"
host = module.load_result(host_path.read_text())
arm = module.load_result(arm_path.read_text())
comparison = module.compare_native_server(
    module.native_candidates(arm), module.native_candidates(host)
)
passed = all(comparison[key] for key in (
    "structure_equal", "numeric_values_finite", "within_frozen_tolerance",
    "all_gate_decisions_equal",
))
result = {
    "schema": "leo-corrected-wideband-arm-comparison/v1",
    "status": "pass" if passed else "fail",
    "scope": "DS9 visit 301, both receivers; physical ARM versus corrected host wrapper",
    "compared_inputs": {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (host_path, arm_path, harness)
    },
    "comparison": comparison,
    "arm_call_wall_ms": arm["call_wall_ms"],
    "arm_detector_cpu_ms": arm["detector_cpu_ms"],
    "dwell_ms": arm["dwell_ms"],
    "call_wall_to_dwell_ratio": arm["call_wall_ms"] / arm["dwell_ms"],
    "not_qualified": ["full-corpus ARM parity", "real-time detector", "capture concurrency"],
}
(here / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({k: v for k, v in result.items() if k != "comparison"}, indent=2))
raise SystemExit(0 if passed else 1)
