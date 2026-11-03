import hashlib
import importlib.util
import inspect
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from surrogate import FrozenDenominator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def catalogue(meta):
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    archive = TleArchiveReader(
        Path(read(REPORTS / "2026_09_29_catalogue_recurrence/plan.json")["archive_root"])
    )
    refs = archive.list_snapshots()

    def payload(key):
        raw = archive.read(next(r for r in refs if r.digest == key))
        assert "sha256:" + hashlib.sha256(raw.encode()).hexdigest() == key
        return exclude_labelled_starlink_debris(raw)[0]

    records = list(parse_element_set_records(payload(meta["baseline_snapshot_sha256"])))
    choices = {}
    for source in meta["provider_sources"]:
        raw = payload(source["snapshot_sha256"])
        epochs = parse_element_sets(raw).element_epoch_utc_ns()
        for record, epoch in zip(parse_element_set_records(raw), epochs, strict=True):
            key = (epoch, source["collected_utc_ns"], source["snapshot_sha256"])
            if record.satellite_number not in choices or key > choices[record.satellite_number][0]:
                choices[record.satellite_number] = (key, record)
    result = parse_element_sets("".join(choices[r.satellite_number][1].text for r in records))
    assert list(result.satellite_numbers) == [r.satellite_number for r in records]
    assert len(result.satellite_numbers) == meta["catalogue_size"]
    return result


def exact_audit(base, inputs, x):
    import ds7_baseline_adapter as numerical
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from trend_mixture import contrast_density

    rows = []
    for di, (doc, engine, entry) in enumerate(
        zip(base.documents, base.models, inputs, strict=True)
    ):
        meta = read(
            Path(
                next(
                    a["path"]
                    for a in entry["artifacts"]
                    if a["kind"] == "candidates" and a["path"].endswith(".json")
                )
            )
        )
        cat = catalogue(meta)
        bankpath = Path(next(a["path"] for a in entry["artifacts"] if a["path"].endswith(".npz")))
        rec, up = numerical.site(*engine.coordinates([x[0], x[1], x[di + 2]]))
        with np.load(bankpath, allow_pickle=False) as bank:
            for ti, track in enumerate(doc["tracks"]):
                pos, vel, ids = propagate_candidate_states(
                    cat,
                    np.arange(len(cat.satellite_numbers)),
                    doc["start_utc_ns"],
                    np.asarray(track["times_s"]),
                    np.array([x[di + 2]]),
                )
                unit = pos[:, 0] - rec
                unit /= np.linalg.norm(unit, axis=-1)[..., None]
                prediction = (
                    -numerical.REFERENCE_RF_HZ
                    / numerical.LIGHT_KM_S
                    * np.sum(unit * vel[:, 0], axis=-1)
                )
                visible = np.any((unit @ up)[:, track["mask"]] >= 0, axis=1)
                index = next(
                    t["index"] for t in meta["tracks"] if t["track_id"] == track["track_id"]
                )
                retained = bank[f"candidate_ids_{index}"]
                keep = np.isin(ids, retained) & visible
                assert keep.any()
                values, _ = contrast_density((track["y"][None, :] - prediction)[:, track["mask"]])
                allsum = float(logsumexp(values[visible]))
                keepsum = float(logsumexp(values[keep]))
                exact = float(
                    np.logaddexp(
                        np.log(0.8) + allsum - np.log(visible.sum()),
                        np.log(0.2) + base.background[di, ti][0],
                    )
                )
                best = int(np.argmax(np.where(visible, values, -np.inf)))
                rows.append(
                    dict(
                        di=di,
                        ti=ti,
                        track_id=track["track_id"],
                        full_count=int(visible.sum()),
                        retained_count=int(keep.sum()),
                        retained_mass=float(np.exp(keepsum - allsum)),
                        best_retained=bool(keep[best]),
                        exact_score=exact,
                    )
                )
    return dict(
        rows=rows,
        exact_score=sum(r["exact_score"] for r in rows),
        runtime_source={
            inspect.getfile(propagate_candidate_states): sha(
                Path(inspect.getfile(propagate_candidate_states))
            )
        },
    )


def main(ds):
    started = time.monotonic()
    manifest = read(HERE / "manifest.json")
    for name, h in manifest["hashes"].items():
        assert sha(ROOT / name) == h, name
    helper = module("holdout_helper", REPORTS / "2026_09_29_curvature_scan_holdout/run.py")
    receiver = helper.receiver
    plan = read(REPORTS / "2026_09_29_donor_residual_transfer/plan.json")
    prior = read(REPORTS / f"2026_09_29_scan_holdout/{ds}_early_8_d0.json")
    for name, h in prior["hashes"].items():
        assert sha(ROOT / name) == h, name
    entry = next(u for u in plan["units"] if u["unit_id"] == f"{ds}_early_8")
    inputs = entry["group"]["inputs"]
    for item in inputs:
        for a in item["artifacts"]:
            assert "sha256:" + sha(Path(a["path"])) == a["sha256"]
    docs = receiver.baseline.load_documents(dict(config=plan["config"], inputs=inputs))
    source, target = docs[:4], docs[4:]
    assert [d["session_id"] for d in source] == prior["source_sessions"]
    assert [d["session_id"] for d in target] == prior["target_sessions"]
    assert not set(prior["source_sessions"]) & set(prior["target_sessions"])
    old = prior["arms"][0]
    assert old["qualified"]
    base = receiver.TrendMixturePosition(source, plan["config"], receiver.baseline.Stationary, 0.2)
    x = np.array(old["x"])
    assert abs(base.evaluate(x, gradient=False)["score"] - old["score"]) < 1e-7
    before = exact_audit(base, inputs[:4], x)
    counts = {(r["di"], r["ti"]): r["full_count"] for r in before["rows"]}
    surrogate = FrozenDenominator(base, counts)
    initial = surrogate.evaluate(x, gradient=False)["score"]
    fit = receiver.fit_model(surrogate, x)
    z = np.array(fit["x"])
    after = exact_audit(base, inputs[:4], z)
    fit["estimate_deg"] = list(base.models[0].coordinates(z[:3]))
    tests = []
    for doc in target:
        model = receiver.TrendMixturePosition(
            [doc], plan["config"], receiver.baseline.Stationary, 0.2
        )
        tests.append(
            dict(
                session_id=doc["session_id"],
                baseline=helper.marginal(model, x[:2]),
                surrogate=helper.marginal(model, z[:2]),
            )
        )
    result = dict(
        dataset=ds,
        source_sessions=prior["source_sessions"],
        target_sessions=prior["target_sessions"],
        baseline=old,
        initial_surrogate_score=initial,
        fit=fit,
        before=before,
        after=after,
        targets=tests,
        elapsed_seconds=time.monotonic() - started,
        manifest_sha256=sha(HERE / "manifest.json"),
    )
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    print(ds, fit["qualified"], fit["x"][:2], time.monotonic() - started, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
