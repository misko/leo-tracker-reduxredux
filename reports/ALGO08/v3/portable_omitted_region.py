"""Replay a held-out geographic offer from one verified physical detector packet."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
INDEX = Path("/dev/shm/leo-v3-portable-orbit-prep-02/dense-orbits.bin")
INDEX_PIN = "sha256:fc51655ff19185cc382aeed925e466cea7290453256d45f80446aceef6f9e30e"
BIND_PIN = "c1c2f5d911c978ad7673a2a53f05e272806f87c539f2f0a552b7e02916fe9c8b"
MODES = ("portable", "ordinary")


def translated(offer):
    result = dict(offer)
    for key in ("center", "screen_center"):
        lat, lon = offer[key]
        result[key] = [lat, (lon + 182.0) % 360.0 - 180.0]
    return result


def worker(root, mode, guard="off"):
    from contextlib import nullcontext
    from unittest.mock import patch
    import continued_cfo_trial
    if guard not in ("on", "off"):
        raise ValueError("Unknown calibration guard")
    flags = (*continued_cfo_trial.FLAGS, "withhold_empty_family_calibration")
    with patch.object(continued_cfo_trial, "FLAGS", flags) if guard == "on" else nullcontext():
        execute(root, mode)


def execute(root, mode):
    if mode == "portable":
        from portable_orbit_index_trial import publication_worker
        publication_worker(root)
    elif mode == "ordinary":
        from continued_cfo_trial import work
        work(root)
    else:
        raise ValueError("Unknown preparation mode")


def launch(root, guard="on", offer_kind="translated"):
    from portable_orbit_index_trial import FILE_ENV, PIN_ENV, local_launcher_tools
    local_launcher_tools()
    from aperture_trial import RELEASE, THREADS, write
    from empty_bootstrap import checked
    from full_short_physical import REGION_SHA, environment
    from historical_orbit_publication import BINDING_PIN, REFERENCE
    from short_raw_diagnostic import measure

    if root.parent != Path("/dev/shm") or root != root.resolve():
        raise ValueError("Expected a fresh direct tmpfs child")
    base = json.loads(checked(REFERENCE/"binding.json", BINDING_PIN))
    original_offer = json.loads(checked(Path(base["offer"]), REGION_SHA))
    checked(INDEX, INDEX_PIN.removeprefix("sha256:"))
    root.mkdir()
    offers = {"translated": translated(original_offer), "containing": original_offer}
    write(root/"offer.json", offers[offer_kind])
    write(root/"settings.json", dict(calibration_guard=guard, offer_kind=offer_kind))
    for mode in MODES:
        directory = root/mode
        directory.mkdir()
        (directory/"tmp").mkdir()
        write(directory/"binding.json", base | {"offer": str(root/"offer.json")})
        env = environment(directory)
        env.update(dict.fromkeys(THREADS, "1"))
        env.update(TMPDIR=str(directory/"tmp"), XDG_CACHE_HOME=str(directory/"tmp"))
        if mode == "portable":
            env.update({FILE_ENV: str(INDEX), PIN_ENV: INDEX_PIN,
                        "LEO_RESEARCH_ORBIT_PRODUCER_SHA256": BIND_PIN})
        python = RELEASE/"venv/bin/python"
        subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                       check=True, env=env, timeout=30)
        clock = measure([python, "-IB", __file__, "worker", directory, mode, guard], env, directory/"selective")
        write(directory/"clock.json", clock)
    if any(json.loads((root/mode/"clock.json").read_bytes())["exit_code"] for mode in MODES):
        raise RuntimeError("At least one saved process failed; inspect both clocks")
    score(root, runtime_ready=True)


def score(root, output="result.json", *, runtime_ready=False):
    from portable_orbit_index_trial import local_launcher_tools
    if not runtime_ready:
        local_launcher_tools()
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from historical_orbit_publication import BINDING_PIN, REFERENCE, REFERENCE_PIN, same_regional_path
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from regional_history_score import scientific, one
    from triage_bounds import REFERENCE as SURVEY, REFERENCE_SHA256, distance_km

    job = json.loads(checked(REFERENCE/"binding.json", BINDING_PIN))
    containing = json.loads(checked(REFERENCE/"result.json", REFERENCE_PIN))["science"]
    offer = read(root/"offer.json")
    original_offer = containing["receipt"]["region"]
    is_omitted = read(root/"settings.json").get("offer_kind", "translated") == "translated"
    if offer != (translated(original_offer) if is_omitted else original_offer):
        raise ValueError("Unexpected supplied offer")
    runs = {}
    for mode in MODES:
        directory = root/mode
        target = directory/"selective"
        data = read(target/"continued-cfo-worker.json")
        receipt = data["receipt"]
        clock = read(directory/"clock.json")
        term = json.loads(checked(one(target, "terminal.json"), receipt["terminal_sha256"][7:]))
        detail = FastStandardAnalysisStore(target).detail(receipt["run_id"])
        detector = sha256(one(target, "detections.json").read_bytes()).hexdigest()
        if (clock["exit_code"] or data["handoffs"] != 1 or data["waveform_calls"] or receipt["region"] != offer
                or detail["raw_authority"] != containing["raw_authority"]
                or detector != job["saved"]["native_sha256"][7:]):
            raise ValueError("Incorrect handoff, input, region or process outcome")
        full = receipt["decision"] == "complete"
        media = artifacts(target, receipt)
        # The published grid includes elapsed_seconds. scientific() separately
        # verifies every grid field except that clock, including every value.
        timed_grid_digest = media.pop("grid", None)
        runs[mode] = dict(clock=clock, timed_grid_digest=timed_grid_digest,
                          science=dict(terminal=term, terminal_sha256=receipt["terminal_sha256"],
                          decision=receipt["decision"], detector=detector, media=media,
                          products=scientific(target) if full else None))
    audit = read(root/"portable/orbits-indexed.json")
    transfer, = audit["transfers"]
    if (transfer["sha256"] != INDEX_PIN or transfer["loading"]["fallback"]
            or transfer["counts"]["sidecar_hit_bodies"] != 19):
        raise ValueError("Portable preparation was inactive or used a different source")
    survey = json.loads(checked(SURVEY, REFERENCE_SHA256))
    case, = (c for c in survey["cases"] if c["dataset_label"] == "DS30-0016")
    if not case["authority_eligible"] or not case["sealed_metadata_digests_verified"]:
        raise ValueError("Ineligible physical site reference")
    site = [case["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    distance = distance_km(site, offer["center"])
    if is_omitted and distance < 2*offer["width_km"]:
        raise ValueError("Insufficient distance to establish omission")
    if not is_omitted and distance > offer["width_km"]/2:
        raise ValueError("The original reference falls outside the inscribed central circle")
    traces = {}
    for mode, run in runs.items():
        actual = run["science"]
        run["false_fix"] = is_omitted and actual["decision"] == "complete"
        run["horizontal_error_km"] = {arm: distance_km(site, row["latlon"])
            for arm, row in actual["terminal"]["arms"].items() if row.get("latlon")}
        detail = traces[mode] = read(root/mode/"selective/joint-research-receipt.json")
        run["early_regional"] = detail["early_regional"]
        run["projector"] = detail["solve"]["geographic_projector"]
        run["catalogue_handoff"] = detail["solve"]["prepared_exterior"]
    if Path(output).name != output:
        raise ValueError("Expected a new result filename within the scored directory")
    write(root/output, dict(case="DS30-0016", original_binding=BINDING_PIN, index_sha256=INDEX_PIN,
          offer=offer, site_to_center_km=distance, containing_decision=containing["receipt"]["decision"],
          raw_authority=containing["raw_authority"], native_sha256=job["saved"]["native_sha256"],
          runs=runs, portable_audit=audit, offer_omits_reference=is_omitted,
          same_regional_evidence=same_regional_path(traces["portable"], traces["ordinary"]),
          same_science=runs["portable"]["science"] == runs["ordinary"]["science"],
          reference_sha256=REFERENCE_SHA256))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    action, target, *options = sys.argv[1:]
    {"worker": worker, "run": launch, "score": score}[action](Path(target), *options)
