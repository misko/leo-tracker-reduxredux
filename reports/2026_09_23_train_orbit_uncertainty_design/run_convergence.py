"""Repeat the unchanged pilot with a 300-evaluation convergence budget."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def main():
    source = Path(__file__).with_name("run_pilot.py")
    spec = importlib.util.spec_from_file_location("pilot_convergence", source)
    pilot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pilot)
    original = pilot.least_squares
    diagnostics = []

    def solve(*args, **kwargs):
        kwargs["max_nfev"] = 300
        result = original(*args, **kwargs)
        diagnostics.append({"status": int(result.status), "message": str(result.message),
                            "nfev": int(result.nfev), "optimality": float(result.optimality),
                            "cost": float(result.cost)})
        return result

    pilot.least_squares = solve
    pilot.main()
    output = Path(sys.argv[sys.argv.index("--output") + 1])
    result = json.loads(output.read_text())
    result["solver_amendment"] = {
        "max_nfev": 300,
        "reason": "Both first-group 60-evaluation fits exhausted their solver budget.",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model_and_input_selection_unchanged": True,
        "solver_calls_in_execution_order": diagnostics,
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
