"""Compare fixed-coordinate late-symbol evidence with the archived capture detector."""

import argparse
import csv
import gzip
import json
from hashlib import sha256
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import differential_agreement as agreement
from . import support_cross, verified_rescue
from .frontier_whole_replay_results import fingerprint
from .full_v5_check import BULK, FRAME_HZ, _load_case, _sha
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file

REPORT = verified_rescue.REPORT
LABELS = ("capture_winner", "other_capture_candidate", "different_family", "capture_negative")


def row_counts(rows):
    found = [r for r in rows if r["label"] in LABELS[:2]]
    other = [r for r in rows if r["label"] in LABELS[2:]]
    if len(found) + len(other) != len(rows):
        raise ValueError("unknown original capture classification")
    return dict(
        proposed=len(rows),
        verified=sum(r["passed"] for r in rows),
        original_matched=len(found),
        original_matched_verified=sum(r["passed"] for r in found),
        other=len(other),
        other_verified=sum(r["passed"] for r in other),
    )


def audit():
    locks = whole_iq.read(REPORT / "prediction-lock.json")["files"]
    measures = verified_rescue.lines(
        whole_iq.checked(REPORT / "probes.jsonl.gz", locks["probes.jsonl.gz"])
    )
    timings = verified_rescue.lines(
        whole_iq.checked(
            REPORT / "verification-costs.jsonl.gz", locks["verification-costs.jsonl.gz"]
        )
    )
    sources = whole_iq.read(whole_iq.checked(REPORT / "input-lock.json", locks["input-lock.json"]))
    capture_hashes = {}
    classified = []
    counters = []
    for ident in verified_rescue.CASES:
        case = _load_case(ident)
        reference = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
        capture = whole_iq.read(reference)
        parent = (
            verified_rescue.FOUR.parent / "whole-fftw"
            if ident in verified_rescue.CASES[:2]
            else verified_rescue.FOUR
        )
        content = gzip.decompress((parent / f"native/{ident}.json.gz").read_bytes())
        digest = sources[ident]["jobs"][0]["donor_native_sha256"]
        if sha256(content).hexdigest() != digest:
            raise ValueError("donor archive changed before verification")
        donor = json.loads(content)
        support_cross.join(donor, capture)
        probes = {
            (r["visit_index"], r["receiver_id"]): (r, c)
            for r, c in zip(donor["source"]["probes"], capture["source"]["probes"], strict=True)
        }
        frame = capture["source"]["sample_rate_hz"] / FRAME_HZ
        for m in measures:
            if m["id"] != ident:
                continue
            d, c = probes[m["visit"], m["lane"]]
            winner = agreement.best(d["candidates"])
            if fingerprint(winner) != m["winner_sha256"]:
                raise ValueError("the late-symbol score was applied to a different winning pilot")
            classified.append(dict(**m, label=agreement.label(winner, c["candidates"], frame)))
        raw = [t["cpu_ns"] / 1e6 for t in timings if t["id"] == ident]
        counters.append(
            dict(
                id=ident,
                **row_counts([m for m in classified if m["id"] == ident]),
                measured_visits=len(raw),
                verification_p50_ms=float(np.median(raw)),
                verification_p95_ms=float(np.percentile(raw, 95)),
            )
        )
        capture_hashes[ident] = case["native"]["sha256"]
    write(REPORT / "capture-labels.jsonl.gz", compressed_rows(classified))
    csv_file(REPORT / "stage.csv", counters)
    save_json(
        REPORT / "verification-lock.json",
        dict(
            source_sha256=_sha(Path(__file__)),
            prediction_lock_sha256=_sha(REPORT / "prediction-lock.json"),
            capture_native_sha256=capture_hashes,
            files={n: _sha(REPORT / n) for n in ("capture-labels.jsonl.gz", "stage.csv")},
        ),
    )


def render(folder):
    receipt = whole_iq.read(folder / "verification-lock.json")
    with whole_iq.checked(folder / "stage.csv", receipt["files"]["stage.csv"]).open() as f:
        rows = list(csv.DictReader(f))
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    fig.subplots_adjust(left=0.16, right=0.94, top=0.77, bottom=0.12)
    fig.suptitle(
        "Which added pilots also pass the later-symbol check?",
        x=0.06,
        y=0.97,
        ha="left",
        fontweight="bold",
        fontsize=16,
    )
    fig.text(
        0.06,
        0.84,
        "Each label counts passing receiver probes out of all probes in its group.",
        fontsize=10,
    )
    for j, (group, legend, color) in enumerate(
        (
            ("original_matched", "Matches an original pilot", "#007c71"),
            ("other", "All other added pilots", "#40567d"),
        )
    ):
        for i, row in enumerate(rows):
            den = int(row[group])
            if den:
                hit = int(row[group + "_verified"])
                val = 100 * hit / den
                y = i + (j - 0.5) * 0.30
                ax.barh(y, val, 0.26, color=color, label=legend if i == 0 else None)
                ax.text(
                    val - 1, y, f"{hit}/{den}", ha="right", va="center", color="white", fontsize=9
                )
    ax.set(
        yticks=range(len(rows)),
        yticklabels=[r["id"] for r in rows],
        xlim=(0, 104),
        xlabel="Share passing both late pilot blocks (%)",
    )
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#e0e5e8")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncols=2, frameon=False, fontsize=9)
    fig.savefig(folder / "late-symbols.png", dpi=160)
    fig.savefig(folder / "late-symbols.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    names = ("stage.csv", "late-symbols.png", "late-symbols.pdf", "verification-lock.json")
    save_json(folder / "stage-lock.json", dict(files={n: _sha(folder / n) for n in names}))
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="verified-rescue-later-symbols",
            title="Do later pilot symbols discriminate among newly detected signals?",
            sample=f"{sum(int(r['proposed']) for r in rows):,} added probes on four recordings",
            boundary="Recorded CI16 through the two-block code test at fixed pilot coordinates",
            note="Other gains include probes where the original detector returned no pilot.",
            seal="stage-lock.json",
            image="late-symbols.png",
            pdf="late-symbols.pdf",
            csv="stage.csv",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "plot"))
    parser.add_argument("--out", type=local_output, default=REPORT)
    args = parser.parse_args()
    if args.action == "audit":
        audit()
    else:
        render(args.out)
