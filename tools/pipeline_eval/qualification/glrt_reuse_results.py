"""Verify the wide preparation receipts and render detector stage evidence offline."""

import argparse
import io
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import distribution
from . import glrt_reuse_eval as run
from . import scout_stage_figures as plot
from .prefix_figures import csv_file

KEYS = ("native_cpu_ms", "wrapper_cpu_ms", "wall_ms", *run.CLOCKS)


def trials(ident, row):
    for mode, values in row["timings"].items():
        if len(values) != 9:
            raise ValueError("a quiet replay changed the paired repetition roster")
        for index, value in enumerate(values, 1):
            yield dict(
                id=ident,
                visit=row["visit"],
                cohort=row["cohort"],
                detector=mode,
                repeat=index,
                native_cpu_ms=value["detector_cpu_ms"],
                wrapper_cpu_ms=value["cpu_ms"],
                wall_ms=value["wall_ms"],
                **value["profile"],
            )


def summarize(scheduled):
    raw = [item for ident, row in scheduled for item in trials(ident, row)]
    clocks = {mode: [row for row in raw if row["detector"] == mode] for mode in run.MODES}
    measurement = {
        mode: dict(
            calls=len(rows),
            deadline={k: sum(r[k] <= 20 for r in rows) for k in KEYS[:3]},
            **{k: distribution([r[k] for r in rows]) for k in KEYS},
        )
        for mode, rows in clocks.items()
    }
    pairs = list(zip(*(clocks[k] for k in run.MODES), strict=True))
    return dict(
        admitted_visits=len(scheduled),
        exact_payloads=sum(row["exact"] for _, row in scheduled),
        candidates=sum(
            len(rx["candidates"]) for _, r in scheduled for rx in r["payloads"]["control"]["rows"]
        ),
        gate_positives=sum(len(rx) for _, r in scheduled for rx in r["positives"]["control"]),
        roles=measurement,
        paired_candidate_minus_control_ms={
            k: distribution([b[k] - a[k] for a, b in pairs]) for k in KEYS
        },
        median_paired_pct={
            k: median(100 * (b[k] / a[k] - 1) for a, b in pairs)
            for k in ("native_cpu_ms", "preparation_cpu_ms", "wall_ms")
        },
    ), raw


def receipts():
    lock = run.wide.load(run.REPORT / "source-lock.json")
    digest = run._digest(encoded(lock))
    if any(run._sha(ROOT / p) != sha for p, sha in lock["inputs"].items()):
        raise ValueError("a measured input or source file changed after the replay")
    admitted, excluded, controls = [], [], {}
    for ident, expected in lock["roster"].items():
        actual = run.wide.load(run.REPORT / f"{ident}.json.gz")
        if actual["id"] != ident or actual["lock_sha256"] != digest:
            raise ValueError("receipt does not bind the fixed waveform lock")
        for bound, row in zip(expected, actual["rows"], strict=True):
            if any(row[k] != value for k, value in bound.items()):
                raise ValueError("archived real selection changed in the candidate replay")
            (admitted if row["status"] == "processed" else excluded).append((ident, row))
        if actual["controls"]:
            controls[ident] = {
                label: dict(
                    exact=row["exact"],
                    tones=row["planted"],
                    positive_counts={
                        k: [len(rx) for rx in votes] for k, votes in row["positives"].items()
                    },
                    iq_sha256=row["iq_sha256"],
                )
                for label, row in actual["controls"].items()
            }
    complete, csv = summarize(admitted)
    return dict(
        position_attempted=False,
        measured=complete,
        cohorts={
            name: summarize([(i, r) for i, r in admitted if r["cohort"] == name])[0]
            for name in ("held", "cpu-tail")
        },
        exclusions=[dict(row, id=ident) for ident, row in excluded],
        controls=controls,
        memory=run.wide.load(run.REPORT / "memory.json"),
        binary=lock["release"]["library_sha256"],
        matched_geometry=dict(
            iq_bytes=1_600_000,
            prepared_payload_bytes=12_800_016,
            new_persistent_bytes=0,
            candidate_wide_packed_loads=100_000,
            candidate_wide_pair_square_adds=100_000,
            candidate_wide_integer_prefix_updates=200_000,
            stock_per_receiver_input_passes=2,
            candidate_two_receiver_input_passes=1,
        ),
    ), csv


def render(data, out):
    m = data["measured"]
    fig, (cpu, wall) = plot.canvas(
        "One-pass dual-receiver preparation in the wide detector",
        f"{m['admitted_visits']} authentic visits · nine matched calls per visit · x86 host",
        f"All public detector fields match on {m['exact_payloads']}/{m['admitted_visits']} visits. "
        "Buffer sizes stay fixed. Preparation CPU uses the native profile API. "
        "Total call wall includes the Python wrapper. This evidence ends at detector output.",
    )
    fig.subplots_adjust(bottom=0.278)
    roles = m["roles"]
    plot.paired(
        cpu,
        ("Preparation p50", "Preparation p95", "Native CPU p50", "Native CPU p95"),
        [
            tuple(roles[mode][k][q] for mode in run.MODES)
            for k in ("preparation_cpu_ms", "native_cpu_ms")
            for q in ("p50", "p95")
        ],
        title="CPU cost",
        xlabel="Milliseconds",
    )
    plot.paired(
        wall,
        ("All visits", "Previously held", "Prior CPU tail"),
        [
            tuple(
                100 * cohort["roles"][mode]["deadline"]["wall_ms"] / cohort["roles"][mode]["calls"]
                for mode in run.MODES
            )
            for cohort in (m, *data["cohorts"].values())
        ],
        title="20 ms wall deadline",
        xlabel="Complete detector calls within deadline (%)",
        xmax=111,
        fmt=".1f",
    )
    plot.key(fig, "Stock wide", "One-pass dual-RX preparation")
    fig.legends[-1].set_bbox_to_anchor((0.052, 0.148))
    for ext in ("png", "pdf"):
        buffer = io.BytesIO()
        options = {"dpi": 165} if ext == "png" else {"metadata": {"CreationDate": None}}
        fig.savefig(buffer, format=ext, facecolor="white", **options)
        write(out / f"glrt-reuse.{ext}", buffer.getvalue())
    plot.plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=local_output, default=run.REPORT)
    out = p.parse_args().out
    data, csv = receipts()
    save_json(out / "qualification.json", data)
    csv_file(out / "timing.csv", csv)
    render(data, out)
    names = ["qualification.json", "timing.csv", "glrt-reuse.png", "glrt-reuse.pdf"]
    if out == run.REPORT:
        names += [
            "PROTOCOL.md",
            "source-lock.json",
            "memory.json",
            "build-receipt.json",
            "release.json",
            *(f"{ident}.json.gz" for ident in run.CASES),
        ]
    save_json(
        out / "evidence-lock.json",
        dict(
            cases=list(run.CASES),
            files={name: run._sha(out / name) for name in names},
            scorer_sha256=run._sha(Path(__file__)),
            position_attempted=False,
        ),
    )


if __name__ == "__main__":
    main()
