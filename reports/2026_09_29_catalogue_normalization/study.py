import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)


def prepare():
    source = HERE.parent / "2026_09_29_out_of_pool/manifest.json"
    m = read(source)
    paths = [source, HERE / "study.py", HERE / "PROTOCOL.md"]
    units = []
    for ds in ("DS7", "DS8", "DS9"):
        row = min(
            (r for r in m["sets"] if r["dataset"] == ds),
            key=lambda r: (r["start_utc_ns"], r["input"]["session_id"]),
        )
        for a in row["input"]["artifacts"]:
            p = Path(a["path"])
            assert "sha256:" + digest(p) == a["sha256"]
            paths.append(p)
        bank = read(
            Path(
                next(
                    a["path"]
                    for a in row["input"]["artifacts"]
                    if a["kind"] == "candidates" and a["path"].endswith(".json")
                )
            )
        )
        tracks = sorted(t["track_id"] for t in bank["tracks"])
        assert tracks
        units.append(
            dict(dataset=ds, input=row["input"], positions=row["positions"], track_ids=tracks)
        )
    for name in (
        "tools/ds7_baseline_adapter.py",
        "tools/ds7_fast_baseline_adapter.py",
        "reports/2026_09_29_unassociated_trend/trend_mixture.py",
        "reports/2026_09_29_frequency_contrast/contrast_position.py",
    ):
        paths.append(ROOT / name)
    save(
        HERE / "manifest.json",
        dict(
            config=m["config"],
            units=units,
            hashes={str(p.relative_to(ROOT)): digest(p) for p in paths},
        ),
    )


