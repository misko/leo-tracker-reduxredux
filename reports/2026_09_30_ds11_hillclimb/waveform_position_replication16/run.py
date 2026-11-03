"""Bounded matched IID refits with direct training-only waveform corrections."""
import concurrent.futures
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HILL.parents[1]
BASE = HILL.parent / "2026_09_30_ds11_single10"
WAVE = HILL / "waveform_replication16"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
ARMS = ("pilot_2_65", "pilot_22_221")
BOUNDS = [(-12., 12.), (-12., 12.), (-4.995, 4.995)]
SUPPORT = None


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def dependencies():
    global SUPPORT
    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_fast_baseline_adapter as fast
    if SUPPORT is None:
        SUPPORT = module('replication16_support_model', HILL / 'waveform_support_position/run.py')
    fast.Stationary = SUPPORT.SupportStationary
    fast.baseline.profile = fast.profile
    return (fast, module("waveform_position_timing", HILL / "timing/model.py"),
            module("waveform_position_harness", HILL / "harness.py"))


def patch_documents(documents, corrections):
    remaining = {(r["track_id"], r["observation_index"]): r for r in corrections}
    assert len(remaining) == len(corrections)
    patched = []
    for document in documents:
        tracks = []
        for track in document["tracks"]:
            y = track["y"].copy()
            shifts = np.zeros(len(y))
            for i in range(len(y)):
                row = remaining.pop((track["track_id"], i), None)
                if row is None:
                    continue
                assert track["mask"][i], "correction targets localization-held row"
                assert float(y[i]) == row["measured_hz"]
                assert float(track["times_s"][i]) == row["time_s"]
                assert track["visits"][i] == row["visit"]
                y[i] += row["delta_hz"]
                shifts[i] = row.get('nominal_support_shift_s', 0.)
                assert np.isfinite(shifts[i]) and -.005 < shifts[i] <= 0.
            np.testing.assert_array_equal(y[~track["mask"]], track["y"][~track["mask"]])
            tracks.append(dict(track, y=y, nominal_support_shift_s=shifts))
        patched.append(dict(document, tracks=tracks))
    assert not remaining, "correction targets absent model row"
    return patched


def audited_endpoint(model, x, success, harness):
    x = np.asarray(x)
    r = model.evaluate(x, gradient=True)
    discrepancies = []
    for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
        d = np.eye(3)[axis]*step
        finite = (model.evaluate(x+d, gradient=False)["score"] -
                  model.evaluate(x-d, gradient=False)["score"])/(2*step)
        discrepancies.append(abs(finite-r["gradient"][axis]))
    audit = float(max(discrepancies))
    qualified, boundary, maximum = harness.qualify(success, x, r["gradient"], audit, BOUNDS)
    return dict(x=x.tolist(), score=float(r["score"]), qualified=qualified,
                boundary=boundary, gradient_max_abs=maximum, audit_max_abs=audit)


def context(plan):
    for path, expected in plan["sources"].items():
        assert digest(path) == expected, path
    fast, timing, harness = dependencies()
    documents = fast.load_documents(dict(config=plan["config"], inputs=[plan["input"]]))
    return documents, fast, timing, harness


def nominal_center(epoch, arm):
    indices = np.arange(64) if arm == ARMS[0] else np.arange(20, 220)
    assert arm in ARMS
    centers = []
    for frame in range(8):
        frame_epoch = epoch + frame*5_000_000/750
        start = max(0, int(frame_epoch)-50)
        fft_starts = np.rint((frame_epoch-start)*48 + (indices+2)*1056 + 16)
        centers.extend(start/5_000_000 + (fft_starts+511.5)/240_000_000)
    return float(np.mean(centers))


