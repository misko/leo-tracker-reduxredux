import concurrent.futures
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE.parent / "2026_09_29_out_of_pool"
spec = importlib.util.spec_from_file_location("source_study", SOURCE / "study.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
read, save, digest = source.read, source.save, source.digest


def prepare():
    manifest = read(SOURCE / "manifest.json")
    paths = [SOURCE / "manifest.json", HERE / "study.py", HERE / "model.py", HERE / "PROTOCOL.md"]
    for name, expected in manifest["hashes"].items():
        assert digest(ROOT / name) == expected, name
        paths.append(ROOT / name)
    for row in manifest["sets"]:
        p = SOURCE / f"{row['unit']}.json"
        assert all(v["qualified"] for v in read(p)["values"])
        paths.append(p)
    save(
        HERE / "manifest.json",
        dict(
            source=str((SOURCE / "manifest.json").relative_to(ROOT)),
            hashes={str(p.relative_to(ROOT)): digest(p) for p in paths},
        ),
    )


def run(unit):
    import numpy as np
    from scipy.special import logsumexp

    baseline, timing, model_class = source.numerical_imports()
    from model import decompose, track_scores

    started = time.monotonic()
    manifest = read(SOURCE / "manifest.json")
    row = next(r for r in manifest["sets"] if r["unit"] == unit)
    docs = baseline.load_documents(dict(config=manifest["config"], inputs=[row["input"]]))
    model = model_class(docs, manifest["config"], baseline.Stationary, 0.2)
    original = read(SOURCE / f"{unit}.json")
    orders = []
    for order in (16, 32):
        nodes, logweights = timing.timing_nodes(order, model.models[0].taus)
        arrays, responsibilities = [], []
        replays = []
        for index, position in enumerate(row["positions"][1:], start=1):
            score, signal = track_scores(model, position, nodes)
            arrays.append(score)
            responsibilities.append(signal)
            expected = original["values"][index]["log_score" if order == 16 else "audit_log_score"]
            replays.append(abs(float(logsumexp(score.sum(axis=1) + logweights)) - expected))
        n24 = decompose(arrays[0], logweights, responsibilities[0])
        mixture = decompose(
            np.concatenate(arrays[1:]),
            np.tile(logweights - np.log(3), 3),
            np.concatenate(responsibilities[1:]),
        )
        orders.append(
            dict(
                order=order,
                n24=n24,
                mixture=mixture,
                replay_error=max(replays),
                track_delta=(
                    np.array(n24["expected_tracks"]) - mixture["expected_tracks"]
                ).tolist(),
                kl_delta=mixture["kl"] - n24["kl"],
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
    )
    scalar_error = 0.0
    for position in row["positions"][1:]:
        times = [-5, -2.375, 0, 1.125, 5]
        score, _ = track_scores(model, position, times)
        for t, value in zip(times, score.sum(axis=1), strict=True):
            scalar = model.evaluate([*position, t], gradient=False, held=True)
            full = scalar["score"] + sum(r["held_log_score"] for r in scalar["rows"])
            scalar_error = max(scalar_error, abs(float(value) - full))
    qualified = bool(
        max(discrepancy.values()) <= 0.01
        and scalar_error < 1e-7
        and max(o["replay_error"] for o in orders) < 1e-7
    )
    tracks = [
        dict(
            track_id=t["track_id"],
            receiver_id=int(t["receiver_id"]),
            rf_hz=float(t["rf_hz"]),
            observations=len(t["y"]),
        )
        for t in docs[0]["tracks"]
    ]
    save(
        HERE / f"{unit}.json",
        dict(
            unit=unit,
            tracks=tracks,
            orders=orders,
            qualified=qualified,
            discrepancy=discrepancy,
            scalar_error=scalar_error,
            elapsed_seconds=time.monotonic() - started,
            manifest_sha256=digest(HERE / "manifest.json"),
        ),
    )
    print(unit, qualified, discrepancy, flush=True)


def batch():
    for name, expected in read(HERE / "manifest.json")["hashes"].items():
        assert digest(ROOT / name) == expected, name

    def worker(row):
        unit = row["unit"]
        try:
            p = subprocess.run(
                [sys.executable, str(HERE / "study.py"), "run", unit],
                capture_output=True,
                text=True,
                timeout=180,
            )
            receipt = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        except subprocess.TimeoutExpired:
            receipt = dict(exit_code=None, timed_out=True)
        save(HERE / f"{unit}.receipt.json", receipt)
        print(unit, receipt, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, read(SOURCE / "manifest.json")["sets"]))


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "batch":
        batch()
    elif sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        raise ValueError("Unknown command")