def run(ds):
    import inspect
    import time

    import numpy as np
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from scipy.special import logsumexp

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    sys.path[:0] = [str(ROOT / "tools"), str(HERE.parent / "2026_09_29_unassociated_trend")]
    import ds7_baseline_adapter as numerical
    import ds7_fast_baseline_adapter as baseline
    from trend_mixture import TrendMixturePosition, contrast_density

    started = time.monotonic()
    m = read(HERE / "manifest.json")
    for name, h in m["hashes"].items():
        assert digest(ROOT / name) == h, name
    unit = next(u for u in m["units"] if u["dataset"] == ds)
    meta = read(
        Path(
            next(
                a["path"]
                for a in unit["input"]["artifacts"]
                if a["kind"] == "candidates" and a["path"].endswith(".json")
            )
        )
    )
    archive_root = read(HERE.parent / "2026_09_29_catalogue_recurrence/plan.json")["archive_root"]
    archive = TleArchiveReader(Path(archive_root))
    refs = archive.list_snapshots()
    payload_hashes = []

    def payload(key):
        ref = next(r for r in refs if r.digest == key)
        raw = archive.read(ref)
        assert "sha256:" + hashlib.sha256(raw.encode()).hexdigest() == key
        payload_hashes.append(key)
        return exclude_labelled_starlink_debris(raw)[0]

    base_records = list(parse_element_set_records(payload(meta["baseline_snapshot_sha256"])))
    choices = {}
    for s in meta["provider_sources"]:
        raw = payload(s["snapshot_sha256"])
        records = parse_element_set_records(raw)
        epochs = parse_element_sets(raw).element_epoch_utc_ns()
        for record, epoch in zip(records, epochs, strict=True):
            key = (epoch, s["collected_utc_ns"], s["snapshot_sha256"])
            if record.satellite_number not in choices or key > choices[record.satellite_number][0]:
                choices[record.satellite_number] = (key, record)
    catalogue = parse_element_sets(
        "".join(choices[r.satellite_number][1].text for r in base_records)
    )
    assert list(catalogue.satellite_numbers) == [r.satellite_number for r in base_records]
    assert len(catalogue.satellite_numbers) == meta["catalogue_size"]
    docs = baseline.load_documents(dict(config=m["config"], inputs=[unit["input"]]))
    model = TrendMixturePosition(docs, m["config"], baseline.Stationary, 0.2)
    engine = model.models[0]
    locations = [
        (label, *position)
        for label, position in zip(
            ("center", "n24", "n8_0", "n8_1", "n8_2"), unit["positions"], strict=True
        )
    ]
    taus = [-5.0, 0.0, 5.0]
    bankpath = Path(
        next(a["path"] for a in unit["input"]["artifacts"] if a["path"].endswith(".npz"))
    )
    rows = []
    with np.load(bankpath, allow_pickle=False) as bank:
        for ti, track in enumerate(docs[0]["tracks"]):
            if track["track_id"] not in unit["track_ids"]:
                continue
            pos, vel, ids = propagate_candidate_states(
                catalogue,
                np.arange(len(catalogue.satellite_numbers)),
                docs[0]["start_utc_ns"],
                np.asarray(track["times_s"]),
                np.array(taus),
            )
            index = next(t["index"] for t in meta["tracks"] if t["track_id"] == track["track_id"])
            retained = bank[f"candidate_ids_{index}"]
            lookup = {int(v): i for i, v in enumerate(ids)}
            slots = [lookup[int(v)] for v in retained]
            retained_mask = np.isin(ids, retained)
            for label, east, north in locations:
                rec, up = numerical.site(*engine.coordinates([east, north, 0]))
                for tau_index, tau in enumerate(taus):
                    direction = pos[:, tau_index] - rec
                    direction /= np.linalg.norm(direction, axis=-1)[..., None]
                    prediction = (
                        -numerical.REFERENCE_RF_HZ
                        / numerical.LIGHT_KM_S
                        * np.sum(direction * vel[:, tau_index], axis=-1)
                    )
                    visible = np.any((direction @ up)[:, track["mask"]] >= 0, axis=1)
                    cached, cached_visible = engine.prediction(track, [east, north, tau])
                    replay = float(np.max(abs(cached - prediction[slots])))
                    assert replay < 1e-6
                    np.testing.assert_array_equal(cached_visible, visible[slots])
                    keep = retained_mask & visible
                    omitted = ~retained_mask & visible
                    assert keep.any() and omitted.any()
                    stats = []
                    for selected, bg in (
                        (track["mask"], model.background[0, ti][0]),
                        (np.ones(len(track["y"]), bool), model.background[0, ti][1]),
                    ):
                        density, _ = contrast_density(
                            (track["y"][None, :] - prediction)[:, selected]
                        )
                        fullsum = float(logsumexp(density[visible]))
                        keepsum = float(logsumexp(density[keep]))
                        omittedsum = float(logsumexp(density[omitted]))
                        best = int(np.argmax(np.where(visible, density, -np.inf)))
                        fullsignal = np.log(0.8) + fullsum - np.log(visible.sum())
                        shortsignal = np.log(0.8) + keepsum - np.log(keep.sum())
                        stats.append(
                            dict(
                                retained_log_score=float(
                                    np.logaddexp(shortsignal, np.log(0.2) + bg)
                                ),
                                denominator_only_log_score=float(
                                    np.logaddexp(
                                        np.log(0.8) + keepsum - np.log(visible.sum()),
                                        np.log(0.2) + bg,
                                    )
                                ),
                                exact_full_log_score=float(
                                    np.logaddexp(fullsignal, np.log(0.2) + bg)
                                ),
                                retained_mass=float(np.exp(keepsum - fullsum)),
                                log_omitted_mass=omittedsum - fullsum,
                                best_number=int(catalogue.satellite_numbers[ids[best]]),
                                best_retained=bool(keep[best]),
                                full_signal_probability=float(
                                    np.exp(fullsignal - np.logaddexp(fullsignal, np.log(0.2) + bg))
                                ),
                                retained_signal_probability=float(
                                    np.exp(
                                        shortsignal - np.logaddexp(shortsignal, np.log(0.2) + bg)
                                    )
                                ),
                            )
                        )
                    rows.append(
                        dict(
                            track_id=track["track_id"],
                            location_class=label,
                            east_km=east,
                            north_km=north,
                            tau_s=tau,
                            catalogue_size=len(catalogue.satellite_numbers),
                            valid=len(ids),
                            visible=int(visible.sum()),
                            retained_visible=int(keep.sum()),
                            prediction_replay_hz=replay,
                            training=stats[0],
                            full=stats[1],
                        )
                    )
    replay_scores = []
    for label, east, north in locations:
        for tau in taus:
            selected_rows = [r for r in rows if r["location_class"] == label and r["tau_s"] == tau]
            assert len(selected_rows) == len(docs[0]["tracks"])
            scalar = model.evaluate([east, north, tau], gradient=False, held=True)
            train = sum(r["training"]["retained_log_score"] for r in selected_rows)
            full = sum(r["full"]["retained_log_score"] for r in selected_rows)
            error = max(
                abs(train - scalar["score"]),
                abs(full - scalar["score"] - sum(r["held_log_score"] for r in scalar["rows"])),
            )
            assert error < 1e-7
            replay_scores.append(dict(location=label, tau_s=tau, error=error))
    runtime = {
        str(Path(inspect.getfile(f))): digest(Path(inspect.getfile(f)))
        for f in (propagate_candidate_states, parse_element_sets, TleArchiveReader)
    }
    save(
        HERE / f"{ds}.json",
        dict(
            dataset=ds,
            rows=rows,
            score_replay=replay_scores,
            payload_hashes=payload_hashes,
            runtime_sources=runtime,
            manifest_sha256=digest(HERE / "manifest.json"),
            elapsed_seconds=time.monotonic() - started,
        ),
    )
    print(
        ds,
        len(rows),
        "settings; minimum training mass",
        min(r["training"]["retained_mass"] for r in rows),
        flush=True,
    )


def batch():
    def worker(ds):
        try:
            p = subprocess.run(
                ["sudo", "-n", PYTHON, str(HERE / "study.py"), "run", ds],
                capture_output=True,
                text=True,
                timeout=180,
            )
            receipt = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        except subprocess.TimeoutExpired:
            receipt = dict(exit_code=None, timed_out=True)
        save(HERE / f"{ds}.receipt.json", receipt)
        print(ds, receipt, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, ("DS7", "DS8", "DS9")))


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "run":
        run(sys.argv[2])
    elif sys.argv[1] == "batch":
        batch()
    else:
        raise ValueError("Unknown command")
