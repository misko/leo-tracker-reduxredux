"""Verify one paid repaired DS30-0316 portable publication against its original control."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
PREVIOUS = Path("/dev/shm/leo-v3-portable-0316-result01")
REFERENCE_SHA = "f1ba522a68cc28a4ca9c2ef2bc5e1283a55332804d1b72a9df9f9ede7f48ab72"
ARTIFACT_SEAL_SHA = "c80b4d306d88253472b943b748090175a383d7de733543afd8574c5b9f6bdca8"
PIN = "sha256:e538485b73528eab7e93f11eb37e7b422273ab063b649edb77dae91a9b2f61f7"
TIMERS = {"cpu_s", "elapsed_s", "cpu_ns", "elapsed_ns", "elapsed_seconds"}


def without_timers(data):
    if isinstance(data, dict):
        return {key: without_timers(value) for key, value in data.items() if key not in TIMERS}
    if isinstance(data, list):
        return [without_timers(row) for row in data]
    return data


def regional_evidence(receipt):
    early, = receipt["early_regional"]
    result = early["result"]
    if ("diagnostic_error" in result or result.get("probes_evaluated") != 24
            or result["complete"] or result["would_withhold"]
            or result["stop"] != "eligible_exterior_separation"
            or len(result["snapshots"]) != 9
            or receipt["solve"]["geographic_projector"] != dict(consumed=24, block_positions=24, block_calls=6,
                                                                scalar_positions=0, fallbacks=0)
            or receipt["solve"]["prepared_exterior"] != dict(prepared_catalogues=1, catalogue_handoff=1)):
        raise ValueError("The original causal regional diagnostic did not run successfully")
    return without_timers(early)


def admitted():
    from empty_bootstrap import checked
    from portable_orbit_0316 import ARTIFACT

    earlier = json.loads(checked(PREVIOUS/"verified.json", REFERENCE_SHA))
    seal = json.loads(checked(PREVIOUS/"artifact-seal.json", ARTIFACT_SEAL_SHA))
    artifact = PREVIOUS/ARTIFACT
    if seal["index_sha256"] != PIN or earlier["producer"]["artifact"]["sha256"] != PIN:
        raise ValueError("Expected the separately sealed earlier DS30-0306 artifact")
    return earlier, artifact


def compare(root, output):
    from aperture_trial import read, write
    from joint_publication import artifacts
    from portable_orbit_0316 import TARGET, TARGET_SEAL_SHA
    from empty_bootstrap import checked
    from regional_history_score import scientific

    earlier, artifact = admitted()
    checked(artifact, PIN.removeprefix("sha256:"))
    candidate, ordinary, defective = root/"portable", PREVIOUS/"ordinary", PREVIOUS/"portable"
    clocks = read(root/"portable.clock.json")
    if clocks["exit_code"]:
        raise ValueError("The corrected portable child did not exit successfully")
    control, broken, corrected = [read(folder/"joint-research-receipt.json") for folder in (ordinary, defective, candidate)]
    original_defect, = broken["early_regional"]
    if "every item must be a Satrec" not in original_defect["result"].get("diagnostic_error", ""):
        raise ValueError("The previous portable run does not document the known Satrec defect")
    if regional_evidence(corrected) != regional_evidence(control):
        raise ValueError("Corrected regional diagnostics differ from original complete computation")
    seal = json.loads(checked(TARGET/"prediction-seal.json", TARGET_SEAL_SHA))
    checked(TARGET/"candidate/joint-research-receipt.json", seal["candidate/joint-research-receipt.json"])
    if regional_evidence(corrected) != regional_evidence(read(TARGET/"candidate/joint-research-receipt.json")):
        raise ValueError("The corrected regional diagnostics do not reproduce the archived original recipe")
    observed = read(root/"portable-preparation.json")
    expected = earlier["runs"]["ordinary"]
    counts, attempt = observed["index_counts"], observed["attempts"][0]
    candidate_worker = read(candidate/"saved-0316-worker.json")
    final_fit = read(candidate/"final-fit-options.json")
    result = scientific(candidate)
    media = artifacts(candidate, candidate_worker["receipt"])
    previous_media = artifacts(ordinary, read(ordinary/"saved-0316-worker.json")["receipt"])
    if (observed["fingerprint"] != expected["active"]["fingerprint"]
            or counts["sidecar_hit_bodies"] != 37 or counts["sidecar_hit_rows"] != 413884
            or counts["cold_bodies"] != 3 or counts["invalid_bodies"]
            or observed["loading"]["fallback"] or observed["index_sha256"] != PIN
            or attempt["fallback"] or attempt["port"] != "regional"
            or observed["verified_original_reads"]["calls"] != 130 or observed["strict_parse"]["calls"] != 40
            or candidate_worker["receipt"]["tle_records"] != expected["native_record_parser"]
            or not candidate_worker["no_waveform"] or candidate_worker["handoffs"] != 1
            or not final_fit["named_survivor_finish"]["paid_final_fit"]
            or media["images"] != previous_media["images"] or media["path"] != previous_media["path"]
            or result != earlier["scientific"]):
        raise ValueError("The repaired candidate changed another original validation, fallback or output")
    write(output, dict(historical=earlier["historical_named_and_research"], geography=earlier["historical_geographic"],
        first_use_producer=earlier["producer_process"], artifact_sha256=PIN, scientific=result,
        defect=dict(through_exit=earlier["runs"]["portable"]["process"], early_regional=original_defect),
        ordinary=dict(through_exit=expected["process"], preparation=expected["active"],
                      solve=expected["solve"], early_regional=control["early_regional"]),
        portable=dict(through_exit=clocks, preparation=observed, solve=corrected["solve"],
                      publication={key: corrected[key] for key in ("publication_cpu_s", "publication_elapsed_s")},
                      early_regional=corrected["early_regional"]),
        native_validations=candidate_worker["receipt"]["tle_records"], no_waveform=True))


def launch(root):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import RELEASE, write
    from full_short_physical import environment
    from portable_orbit_0316 import TARGET
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Require fresh output in tmpfs")
    admitted()
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root/name).mkdir()
    for font in (TARGET/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/font.name).write_bytes(font.read_bytes())
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    command = ["/usr/bin/timeout", "--kill-after=2s", "60s", RELEASE/"venv/bin/python", "-IB",
               __file__, "worker", root]
    clock = measure(command, env, root/"portable")
    write(root/"portable.clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    compare(root, root/"result.json")


def worker(root):
    from functools import partial
    from portable_orbit_0316 import work
    from portable_orbit_compatibility import producer_versions

    earlier, artifact = admitted()
    compatibility = partial(producer_versions, earlier["producer"]["compatibility"])
    work(root, "portable", PIN, artifact_path=artifact, compatibility_check=compatibility)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "compare"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "compare":
        from empty_bootstrap import load_runtime

        load_runtime()
        compare(args.root, args.output or args.root/"result.json")
    else:
        {"launch": launch, "worker": worker}[args.action](args.root)