def prepare():
    from types import SimpleNamespace
    from leo.application.scanner_trajectory import fractional_glrt64_support_geometry
    import inspect
    wave = read(WAVE / "manifest.json")
    measured_path = WAVE / "local/measurements.json"
    measured = read(measured_path)
    extraction_path = WAVE / "local/extraction.json"
    extraction = read(extraction_path)
    assert measured["plan_sha256"] == extraction["plan_sha256"] == digest(WAVE / "manifest.json")
    assert measured["extraction_sha256"] == digest(extraction_path)
    assert len(measured["rows"]) == len(wave["rows"]) == 124
    assert all(row["status"] == "ok" for row in extraction["rows"])
    for row in extraction["rows"]:
        assert digest(row["path"]) == row["sha256"]
    corrections = {arm: [] for arm in ARMS}
    for p, r in zip(wave["rows"], measured["rows"], strict=True):
        assert r["status"] == "ok"
        for key in ("ordinal", "track_id", "observation_index", "visit"):
            assert p[key] == r[key]
        for arm in ARMS:
            a = r["arms"][arm]
            assert not a["search_boundary"] and a["additive_alias"] == p["additive_alias"]
            delta = a["native_residual_hz"]*11.2e9/p["actual_rf_hz"]
            assert abs(delta-a["canonical_delta_hz"]) < 1e-9 and math.isfinite(delta)
            candidate = SimpleNamespace(**p['candidate'])
            support = fractional_glrt64_support_geometry(candidate, sample_rate_hz=5_000_000,
                                                         probe_sample_count=100_000)
            epoch = candidate.integer_epoch_sample + candidate.fractional_epoch_offset_samples
            shift = nominal_center(epoch, arm) - support.center_in_probe_samples/5_000_000
            corrections[arm].append(dict(
                **{k:p[k] for k in ("track_id", "observation_index", "visit", "time_s", "measured_hz")},
                delta_hz=delta, nominal_support_shift_s=shift))
    base = read(BASE / "plan.json")
    entry = base["inputs"][16]
    incumbent = read(BASE / "runs/16_iid.json")
    receipt = read(BASE / "runs/16_iid.receipt.json")
    assert receipt["exit_code"] == 0 and receipt["index"] == incumbent["index"] == 16
    assert receipt["method"] == incumbent["method"] == "iid"
    assert entry["session_id"] == incumbent["session"] == wave["session_id"]
    assert incumbent["selected"]["qualified"]
    sources = dict(wave["sources"])
    for artifact in entry["artifacts"]:
        expected = artifact["sha256"].removeprefix("sha256:")
        assert digest(artifact["path"]) == expected
        sources[artifact["path"]] = expected
    paths = [WAVE / "manifest.json", measured_path, extraction_path,
             BASE / "plan.json", BASE / "runs/16_iid.json", BASE / "runs/16_iid.receipt.json",
             HERE / "PROTOCOL.md", HERE / "run.py", HERE / "test_run.py",
             HILL / "harness.py", HILL / "timing/model.py",
             ROOT / "tools/ds7_baseline_adapter.py", ROOT / "tools/ds7_fast_baseline_adapter.py"]
    paths += sorted((WAVE / "attempts").glob("*.receipt.json"))
    paths += [HILL/'waveform_support_position/run.py', HILL/'norad65512_position/run.py',
              Path(inspect.getfile(fractional_glrt64_support_geometry))]
    for path in paths:
        sources[str(path.resolve())] = digest(path)
    plan = dict(schema="ds11-waveform-position-ablation/v1", reference_used=False,
                config=base["config"], input=entry, corrections=corrections, sources=sources,
                bounds=BOUNDS, effective_estimator_weighting_measured=False,
                measurement_time_policy='Nominal eight-frame FFT center for corrected training rows only')
    documents, fast, timing, harness = context(plan)
    model = timing.TimingModel(documents, plan["config"], "original")
    control = audited_endpoint(model, incumbent["selected"]["x"], True, harness)
    assert control["qualified"] and abs(control["score"]-incumbent["selected"]["score"]) < 1e-6
    control["estimate_deg"] = list(model.model.coordinates(np.asarray(control["x"])))
    for arm in ARMS:
        patch_documents(documents, corrections[arm])
    plan["control"] = control
    seeds = [control["x"]] + [[east, 0., 0.] for east in (-2., 0., 2.)]
    plan["jobs"] = [dict(arm=arm, seed_index=i, seed=seed) for arm in ARMS for i, seed in enumerate(seeds)]
    write(HERE / "plan.json", plan)
    print(json.dumps(dict(jobs=len(plan["jobs"]), correction_rows_per_arm=124,
                          replay_score_difference=control["score"]-incumbent["selected"]["score"])))


def held_score(documents, config, x, fast):
    geometry = fast.Stationary(documents[0], config)
    total = 0.
    for track in documents[0]["tracks"]:
        prediction, visible = geometry.prediction(track, np.asarray(x))
        train, joint, audits, _ = fast.profile(track["y"][None, :]-prediction, track["mask"])
        assert all(a["converged"] for a in audits)
        total += float(np.logaddexp.reduce(np.where(visible, joint, -np.inf)) -
                       np.logaddexp.reduce(np.where(visible, train, -np.inf)))
    return total


