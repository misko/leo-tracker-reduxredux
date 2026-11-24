"""Verify the saved confidence witness against the identical archived raw products."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import time_ns

from accepted_confidence_trial import CASE, STAGE, checked, sha, write
from sparse8_cfo_epoch_challenge import CAMPAIGN, PAIR, ordinary


ARMS = ("c0", "fitted_c")


def comparable_grid(grid):
    return {name: value for name, value in grid.items() if name != "elapsed_seconds"}


def readout(root, proof, output):
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from PIL import Image

    book = checked(proof, sha(proof))
    gate = json.loads((root/"gate.json").read_bytes())
    watch = json.loads((root/"watch-start.json").read_bytes())
    end = json.loads((root/"watch-end.json").read_bytes())
    run = root/"run"
    clock = json.loads((run/"clock.json").read_bytes())
    row = json.loads((run/"observed.json").read_bytes())
    witness = checked(run/"publication/exact-named-raw-witness.json", row["witness_sha256"])
    trace = checked(run/"trace.json", row["trace_sha256"])
    baseline = ordinary(STAGE)
    raw_case = CAMPAIGN/"cases"/CASE
    pair = checked(raw_case/"pair.json", PAIR)
    raw_root = raw_case/"successor"/f"attempt-{pair['generation']:06d}"
    raw = checked(raw_root/"result.json", pair["attempt_result_sha256"]["successor"])
    previous, current = (FastStandardAnalysisStore(path) for path in (raw_root/"publication", run/"publication"))
    original_id = raw["evidence"]["receipt"]["run_id"]
    receipt = row["receipt"]
    run_id = receipt["run_id"]
    terminal = checked(run/"publication/fast-scan-automatic-work"/run_id/"terminal.json",
                       receipt["terminal_sha256"])
    native, = (run/"publication").glob("fast-scan-automatic-work/*/detections.json")
    detail = current.detail(run_id)
    owners = witness["evidence"]["owner_rows"]
    owner_pins = {arm: owner_digest({oid: norad for oid, norad, _ in owners[arm]}) for arm in ARMS}
    grid, path = current.position_grid(run_id), current.position_path(run_id)
    images = {}
    for item in detail["artifacts"]:
        content = current.artifact(run_id, item["name"], item["sha256"])
        with Image.open(BytesIO(content)) as image:
            if image.format != "PNG" or "sha256:"+sha256(content).hexdigest() != item["sha256"]:
                raise ValueError("Expected the exact stored PNG bytes")
            images[item["name"]] = dict(size=list(image.size), sha256=item["sha256"],
                                         rgba_sha256=sha256(image.convert("RGBA").tobytes()).hexdigest())
    expected_figures = {row["name"]: {k: row[k] for k in ("size", "sha256", "rgba_sha256")}
                        for row in raw["figures"]}
    for png in expected_figures.values():
        png["rgba_sha256"] = png["rgba_sha256"].removeprefix("sha256:")
    checks = dict(
        single_saved_success=end["status"] == clock["exit"] == 0 and row["handoffs"] == 1
            and watch["ready_sha256"] == sha(proof),
        exact_detector=sha(native) == row["input"] == book["custody"]["native"],
        exact_terminal=receipt["terminal_sha256"] == raw["evidence"]["receipt"]["terminal_sha256"],
        exact_both_arms=terminal["arms"] == baseline["terminal"]["arms"] and set(terminal["arms"]) == set(ARMS),
        exact_owners=owners == baseline["witness"]["evidence"]["owner_rows"] and owner_pins == raw["evidence"]["owners"],
        exact_grid=grid["complete"] and grid["evaluated_points"] == 179
            and comparable_grid(grid) == comparable_grid(previous.position_grid(original_id)),
        exact_path=path == previous.position_path(original_id),
        exact_eight_pngs=len(images) == 8 and images == expected_figures,
        exact_published_source=row["source_sha256"] == baseline["witness"]["source_sha256"],
    )
    event_path = CAMPAIGN/gate["event"]
    if "sha256:"+sha(event_path) != gate["event_sha256"]:
        raise ValueError("The recorded official deferral changed")
    subsequent = []
    for path in sorted(event_path.parent.glob("*.json")):
        stamp = int(path.name.split("-",1)[0])
        if gate["unix_ns"] < stamp <= clock["terminated_unix_ns"]+35_000_000_000:
            event = json.loads(path.read_bytes())
            subsequent.append(dict(stamp=stamp, state=event["state"], sha256=sha(path)))
    post = dict(observed_through_ns=time_ns(), events=subsequent)
    write(output, dict(proof=book, preflight_sha256=sha(proof), clock=clock, gate=gate,
                       post_event=post, comparisons=checks, observed=row, trace=trace, original=baseline["timed_saved_clock"]))
    if not all(checks.values()):
        raise ValueError(f"Saved ordinary archive parity failed: {checks}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "proof", "output"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    readout(args.root, args.proof, args.output)
