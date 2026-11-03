import concurrent.futures
import subprocess
import sys
import time

import numpy as np
from study import HERE, SOURCE, digest, read, save, source

baseline, timing, model_class = source.numerical_imports()
from model import decompose, track_scores  # noqa: E402


def run(unit):
    started = time.monotonic()
    original = read(HERE / f"{unit}.json")
    assert not original["qualified"]
    manifest = read(SOURCE / "manifest.json")
    row = next(r for r in manifest["sets"] if r["unit"] == unit)
    docs = baseline.load_documents(dict(config=manifest["config"], inputs=[row["input"]]))
    model = model_class(docs, manifest["config"], baseline.Stationary, 0.2)
    orders = []
    for order in (64, 128):
        nodes, weights = timing.timing_nodes(order, model.models[0].taus)
        values = [track_scores(model, p, nodes) for p in row["positions"][1:]]
        a = decompose(values[0][0], weights, values[0][1])
        b = decompose(
            np.concatenate([v[0] for v in values[1:]]),
            np.tile(weights - np.log(3), 3),
            np.concatenate([v[1] for v in values[1:]]),
        )
        orders.append(
            dict(
                order=order,
                n24=a,
                mixture=b,
                track_delta=(np.array(a["expected_tracks"]) - b["expected_tracks"]).tolist(),
                kl_delta=b["kl"] - a["kl"],
            )
        )
    low, high = orders
    discrepancy = dict(
        track=float(max(abs(np.array(low["track_delta"]) - high["track_delta"]))),
        kl=abs(low["kl_delta"] - high["kl_delta"]),
        responsibility=max(
            float(
                max(
                    abs(
                        np.array(low[a]["signal_responsibility"]) - high[a]["signal_responsibility"]
                    )
                )
            )
            for a in ("n24", "mixture")
        ),
        log_score=max(abs(low[a]["log_score"] - high[a]["log_score"]) for a in ("n24", "mixture")),
        prior_score=max(
            abs(original["orders"][-1][a]["log_score"] - high[a]["log_score"])
            for a in ("n24", "mixture")
        ),
    )
    result = dict(
        original,
        orders=orders,
        discrepancy=discrepancy,
        qualified=bool(max(discrepancy.values()) <= 0.01 and original["scalar_error"] < 1e-7),
        original_sha256=digest(HERE / f"{unit}.json"),
        elapsed_seconds=time.monotonic() - started,
        refinement_hashes={p.name: digest(p) for p in (HERE / "refine.py", HERE / "REFINEMENT.md")},
    )
    save(HERE / f"{unit}.refined.json", result)
    print(unit, result["qualified"], discrepancy, flush=True)


def batch():
    units = [p.stem for p in sorted(HERE.glob("DS[789]_[0-4].json")) if not read(p)["qualified"]]

    def worker(unit):
        try:
            p = subprocess.run(
                [sys.executable, str(HERE / "refine.py"), unit],
                capture_output=True,
                text=True,
                timeout=180,
            )
            r = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        except subprocess.TimeoutExpired:
            r = dict(exit_code=None, timed_out=True)
        save(HERE / f"{unit}.refined.receipt.json", r)
        print(unit, r, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, units))


if __name__ == "__main__":
    if sys.argv[1] == "batch":
        batch()
    else:
        run(sys.argv[1])