def fit(job_index):
    started = time.monotonic()
    plan_path = HERE / "plan.json"
    plan = read(plan_path)
    documents, fast, timing, harness = context(plan)
    job = plan["jobs"][job_index]
    changed = patch_documents(documents, plan["corrections"][job["arm"]])
    model = timing.TimingModel(changed, plan["config"], "original")
    def objective(x):
        r = model.evaluate(x, gradient=True)
        return -r["score"], -r["gradient"]
    result = minimize(objective, job["seed"], jac=True, method="L-BFGS-B", bounds=BOUNDS,
                      options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-6, maxls=25))
    endpoint = audited_endpoint(model, result.x, bool(result.success), harness)
    endpoint.update(success=bool(result.success), message=str(result.message),
                    nfev=int(result.nfev), nit=int(result.nit))
    if endpoint["qualified"]:
        endpoint.update(estimate_deg=list(model.model.coordinates(result.x)),
                        original_model_held_score=held_score(documents, plan["config"], result.x, fast),
                        corrected_training_held_score=held_score(changed, plan["config"], result.x, fast))
    write(HERE / "runs" / f"{job_index:02d}.json", dict(
        job_index=job_index, job=job, endpoint=endpoint, plan_sha256=digest(plan_path),
        reference_used=False, elapsed_s=time.monotonic()-started))


def batch():
    plan = read(HERE / "plan.json")
    (HERE / "runs").mkdir(exist_ok=True)
    def launch(index):
        path = HERE / "runs" / f"{index:02d}"
        assert not path.with_suffix(".json").exists() and not path.with_suffix(".receipt.json").exists()
        command = ["sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
                   "MKL_NUM_THREADS=1", "timeout", "--kill-after=5s", "90s", "nice", "-n", "19",
                   PYTHON, str(HERE / "run.py"), "fit", str(index)]
        started = time.monotonic()
        with path.with_suffix(".log").open("x") as log:
            done = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        row = dict(job_index=index, exit_code=done.returncode, wall_s=time.monotonic()-started,
                   command=command, plan_sha256=digest(HERE / "plan.json"))
        write(path.with_suffix(".receipt.json"), row)
        print(json.dumps(row), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(launch, range(len(plan["jobs"]))))


def assess():
    plan = read(HERE / "plan.json")
    documents, fast, timing, harness = context(plan)
    records = []
    for i, job in enumerate(plan["jobs"]):
        receipt = read(HERE / "runs" / f"{i:02d}.receipt.json")
        assert receipt["job_index"] == i and receipt["plan_sha256"] == digest(HERE / "plan.json")
        path = HERE / "runs" / f"{i:02d}.json"
        r = read(path) if receipt["exit_code"] == 0 and path.exists() else None
        if r:
            assert r["job_index"] == i and r["job"] == job and r["plan_sha256"] == receipt["plan_sha256"]
        records.append(dict(job=job, receipt=receipt, result=r))
    selected = {}
    for arm in ARMS:
        valid = [r["result"]["endpoint"] for r in records if r["job"]["arm"] == arm
                 and r["result"] and r["result"]["endpoint"]["qualified"]]
        selected[arm] = max(valid, key=lambda r:r["score"]) if valid else None
    complete = all(selected.values())
    write(HERE / "selections.json", dict(selected=selected, complete=complete,
          reference_used=False, plan_sha256=digest(HERE / "plan.json")))
    result = dict(schema="ds11-waveform-position-outcome/v1", attempts=records,
                  selected=selected, control=plan["control"], geographic_errors_evaluated=complete,
                  model_promotion=False, plan_sha256=digest(HERE / "plan.json"))
    if complete:
        for row in [result["control"]] + list(selected.values()):
            row["error_m"] = harness.distance(row["estimate_deg"])
        result["control"]["original_model_held_score"] = held_score(documents, plan["config"], plan["control"]["x"], fast)
    paths = [HERE / "plan.json", HERE / "run.py", HERE / "selections.json"] + sorted((HERE / "runs").glob("*.json"))
    result["sources"] = {str(p):digest(p) for p in paths}
    write(HERE / "outcome.json", result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("attempts", "sources")}, indent=2))


if __name__ == "__main__":
    if sys.argv[1] == "fit":
        fit(int(sys.argv[2]))
    else:
        {"prepare":prepare, "batch":batch, "assess":assess}[sys.argv[1]]()
