"""Compare new wide-GLRT winners with the capture detector on every recorded probe."""

import argparse
import csv
import gzip
import io
import json
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from . import factor_cross, shared_winner_cross, support_cross
from .full_v5_check import BULK, _load_case, _sha

FRONTIER = ROOT / "reports/2026_11_19_receiver_screening/acquisition-frontier"
REPORT = FRONTIER / "detector-agreement"
PARENT = FRONTIER / "whole-replay"
PARENT_SEAL = "e46441f38312a61a4febff38c15d06a2a4bb53a3037ddcc84c1bc95f50d53671"
CASES = ("DS26-0168", "DS29-0604")
LABELS = ("capture_winner", "other_capture_candidate", "different_family", "capture_negative")


def best(candidates):
    index = factor_cross.winner(candidates)
    return candidates[index] if index is not None else None


def match(left, right, frame, absolute=False):
    if left is None or right is None:
        return False
    lt, lf = shared_winner_cross.physical(left)
    rt, rf = shared_winner_cross.physical(right)
    frequency = lf - rf if absolute else factor_cross.wrapped(lf - rf, factor_cross.ALIAS_HZ)
    return abs(factor_cross.wrapped(lt - rt, frame)) <= 2 and abs(frequency) <= 1000


def label(candidate, reference, frame):
    if candidate is None:
        return "no_winner"
    winner = best(reference)
    if winner is None:
        return "capture_negative"
    if match(candidate, winner, frame):
        return "capture_winner"
    if any(c[factor_cross.GATE] and match(candidate, c, frame) for c in reference):
        return "other_capture_candidate"
    return "different_family"


def classify(left, right, reference, frame):
    if left is None:
        transition = "gained" if right is not None else "both_negative"
    elif right is None:
        transition = "lost"
    elif left == right:
        transition = "identical_winner"
    else:
        transition = "same_family" if match(left, right, frame) else "switched_family"
    capture = best(reference)
    return dict(
        transition=transition,
        capture_positive=capture is not None,
        stock=label(left, reference, frame),
        hinted=label(right, reference, frame),
        stock_absolute=match(left, capture, frame, absolute=True),
        hinted_absolute=match(right, capture, frame, absolute=True),
    )


def summary(rows):
    output = {}
    for case in (*CASES, "pooled"):
        cohort = [r for r in rows if case == "pooled" or r["id"] == case]
        tally = Counter(r["transition"] for r in cohort)
        gained = [r for r in cohort if r["transition"] == "gained"]
        lost = [r for r in cohort if r["transition"] == "lost"]
        changed = [r for r in cohort if r["transition"] == "switched_family"]
        output[case] = dict(
            probes=len(cohort),
            capture_positive=sum(r["capture_positive"] for r in cohort),
            transitions=dict(tally),
            gains_by_hint_label=dict(Counter(r["hinted"] for r in gained)),
            losses_by_stock_label=dict(Counter(r["stock"] for r in lost)),
            switched_toward_capture=sum(
                r["stock"] != "capture_winner" and r["hinted"] == "capture_winner" for r in changed
            ),
            switched_away_from_capture=sum(
                r["stock"] == "capture_winner" and r["hinted"] != "capture_winner" for r in changed
            ),
            winner_agreement={
                arm: sum(r[arm] == "capture_winner" for r in cohort) for arm in ("stock", "hinted")
            },
            absolute_winner_agreement={
                arm: sum(r[f"{arm}_absolute"] for r in cohort) for arm in ("stock", "hinted")
            },
        )
    return output


def evaluate(runs, out):
    lock = whole_iq.read(whole_iq.checked(PARENT / "prediction-lock.json", PARENT_SEAL))
    plan = whole_iq.read(
        whole_iq.checked(PARENT / "source-lock.json", lock["files"]["source-lock.json"])
    )
    preds = whole_iq.checked(PARENT / "positions.jsonl.gz", lock["files"]["positions.jsonl.gz"])
    records = [json.loads(b) for b in gzip.decompress(preds.read_bytes()).splitlines()]
    if len(records) != 4 or set(plan["cases"]) != set(CASES):
        raise ValueError("source is not the measured two-recording whole-IQ pair")
    rows, inputs = [], {}
    for case in CASES:
        item = plan["cases"][case]
        reference = whole_iq.checked(
            BULK / _load_case(case)["native"]["path"], item["capture_native_sha256"]
        )
        capture = whole_iq.read(reference)
        frame = capture["source"]["sample_rate_hz"] / factor_cross.FRAME_HZ
        sources = {}
        for role in ("control", "candidate"):
            native = [
                r for r in records if r["id"] == case and r["method"] == f"frontier-whole-iq_{role}"
            ]
            if len(native) != 1:
                raise ValueError("missing or duplicate sealed native result")
            path = whole_iq.checked(
                runs / case / role / "recording/native.json", native[0]["native_sha256"]
            )
            doc = whole_iq.read(path)
            support_cross.join(doc, capture)
            sources[role] = doc["source"]["probes"]
            inputs[f"{case}/{role}"] = native[0]["native_sha256"]
        inputs[f"{case}/capture"] = item["capture_native_sha256"]
        for left, right, ref in zip(
            sources["control"], sources["candidate"], capture["source"]["probes"], strict=True
        ):
            record = {k: ref[k] for k in (*support_cross.IDENTITY_FIELDS, "channel", "edge")}
            rows.append(
                dict(
                    id=case,
                    **record,
                    **classify(
                        best(left["candidates"]),
                        best(right["candidates"]),
                        ref["candidates"],
                        frame,
                    ),
                )
            )
    buffer = io.StringIO(newline="")
    table = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    table.writeheader()
    table.writerows(rows)
    write(out / "probes.csv.gz", gzip.compress(buffer.getvalue().encode(), mtime=0))
    save_json(out / "summary.json", summary(rows))
    save_json(
        out / "result-lock.json",
        dict(
            parent_sha256=PARENT_SEAL,
            input_sha256=inputs,
            source_sha256=_sha(Path(__file__)),
            files={
                name: _sha(out / name) for name in ("PROTOCOL.md", "probes.csv.gz", "summary.json")
            },
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--runs", type=Path, required=True)
    cli.add_argument("--out", type=local_output, default=REPORT)
    args = cli.parse_args()
    evaluate(args.runs, args.out)
