import concurrent.futures
import importlib.util
import math
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_prediction_attribution"
spec = importlib.util.spec_from_file_location("attribution_study", PRIOR / "study.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
read, save, digest = prior.read, prior.save, prior.digest


def prepare():
    summary = read(PRIOR / "summary.json")
    assert summary["complete"]
    targets = summary["top_losses"]
    assert len(targets) == 20
    paths = [
        HERE / "study.py",
        HERE / "PROTOCOL.md",
        PRIOR / "summary.json",
        HERE.parent / "2026_09_29_catalogue_recurrence/result.json",
    ]
    for name, expected in read(PRIOR / "manifest.json")["hashes"].items():
        assert digest(ROOT / name) == expected
        paths.append(ROOT / name)
    for unit in sorted({r["unit"] for r in targets}):
        paths.append(PRIOR / f"{unit}.json")
    save(
        HERE / "manifest.json",
        dict(targets=targets, hashes={str(p.relative_to(ROOT)): digest(p) for p in paths}),
    )


def candidate_joint(engine, track, position, times, track_log_scores):
    import ds7_baseline_adapter as numerical
    import numpy as np
    from trend_mixture import contrast_density

    rec, up = numerical.site(*engine.coordinates([*position, 0.0]))
    grid = engine.taus
    result = np.zeros((len(times), len(track["candidate_position_km"])))
    for start in range(0, len(times), 32):
        t = times[start : start + 32]
        hi = np.clip(np.searchsorted(grid, t, side="right"), 1, len(grid) - 1)
        lo = hi - 1
        weight = ((t - grid[lo]) / (grid[hi] - grid[lo]))[None, :, None, None]
        pb, vb = track["candidate_position_km"], track["candidate_velocity_km_s"]
        pos = pb[:, lo] * (1 - weight) + pb[:, hi] * weight
        vel = vb[:, lo] * (1 - weight) + vb[:, hi] * weight
        unit = pos - rec
        unit /= np.linalg.norm(unit, axis=-1)[..., None]
        prediction = -numerical.REFERENCE_RF_HZ / numerical.LIGHT_KM_S * np.sum(unit * vel, axis=-1)
        visible = np.any((unit @ up)[:, :, track["mask"]] >= 0, axis=2)
        count = visible.sum(axis=0)
        assert np.all(count > 0)
        residual = track["y"][None, None, :] - prediction
        density, _ = contrast_density(residual.reshape(-1, len(track["y"])))
        density = density.reshape(prediction.shape[:2])
        logjoint = math.log(0.8) + np.where(visible, density, -np.inf) - np.log(count)
        result[start : start + len(t)] = np.exp(
            logjoint.T - track_log_scores[start : start + len(t), None]
        )
    return result


def run(unit):
    import numpy as np
    from scipy.special import logsumexp

    baseline, timing, model_class = prior.source.numerical_imports()
    sys.path.insert(0, str(PRIOR))
    from model import track_scores

    started = time.monotonic()
    frozen = read(HERE / "manifest.json")
    targets = [r for r in frozen["targets"] if r["unit"] == unit]
    manifest = read(prior.SOURCE / "manifest.json")
    spec = next(r for r in manifest["sets"] if r["unit"] == unit)
    docs = baseline.load_documents(dict(config=manifest["config"], inputs=[spec["input"]]))
    model = model_class(docs, manifest["config"], baseline.Stationary, 0.2)
    mapping = {
        s["session_id"]: {t["track_id"]: t["numbers"] for t in s["tracks"]}
        for s in read(HERE.parent / "2026_09_29_catalogue_recurrence/result.json")["scans"]
    }
    slots = {t["track_id"]: i for i, t in enumerate(docs[0]["tracks"])}
    original = read(prior.SOURCE / f"{unit}.json")
    orders = []
    max_replay = 0.0
    max_signal_replay = 0.0
    for order in (32, 64):
        times, weights = timing.timing_nodes(order, model.models[0].taus)
        arrays = []
        joints = {r["track_id"]: [] for r in targets}
        for index, position in enumerate(spec["positions"][1:], start=1):
            score, signal = track_scores(model, position, times)
            arrays.append(score.sum(axis=1))
            if order == 32:
                max_replay = max(
                    max_replay,
                    abs(
                        float(logsumexp(arrays[-1] + weights))
                        - original["values"][index]["audit_log_score"]
                    ),
                )
            for row in targets:
                ti = slots[row["track_id"]]
                track = docs[0]["tracks"][ti]
                joint = candidate_joint(model.models[0], track, position, times, score[:, ti])
                max_signal_replay = max(
                    max_signal_replay, float(max(abs(joint.sum(axis=1) - signal[:, ti])))
                )
                joints[row["track_id"]].append(joint)
        results = []
        evidence = []
        for component in ([0], [1, 2, 3]):
            logmass = np.concatenate(
                [arrays[i] + weights - math.log(len(component)) for i in component]
            )
            z = float(logsumexp(logmass))
            evidence.append(z)
            posterior = np.exp(logmass - z)
            rows = []
            for target in targets:
                track_id = target["track_id"]
                joint = posterior @ np.concatenate([joints[track_id][i] for i in component])
                probability = float(joint.sum())
                conditional = joint / probability
                numbers = mapping[docs[0]["session_id"]][track_id]
                assert len(numbers) == len(conditional) and len(set(numbers)) == len(numbers)
                best = int(np.argmax(conditional))
                rows.append(
                    dict(
                        track_id=track_id,
                        numbers=numbers,
                        conditional=conditional.tolist(),
                        signal_probability=probability,
                        top_number=numbers[best],
                        top_probability=float(conditional[best]),
                    )
                )
            results.append(rows)
        orders.append(dict(order=order, arms=results, evidence=evidence))
    low, high = orders
    error = max(abs(a - b) for a, b in zip(low["evidence"], high["evidence"], strict=True))
    probability_error = 0.0
    stable = True
    for loarm, hiarm in zip(low["arms"], high["arms"], strict=True):
        for lo, hi in zip(loarm, hiarm, strict=True):
            probability_error = max(
                probability_error, float(max(abs(np.array(lo["conditional"]) - hi["conditional"])))
            )
            stable &= lo["top_number"] == hi["top_number"]
    # Independent scalar replay for the selected tracks at fixed diagnostic times.
    scalar_error = 0.0
    from trend_mixture import contrast_density

    for position in spec["positions"][1:]:
        for t in (-5, 0, 5):
            full, signal = track_scores(model, position, np.array([t]))
            for target in targets:
                ti = slots[target["track_id"]]
                track = docs[0]["tracks"][ti]
                pred, visible = model.models[0].prediction(track, [*position, t])
                density, _ = contrast_density(track["y"][None, :] - pred)
                scalar = float(
                    np.logaddexp(
                        math.log(0.8) + logsumexp(density[visible]) - math.log(sum(visible)),
                        math.log(0.2) + model.background[0, ti][1],
                    )
                )
                scalar_error = max(scalar_error, abs(scalar - full[0, ti]))
    qualified = bool(
        error <= 0.01
        and probability_error <= 0.001
        and stable
        and max_replay < 1e-7
        and scalar_error < 1e-7
        and max_signal_replay < 1e-7
    )
    save(
        HERE / f"{unit}.json",
        dict(
            unit=unit,
            orders=orders,
            qualified=qualified,
            log_score_difference=error,
            probability_difference=probability_error,
            stable_labels=bool(stable),
            replay_error=max_replay,
            scalar_error=scalar_error,
            signal_replay_error=max_signal_replay,
            elapsed_seconds=time.monotonic() - started,
            manifest_sha256=digest(HERE / "manifest.json"),
        ),
    )
    print(unit, qualified, probability_error, flush=True)


def batch():
    manifest = read(HERE / "manifest.json")
    for name, expected in manifest["hashes"].items():
        assert digest(ROOT / name) == expected, name

    def worker(unit):
        try:
            p = subprocess.run(
                [sys.executable, str(HERE / "study.py"), "run", unit],
                capture_output=True,
                text=True,
                timeout=180,
            )
            r = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        except subprocess.TimeoutExpired:
            r = dict(exit_code=None, timed_out=True)
        save(HERE / f"{unit}.receipt.json", r)
        print(unit, r, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, sorted({r["unit"] for r in manifest["targets"]})))


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "batch":
        batch()
    elif sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        raise ValueError("Unknown command")
