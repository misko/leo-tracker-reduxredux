import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def read(path):
    return json.loads(path.read_text())


def decompose(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    assert a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all()
    za, zb = np.logaddexp.reduce(a), np.logaddexp.reduce(b)
    la, lb = a - za, b - zb
    pa, pb = np.exp(la), np.exp(lb)
    frozen = float(pa @ (b - a))
    kl = float(pa @ (la - lb))
    delta = float(zb - za)
    error = abs(delta - frozen - kl)
    assert error < 1e-8 and kl > -1e-9
    return dict(delta=delta, frozen_gain=frozen, posterior_kl=kl, identity_error=error, total_variation=float(np.abs(pa - pb).sum() / 2), top_component_changed=bool(np.argmax(a) != np.argmax(b)), satellite_map_changed=bool(np.argmax(a[1:]) != np.argmax(b[1:])), signal_pool=float(1-pa[0]), signal_panel=float(1-pb[0]))


def main(ds):
    import hashlib

    started = time.monotonic()
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert hashlib.sha256((HERE.parents[1] / name).read_bytes()).hexdigest() == h, name
    helper = module("receiver", REPORTS / "2026_09_29_receiver_holdout/run.py")
    density = module("contrast_density_module", REPORTS / "2026_09_29_frequency_contrast/contrast_position.py").contrast_density
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    source = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    docs = helper.baseline.load_documents(dict(config=manifest["config"], inputs=[s["input"] for s in source["scans"]]))
    by_id = {d["session_id"]: d for d in docs}
    prior = read(REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json")
    assert prior["selected"]["qualified"]
    pool_x = prior["selected"]["x"]
    timing = dict(zip(prior["sessions"], pool_x[2:], strict=True))
    panels = []
    for family, suffixes in [("contiguous", ["early", "middle", "late"]), ("balanced", [0, 1, 2])]:
        for suffix in suffixes:
            panel = read(REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_{family}_{suffix}.json")
            selected = panel["selected"]
            assert selected["qualified"]
            subset = [by_id[s] for s in panel["sessions"]]
            model = helper.TrendMixturePosition(subset, manifest["config"], helper.baseline.Stationary, 0.2)
            source_x = [*pool_x[:2], *[timing[s] for s in panel["sessions"]]]
            endpoints = [source_x, selected["x"]]
            rows, sums = [], [0.0, 0.0]
            for di, (doc, engine) in enumerate(zip(subset, model.models, strict=True)):
                for ti, track in enumerate(doc["tracks"]):
                    components, visibility = [], []
                    for arm, x in enumerate(endpoints):
                        pred, visible = engine.prediction(track, [*x[:2], x[di+2]])
                        assert visible.any()
                        train, _ = density((track["y"][None, :] - pred)[:, track["mask"]])
                        a = np.r_[math.log(0.2) + model.background[di, ti][0], math.log(0.8) + train[visible] - math.log(int(visible.sum()))]
                        components.append(a)
                        visibility.append(visible)
                        sums[arm] += float(np.logaddexp.reduce(a))
                    stable = bool(np.array_equal(*visibility))
                    row = dict(session_id=doc["session_id"], track_id=track["track_id"], stable_support=stable)
                    if stable:
                        row.update(decompose(*components))
                    else:
                        row["delta"] = float(np.logaddexp.reduce(components[1]) - np.logaddexp.reduce(components[0]))
                    rows.append(row)
            pooled_replay = abs(sums[0] - model.evaluate(source_x, gradient=False)["score"])
            panel_replay = abs(sums[1] - selected["score"])
            assert max(pooled_replay, panel_replay) < 1e-7
            stable = [r for r in rows if r["stable_support"]]
            summary = dict(dataset=ds, family=family, panel=str(suffix), tracks=len(rows), stable_support=len(stable), training_gain=sums[1]-sums[0], frozen_gain=sum(r["frozen_gain"] for r in stable), posterior_kl=sum(r["posterior_kl"] for r in stable), top_component_changes=sum(r["top_component_changed"] for r in stable), satellite_map_changes=sum(r["satellite_map_changed"] for r in stable), mean_total_variation=float(np.mean([r["total_variation"] for r in stable])), signal_to_background=sum(r["signal_pool"]>=0.5 and r["signal_panel"]<0.5 for r in stable), background_to_signal=sum(r["signal_pool"]<0.5 and r["signal_panel"]>=0.5 for r in stable), max_identity_error=max(r["identity_error"] for r in stable), pooled_replay=pooled_replay, panel_replay=panel_replay)
            panels.append(dict(summary=summary, tracks=rows))
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(dict(panels=panels, elapsed_seconds=time.monotonic()-started), out, indent=2, allow_nan=False)
    print(ds, [p["summary"] for p in panels], flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
