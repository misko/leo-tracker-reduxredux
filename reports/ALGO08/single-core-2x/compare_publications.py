"""Describe scientific changes in an approximate raw-to-web development pair."""
import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from math import isfinite
from pathlib import Path

from PIL import Image

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification.paired_publication import evidence
from tools.pipeline_eval.scoring import ARMS, coordinate, distance_km
from .audit_shared_publication import _png_scaffold


def selected_factors(probes):
    # Preserve identity across arms even if an earlier visit lost a selection.
    return Counter(canonical_digest([row["visit_index"], row["receiver_id"], row["channel"],
                                     row["actual_rf_hz"], row["valid_start_counter"], candidate])
                   for row in probes for candidate in row["candidates"])


def image_receipt(data):
    _png_scaffold(data)
    with Image.open(BytesIO(data)) as image:
        if image.format != "PNG" or image.n_frames != 1 or data[24] != 8:
            raise ValueError("Expected a single 8-bit publication PNG")
        return dict(size=list(image.size), rgba_sha256=sha256(image.convert("RGBA").tobytes()).hexdigest())


def verified(root, run):
    receipt = run["receipt"]
    restored = evidence(root, receipt, 0, read_only=True)
    for key in ("receipt", "raw_authority", "arms", "owners", "reason", "artifacts", "scientific_digests"):
        if restored[key] != run[key]:
            raise ValueError(f"Stored pair disagrees with published {key}")
    run_id = receipt["run_id"]
    workspace = FastScanStore(root).automatic_workspace(run_id, create=False)
    terminal_path = workspace / "terminal.json"
    terminal = json.loads(terminal_path.read_bytes())
    native_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(native_path.read_bytes())
    detector_to_terminal = (terminal_path.stat().st_mtime_ns - native_path.stat().st_mtime_ns) / 1e9
    terminal_elapsed = run["terminal_file_s"]
    if not isfinite(terminal_elapsed) or not 0 <= detector_to_terminal <= terminal_elapsed <= run["elapsed_s"]:
        raise ValueError("Published file timestamps disagree with the launch clock")
    source = native["source"]
    if (canonical_digest(native) != terminal["native_sha256"]
            or source["raw_recording_authority_digest"] != run["raw_authority"]):
        raise ValueError("Detection inventory does not match the sealed raw input and terminal")
    store = FastStandardAnalysisStore(root)
    publication = store.detail(run_id)
    session = receipt["session_id"]
    if (terminal["session_id"] != session or source["session_id"] != session
            or publication["session_id"] != session or publication["run_id"] != run_id
            or publication["input_sha256"] != terminal["native_sha256"]):
        raise ValueError("Session or detector digest differs between the terminal and publication")
    fixed = receipt["decision"] == "complete"
    if (terminal["decision"] != ("ok" if fixed else "withheld") or set(terminal["arms"]) != set(ARMS)
            or any((coordinate(terminal["arms"][arm]["latlon"]) is not None) != fixed for arm in ARMS)):
        raise ValueError("The terminal must supply both calibration arms for its decision")
    if fixed:
        if any(publication["arms"][arm]["endpoint_latlon"] != terminal["arms"][arm]["latlon"] for arm in ARMS):
            raise ValueError("Published endpoints differ from the bound terminal")
    elif publication["reason"] != terminal["reason"]:
        raise ValueError("Published withholding reason differs from the bound terminal")
    figures = {item["name"]: image_receipt(store.artifact(run_id, item["name"], item["sha256"]))
               for item in run["artifacts"]}
    probes = source["probes"]
    result = dict(
        probe_rows=len(probes), figures=figures, decision=receipt["decision"], reason=run["reason"],
        detector_sha256=native["provenance"]["detector_sha256"], counts=receipt["counts"],
        arms=run["arms"], owners=run["owners"], scientific_digests=run["scientific_digests"],
        elapsed_s=run["elapsed_s"], cpu_s=run["cpu_s"],
    )
    return selected_factors(probes), result


def compare(pair):
    data = json.loads(pair.read_bytes())
    if "failure" in data:
        raise ValueError("Pair failed before both publications could be verified")
    baseline, candidate = (data["runs"][k] for k in ("baseline", "candidate"))
    if (baseline["raw_authority"] != candidate["raw_authority"] or
            any(baseline["receipt"][k] != candidate["receipt"][k] for k in ("region", "session_id", "window_count"))):
        raise ValueError("Compared publications use different raw inputs or offers")
    before, control = verified(pair.parent / "baseline", baseline)
    after, changed = verified(pair.parent / "candidate", candidate)
    names = set(control["figures"]) | set(changed["figures"])
    return dict(session=baseline["receipt"]["session_id"], raw_authority=baseline["raw_authority"],
                region=baseline["receipt"]["region"], baseline=control, candidate=changed,
                selected_common=(before & after).total(), selected_lost=(before - after).total(),
                selected_added=(after - before).total(),
                same_rendered_figures={key: control["figures"].get(key) == changed["figures"].get(key)
                                       for key in sorted(names)},
                displacement_km={k: distance_km(control["arms"][k]["latlon"], changed["arms"][k]["latlon"])
                                 for k in ARMS})


def score_public_waveform(pair, scoring_key):
    from . import selected_changes

    result = compare(pair)
    recording = Path(json.loads(pair.read_bytes())["recording"]).name
    answers = json.loads(scoring_key.read_bytes())["answers"]
    sites = {tuple(row["truth"]) for row in answers.values() if row["recording"] == recording}
    if len(sites) != 1:
        raise ValueError("Expected one public reference for the measured recording")
    site, = sites
    result.update(selected_fields=selected_changes.compare(pair, summary=True), reference_latlon=list(site),
                  error_km={method: {arm: distance_km(result[method]["arms"][arm]["latlon"], site)
                                     for arm in ARMS} for method in ("baseline", "candidate")})
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pair", type=Path)
    cli.add_argument("--public-scoring-key", type=Path, help="Score an already published simulation by recording")
    args = cli.parse_args()
    result = score_public_waveform(args.pair, args.public_scoring_key) if args.public_scoring_key else compare(args.pair)
    print(json.dumps(result, indent=2, allow_nan=False))
