"""Run the pinned combined successor on the two original South saved offers."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from nomination_handoff_south import CONTROL, CONTROL_SEAL, FONT_SHA, MIRROR, MIRROR_REQUEST_SHA, digest, read, staged


ORDER = ("containing", "near-omitted")
ARMS = ("c0", "fitted_c")
CONTAINING_REQUEST = "975c8b3bf5c6c30a358eb974772cd00e917a9e98fc998bfe9a8fcfad22d48f91"
PROTOCOL = HERE/"combined-successor-south-protocol.md"
TIMED_ADAPTER = "10fdc6861812e4a7a8003cac26056f5d85ca9f76374bff69fbd19a69a0945542"


def own_sources():
    names = (Path(__file__), PROTOCOL, HERE/"nomination_handoff_south.py", HERE/"ds30_0163_combined.py")
    return {path.name: digest(path) for path in names}


def deny_waveform(recording):
    def guard(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(recording) or path.name.endswith((".ci16", ".ci16.zst")):
                raise ValueError("A saved request may not open waveform or original recording files")
    return guard


def mirror_requests(inside, outside):
    shape = {"offer_file", "offer_sha256", "case"}
    if ({key: value for key, value in inside.items() if key not in shape}
            != {key: value for key, value in outside.items() if key not in shape}
            or inside["offer_sha256"] == outside["offer_sha256"]):
        raise ValueError("These two offers must change only the supplied region on the same saved request")


def controls():
    from empty_bootstrap import checked
    from held_adaptive_0160_score import verified
    from isolated_salvage_south import NATIVE_SHA, ORIGINAL, PAIR_SHA
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from nomination_handoff_south import checked_control, enrolled
    from tools.pipeline_eval.qualification import paired_publication as pairs

    near, inventory, original_packets, previous = enrolled()
    origin = json.loads(checked(staged(MIRROR/"containing-request.json"), CONTAINING_REQUEST))
    inside = near | {key: origin[key] for key in ("offer_file", "offer_sha256")} | {"case": "South containing simulation"}
    if (any(inside[key] != value for key, value in origin.items() if key != "local_archive")
            or origin["local_archive"] != inside["original_archive"]
            or tuple(near[key] for key in ("issued", "admitted")) != (1200, 1200)):
        raise ValueError("The frozen containing request must preserve the complete original signed scope")
    mirror_requests(inside, near)
    containing, omitted = (json.loads(checked(staged(Path(req["offer_file"])), req["offer_sha256"])) for req in (inside, near))
    if containing != previous["containing"]["offer"] or omitted != previous["near-omitted"]["offer"]:
        raise ValueError("The requested regions disagree with the sealed original controls")
    pair = json.loads(checked(staged(ORIGINAL/"pair.json"), PAIR_SHA))
    specification = pairs.V3_IDENTITY["frozen_specification"]
    config = checked(staged(ORIGINAL/"candidate-config.json"), specification[7:])
    stock = pair["runs"]["candidate"]
    installed_root = ORIGINAL/"candidate"
    receipt = stock["receipt"]
    science = pairs.evidence(installed_root, receipt, 0, read_only=True)
    if (pair["candidate_specification_digest"] != specification or sha256(config).hexdigest() != specification[7:]
            or sha256(Path(inside["native_file"]).read_bytes()).hexdigest() != NATIVE_SHA
            or any(science[key] != stock[key] for key in ("raw_authority", "arms", "owners", "artifacts", "scientific_digests"))):
        raise ValueError("The original containing publication no longer matches the named v3 specification and products")
    store = FastStandardAnalysisStore(installed_root)
    terminal = read(installed_root/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json")
    first = dict(terminal=terminal, science=science, products=artifacts(installed_root, receipt),
                 sample=store.position_grid(receipt["run_id"]), path=store.position_path(receipt["run_id"]), rows={},
                 clock={key: stock[key] for key in ("elapsed_s", "cpu_s", "terminal_file_s")},
                 timing_scope="historical original raw through exit")
    checked_control(CONTROL, near)
    clock = read(CONTROL/"installed/clock.json")
    second = verified(CONTROL/"installed/candidate", clock, "worker.json", near) | {"timing_scope": "saved worker through exit"}
    if any(second["terminal"][key] != first["terminal"][key] for key in ("session_id", "native_sha256")) or terminal["native_sha256"] != "sha256:"+NATIVE_SHA:
        raise ValueError("Both installed controls must verify the exact same signed detector packet")
    if (any(first["sample"]["binding"][key] != first["path"]["binding"][key]
            for key in ("owner_sha256", "position_png_sha256", "terminal_sha256"))
            or canonical_digest(first["terminal"]) != receipt["terminal_sha256"]):
        raise ValueError("The original containing publication binding changed")
    return dict(zip(ORDER, (inside, near), strict=True)), inventory, original_packets, dict(zip(ORDER, (first, second), strict=True))


def run(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from combined_successor_0289 import admitted_libraries
    from dense_geographic_trial import host
    from ds30_0163_combined import pinned_sources
    from empty_bootstrap import RELEASE, checked, clock, now
    from exact_named_route import checked_catalogue
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from north_direct_multichunk import checked_lease
    from short_raw_diagnostic import measure

    started = now()
    checked_lease()
    machine = host()
    if root.exists() or staged(root.parent) != Path("/tmp") or shutil.disk_usage(root.parent).free < 2**29:
        raise ValueError("Use a fresh private tmpfs output with adequate headroom")
    sources, libraries = pinned_sources(), admitted_libraries()
    requests, inventory, packets, installed = controls()
    sys.addaudithook(deny_waveform(Path(requests["containing"]["recording"])))
    full = requests["containing"]
    _, refs = checked_catalogue({"archive": full["local_archive"]["root"]}, full, TleArchiveReader, canonical_digest, resident=staged)
    for ref in refs:
        checked(staged(ref.path), ref.sha256.removeprefix("sha256:"))
    root.mkdir(mode=0o700)
    for name in ("fonts", "tmp"):
        (root/name).mkdir()
    font = "fontlist-v3.11.0.json"
    (root/"fonts"/font).write_bytes(checked(staged(MIRROR/"fonts"/font), FONT_SHA))
    for mode in ORDER:
        work = root/mode
        work.mkdir()
        (work/"routed").mkdir()
        request = requests[mode]
        req_path = work/"request.json"
        write(req_path, request)
        archive = request["local_archive"]["root"]
        bound = dict(case=request["case"], stage=str(work), archive=archive, request=str(req_path), inventory=str(inventory),
                     issued=request["issued"], admitted=request["admitted"], portable=None,
                     sources=sources, packets=packets | {str(req_path): digest(req_path), request["offer_file"]: request["offer_sha256"]})
        job = work/"job.json"
        write(job, dict(binding=bound, original_archive=request["original_archive"]))
        write(work/"routed/binding.json", {"input": bound})
        cmd = ["/usr/bin/timeout", "--kill-after=2s", "45s", str(RELEASE/"venv/bin/python"), "-IB",
               str(Path(__file__).resolve()), "worker", str(work)]
        write(work/"admission.json", dict(command=cmd, job_sha256=digest(job), sources=sources, libraries=libraries,
              original_control=digest(CONTROL/"prediction-seal.json") if mode != "containing" else installed[mode]["science"]["receipt"]["terminal_sha256"],
              verified_archive_bodies=len(refs), verified_archive_bytes=sum(ref.byte_size for ref in refs)))
    write(root/"admission.json", dict(science_commit="1245957b4", mode_order=ORDER, sources=own_sources(), machine=machine,
                                     setup=clock(started), no_waveform=True, recorded_installed_only=True))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    for mode in ORDER:
        work = root/mode
        log = measure(read(work/"admission.json")["command"], env, work/"routed/candidate")
        write(work/"routed/clock.json", log)
        if log["exit_code"]:
            break
    write(root/"prediction-seal.json", output_seal(root))


def worker(root):
    import combined_successor_0289 as combined
    from history_risk_weak_physical import deny_original
    from nomination_handoff_south import staged_saved_ports

    sys.addaudithook(deny_original)
    sys.addaudithook(deny_waveform(Path(read(root/"request.json")["recording"])))
    if "leo" in sys.modules or read(root.parent/"admission.json")["sources"] != own_sources():
        raise ValueError("Scientific imports or adapter pins diverged before the installed bootstrap")
    with staged_saved_ports(), patch.multiple(combined, STAGED=root, JOB_SHA=read(root/"admission.json")["job_sha256"]):
        combined.worker(root)


def figures_and_grid(run, offer):
    if run["terminal"]["region"] != offer or set(run["terminal"]["arms"]) != set(ARMS):
        raise ValueError("The published region and calibration arms must be the original ones")
    published = run["science"]["receipt"]["decision"]
    numerical = run["terminal"]["decision"]
    if not (published == "withheld" == numerical or published == "complete" and numerical in ("ok", "complete")):
        raise ValueError("The numerical terminal and public decision disagree")
    figures = run["products"]["images"]
    sample, path = run["sample"], run["path"]
    if published == "withheld":
        if figures or sample is not None or path is not None or run["rows"] or any(
            arm["latlon"] is not None or arm.get("rf_rms_hz") is not None for arm in run["terminal"]["arms"].values()):
            raise ValueError("Withholding requires two null arms and zero position products")
        return None
    if (len(figures) != 8 or sample is None or path is None or not sample["complete"]
            or not sample["matched_c_grid"] or sample["evaluated_points"] != len(sample["points"]) or not path["stages"]
            or any(item["binding"]["position_png_sha256"] != figures["position"]["sha256"] for item in (sample, path))):
        raise ValueError("A fix requires the entire verified common grid, path and eight official images")
    return sample["evaluated_points"]


def score(root, output):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from empty_bootstrap import checked
    from held_adaptive_0160_score import verified
    from isolated_salvage_south import ORIGINAL, TRUTH_SHA
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from nomination_handoff_south_score import decision
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    book, seal = read(root/"admission.json"), root/"prediction-seal.json"
    timed_sources = own_sources() | {Path(__file__).name: TIMED_ADAPTER}
    if read(seal) != output_seal(root) or book["sources"] not in (own_sources(), timed_sources):
        raise ValueError("Only the sealed, unchanged scientific runs can be scored")
    requests, _, _, installed = controls()
    clocks = {mode: read(root/mode/"routed/clock.json") for mode in ORDER if (root/mode/"routed/clock.json").is_file()}
    if set(clocks) != set(ORDER) or any(row["exit_code"] for row in clocks.values()):
        write(output, dict(qualified=False, clocks=clocks, admission=book, prediction_sha256=digest(seal)))
        return
    trial = {mode: verified(root/mode/"routed/candidate", clocks[mode], "worker.json", requests[mode]) for mode in ORDER}
    scoring = json.loads(checked(HERE.parent/"regional-release/scoring-key.json", TRUTH_SHA))
    truth, = {tuple(row["truth"]) for row in scoring["answers"].values()
              if row["recording"] == Path(requests["containing"]["recording"]).name}
    result = {}
    for mode in ORDER:
        folder = root/mode/"routed"
        offer = read(Path(requests[mode]["offer_file"]))
        signed_distance = face_clearance_km(offer, truth)
        if abs(signed_distance - (.1 if mode == "containing" else -.1)) > .001:
            raise ValueError("The enrolled simulated position and known 100 m offers differ")
        reports = {}
        for name, run, location in (("candidate", trial[mode], folder/"candidate"),
                                     ("installed", installed[mode], ORIGINAL/"candidate" if mode == "containing" else CONTROL/"installed/candidate")):
            points = figures_and_grid(run, offer)
            terminal, rows = run["terminal"], run["rows"]
            rid = run["science"]["receipt"]["run_id"]
            detail = FastStandardAnalysisStore(location).detail(rid)
            arms = {}
            for arm, value in terminal["arms"].items():
                coordinates = value["latlon"]
                if rows and canonical_digest({oid: norad for oid, norad, _ in rows[arm]}) != run["science"]["owners"][arm]:
                    raise ValueError("Owner rows changed from the official published digest")
                arms[arm] = dict(latlon=coordinates, horizontal_error_m=1000*distance_km(truth, coordinates) if coordinates else None,
                    east_west_clearance_m=1000*face_clearance_km(offer, coordinates) if coordinates else None,
                    conditional_rf_rms_hz=value.get("rf_rms_hz"), all_owned_rf_rms_hz=detail["arms"].get(arm, {}).get("residual_rms_hz"),
                    owners=detail["arms"].get(arm, {}).get("associated_points", 0))
            timing = run["clock"] | {k: run["trace"][k] for k in ("publication_elapsed_s", "publication_cpu_s", "solve")} if "trace" in run else run["clock"]
            reports[name] = dict(decision=decision(run["science"]["receipt"]["decision"], signed_distance > 0), arms=arms, timing=timing,
                timing_scope=run.get("timing_scope", "saved worker through exit"), owners=run["science"]["owners"],
                numerical=run["science"]["scientific_digests"], figures=run["products"]["images"], grid_points=points)
        old, new = installed[mode], trial[mode]
        result[mode] = dict(offer=offer, actual_site_clearance_m=1000*signed_distance, reports=reports,
              comparative_owners={arm: owner_delta(old["rows"].get(arm, []), new["rows"].get(arm, [])) for arm in ARMS} if old["rows"] else None,
              route=read(folder/"risk-route.json"), native_grid=read(folder/"combined-grid.json"),
              live_orbit=read(folder/"live-corner.json"), render=read(folder/"render-usage.json"))
    write(output, dict(qualified=True, case="South simulation", results=result, admission=book,
          correct_geography={mode: value["reports"]["candidate"]["decision"] in ("fix", "withheld") for mode, value in result.items()},
          prediction_sha256=digest(seal), control_seal=CONTROL_SEAL, scoring_key_sha256=TRUTH_SHA,
          new_candidate_children=2, new_installed_children=0, native_sha256=requests["containing"]["native_sha256"],
          source_archive=requests["containing"]["local_archive"], waveform_reads=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.action == "score":
        score(args.root, args.output or args.root/"result.json")
    else:
        {"run": run, "worker": worker}[args.action](args.root)
