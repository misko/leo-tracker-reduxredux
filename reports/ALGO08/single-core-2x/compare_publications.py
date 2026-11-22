"""Describe scientific changes in an approximate raw-to-web development pair."""
import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification.paired_publication import evidence
from tools.pipeline_eval.scoring import ARMS, distance_km
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
    terminal = json.loads((workspace / "terminal.json").read_bytes())
    native_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(native_path.read_bytes())
    if (canonical_digest(native) != terminal["native_sha256"]
            or native["source"]["raw_recording_authority_digest"] != run["raw_authority"]):
        raise ValueError("Detection inventory does not match the sealed raw input and terminal")
    store = FastStandardAnalysisStore(root)
    figures = {item["name"]: image_receipt(store.artifact(run_id, item["name"], item["sha256"]))
               for item in run["artifacts"]}
    probes = native["source"]["probes"]
    result = dict(
        probe_rows=len(probes), figures=figures, decision=receipt["decision"], counts=receipt["counts"],
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


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pair", type=Path)
    print(json.dumps(compare(cli.parse_args().pair), indent=2, allow_nan=False))
