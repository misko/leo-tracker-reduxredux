"""Small alternating exactness/timing comparison; synthetic evidence only."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from algo07v3_prevariance_hierarchical_oracle import hierarchical_bound
from probe_algo07v3_assembly import exact_result
from probe_algo07v3_variance_groups import candidate_function


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Fresh output required")
    candidate, source, code = candidate_function()
    rng, records = np.random.default_rng(786), []
    for pattern in ("local", "dense"):
        for n, width, ng in ((301, 32, 17), (2783, 190, 70)):
            u, g = rng.normal(size=(n, width)), np.arange(n) % ng
            if pattern == "local":
                for k in range(ng):
                    cols = np.arange(width)
                    keep = ((cols < min(8, width))
                            | ((cols // 4) % max(1, ng // 2) == k % max(1, ng // 2))
                            | (cols == width - 1 - k % max(1, width - 8)))
                    u[np.ix_(g == k, ~keep)] = 0
            y, sigma = rng.normal(size=n) * 150, rng.uniform(40, 120, n)
            arguments = (y, u, sigma, g)
            kwargs = dict(prior_groups=np.arange(width) // 5 - 1,
                          powers=np.linspace(.1, 1, ng), iterations=64)
            functions = dict(reference=hierarchical_bound, candidate=candidate)
            timings = {name: [] for name in functions}
            for pair in range(4):
                outputs = {}
                order = ("reference", "candidate") if pair % 2 == 0 else ("candidate", "reference")
                for side in order:
                    began = time.perf_counter()
                    outputs[side] = functions[side](*arguments, **kwargs)
                    timings[side].append(time.perf_counter() - began)
                exact_result(outputs["reference"], outputs["candidate"])
            records.append(dict(
                pattern=pattern, n=n, width=width, groups=ng, seconds=timings,
                exact=True, iterations=outputs["reference"]["precision_iterations"],
                input_sha256={str(i): hashlib.sha256(a.tobytes()).hexdigest()
                              for i, a in enumerate(arguments)},
            ))
    result = dict(
        seed=786, records=records,
        reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
        candidate_sha256=hashlib.sha256(code.encode()).hexdigest(),
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        candidate_tool_sha256=hashlib.sha256(
            Path(__file__).with_name("probe_algo07v3_variance_groups.py").read_bytes()
        ).hexdigest(), enabled_in_runtime=False, qualified_speedup=None,
    )
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for row in records:
        old, new = (sum(row["seconds"][side]) for side in ("reference", "candidate"))
        print(json.dumps(dict(pattern=row["pattern"], width=row["width"],
                              reference_seconds=old, candidate_seconds=new,
                              reduction_percent=100 * (1 - new / old))))


if __name__ == "__main__":
    main()
