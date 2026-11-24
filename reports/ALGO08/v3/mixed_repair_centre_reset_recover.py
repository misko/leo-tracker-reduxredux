"""Verify retained standard products without re-entering the failed saved child."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
sys.path[:0] = [str(HERE), str(RELEASE / "src"), str(HERE.parents[2])]
from mixed_repair_centre_reset_trial import CAMPAIGN, CASE, CHARTED, digest, metadata, save, verified


EARLY = Path("/dev/shm/leo-v3-mixed-repair-centre-reset-0220-01")
NUMERICAL = Path("/dev/shm/leo-v3-mixed-repair-centre-reset-0220-02")
EARLY_CLOCK = "b7797ad1fb472c9368367c2212d597f3325cc76a1b670d6a5661829041ce5e07"
NUMERICAL_CLOCK = "5c1c8f350170e8a7158f0057c38aa6e3f5f2bff3e474de4efb731adaedb8f9c8"
ARMS = ("c0", "fitted_c")


def next_official(clock):
    trigger = clock["official_deferral"]
    files = sorted((CAMPAIGN / "cases" / trigger["case"] / "events").glob("*.json"))
    later = [(int(p.name.split("-", 1)[0]), p) for p in files if p.name > Path(trigger["event"]).name]
    stamp, path = later[0]
    return dict(path=str(path.relative_to(CAMPAIGN)), sha256=digest(path), state=json.loads(path.read_bytes())["state"],
                elapsed_s_from_deferral=(stamp-trigger["unix_ns"])/1e9,
                elapsed_s_after_child_exit=(stamp-clock["finished_ns"])/1e9)


def observation(output):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from PIL import Image

    _, mixed, charted, original, _, _, _ = metadata(CASE)
    began, cpu = perf_counter(), process_time()
    snapshots = {}
    for name, root, pin in (("setup_failure", EARLY, EARLY_CLOCK), ("numerical", NUMERICAL, NUMERICAL_CLOCK)):
        clock = verified(root / "clock.json", pin)
        seal = json.loads((root / "prediction-seal.json").read_bytes())
        assert seal["clock_sha256"] == pin and clock["exit_code"] == 1 and seal["worker_sha256"] is None
        snapshots[name] = dict(clock=clock, clock_sha256=pin, prediction_seal_sha256=digest(root / "prediction-seal.json"),
                               plan_sha256=seal["plan_sha256"], stderr_sha256=digest(root / "stderr"),
                               next_official=next_official(clock))
    clock = snapshots["numerical"]["clock"]
    cell = NUMERICAL / "cell"
    terminal_file, = cell.glob("fast-scan-automatic-work/*/terminal.json")
    native_file, = cell.glob("fast-scan-automatic-work/*/detections.json")
    original_authority = mixed["raw_identity"]
    terminal_sha = "sha256:" + digest(terminal_file)
    terminal = json.loads(terminal_file.read_bytes())
    assert "sha256:" + digest(native_file) == terminal["native_sha256"] == mixed["native_sha256"]
    assert terminal["decision"] == "ok" and terminal["region"] == mixed["evidence"]["receipt"]["region"]
    assert clock["started_ns"] < terminal_file.stat().st_mtime_ns < clock["finished_ns"]
    assert set(terminal["arms"]) == set(ARMS)
    session = original_authority["session_id"]
    assert terminal["session_id"] == session
    assert "sha256:" + digest(cell / "fast-scan-inputs" / (session + ".json")) == original_authority["inventory_sha256"]
    store = FastStandardAnalysisStore(cell)
    run = terminal_file.parent.name
    detail, grid, path = store.detail(run), store.position_grid(run), store.position_path(run)
    assert detail["state"] == "complete" and detail["terminal_sha256"] == terminal_sha
    assert detail["raw_authority"] == original_authority["raw_authority_sha256"] and detail["input_sha256"] == mixed["native_sha256"]
    assert grid["complete"] and grid["evaluated_points"] == 179
    stage, = path["stages"]
    figures = {}
    for item in detail["artifacts"]:
        encoded = store.artifact(run, item["name"], item["sha256"])
        with Image.open(BytesIO(encoded)) as image:
            assert image.format == "PNG"
            figures[item["name"]] = dict(encoded_sha256=item["sha256"], dimensions=image.size,
                                         rgba_sha256=sha256(image.convert("RGBA").tobytes()).hexdigest())
    assert len(figures) == 8
    assert grid["binding"] == path["binding"]
    assert path["binding"]["position_png_sha256"] == figures["position"]["encoded_sha256"]
    results = {}
    for arm in ARMS:
        rows = stage["arms"][arm]
        fitted = terminal["arms"][arm]
        standard = detail["arms"][arm]
        owner_hash = standard["owner_sha256"]
        assert owner_hash == charted["evidence"]["owner_maps"][arm] == path["binding"]["owner_sha256"][arm]
        assert fitted["latlon"] == standard["endpoint_latlon"] == grid["endpoint_latlon"][arm]
        assert all(math.isfinite(value) for value in (*fitted["latlon"], fitted["rf_rms_hz"]))
        rounds = rows["rounds"]
        assert rows["history_available"] and rounds[0]["points"][0] == [0.0, 0.0]
        assert len(rounds) == 4 and original["repair"]["finish"][arm]["phase_refreshes"] == 2
        results[arm] = dict(latlon=fitted["latlon"], east_north_km=rows["endpoint"], owner_sha256=owner_hash,
                            associated_points=standard["associated_points"], rf_rms_hz=fitted["rf_rms_hz"],
                            all_owned_rf_rms_hz=standard["residual_rms_hz"], first_point=rounds[0]["points"][0],
                            phase_changes_s=[x["phase_change_s"] for x in rounds])
    source_manifest = {name: dict(expected=pin, archived=digest(CHARTED / name), local=digest(HERE.parents[2] / name))
                       for name, pin in charted["source_sha256"].items()}
    assert all(row["expected"] == row["archived"] for row in source_manifest.values())
    save(output, dict(case=CASE, child_exit=1, full_worker_witness_available=False, provenance_complete=False,
                      reset_invocation_confirmed_by_product_path=True, incremental_reset_clocks_s=None,
                      ordered_role_rows_independently_available=False, runs=snapshots, arms=results,
                      terminal_sha256=terminal_sha, native_sha256=mixed["native_sha256"], figures=figures,
                      grid_points=grid["evaluated_points"], numerical_sidecars={k:digest(p) for k,p in (
                          (key, next(cell.glob("**/position-" + key + ".json"))) for key in ("grid", "path"))},
                      source_files_by_logical_name=source_manifest,
                      verified_after_release=dict(elapsed_s=perf_counter()-began, cpu_s=process_time()-cpu),
                      raw_timing_credit=0))


def score(science, pin, output):
    from sparse8_cfo_epoch_trial import geography
    from tools.pipeline_eval.scoring import distance_km

    recovered = verified(science, pin)
    _, mixed, _, _, _, _, saved = metadata(CASE)
    controls = json.loads((saved / "score.json").read_bytes())["arms"]
    reference = geography(CASE)
    result = {}
    for arm in ARMS:
        trial = distance_km(reference, recovered["arms"][arm]["latlon"])
        current = controls[arm]["error_km"]["charted/mixed"]
        named = controls[arm]["error_km"]["installed/mixed"]
        delta = distance_km(mixed["evidence"]["arms"][arm]["latlon"], recovered["arms"][arm]["latlon"])
        result[arm] = dict(trial_error_km=trial, charted_mixed_error_km=current, installed_mixed_error_km=named,
                           change_from_charted_mixed_m=1000*(trial-current),
                           excess_over_installed_mixed_m=1000*(trial-named),
                           displacement_from_charted_mixed_m=1000*delta)
    passed = all(x["change_from_charted_mixed_m"] < 0 and x["excess_over_installed_mixed_m"] <= 250
                 for x in result.values())
    save(output, dict(case=CASE, recovered_product_only=True, science_receipt_sha256=pin, arms=result,
                      improvement_gate=passed, advance=False, raw_timing_credit=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--science", type=Path)
    parser.add_argument("--pin")
    args = parser.parse_args()
    if args.science is None:
        observation(args.output)
    else:
        score(args.science, args.pin, args.output)
