"""Seal direct CFO measurements at differential pilot times before scoring references."""

import argparse
import csv
import gzip
import io
import json
from pathlib import Path
from time import process_time_ns

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import differential_pilot as timing
from ..variants import pilot_carrier
from . import differential_pilot_eval as parent
from . import hinted_glrt_trial, oracle_start
from .full_v5_check import _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-frontier/pilot-carrier"
COHORTS = {"primary": "", "confirmation": "-confirmation"}
PARENT_SEAL = "536064c122033695dbe0735ae85feb00cd778cc25631f2c13c358125afe12d0b"


def capture(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def save_rows(path, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
    writer.writeheader()
    writer.writerows(rows)
    write(path, buffer.getvalue().encode())


def measured(samples, lane, edge, centers):
    for lag in (timing.LAG, pilot_carrier.SHORT_LAG):
        pilot_carrier.coefficients(edge, lag)
    start = process_time_ns()
    signals = pilot_carrier.products(samples, lane)
    setup_us = (process_time_ns() - start) / 1000
    values = []
    for mode, epoch in centers:
        start = process_time_ns()
        estimate = pilot_carrier.at_epoch(signals, edge, epoch)
        values.append(
            dict(
                mode=mode,
                epoch=epoch,
                estimate=estimate,
                projection_us=(process_time_ns() - start) / 1000,
            )
        )
    return dict(setup_us=setup_us, estimates=values)


def proposals(epochs):
    ranked = [(f"rank{i}", int(e)) for i, e in enumerate(epochs[:4], 1)]
    if ranked:
        ranked.append(("sham", (ranked[0][1] + timing.FRAME // 2) % timing.FRAME))
    return ranked


def predict(parent_dir, out):
    if (out / "prediction-lock.json").exists() or (out / "source-lock.json").exists():
        raise FileExistsError("use a fresh report directory for a waveform replay")
    paths = {
        (cohort, case): parent_dir / f"{case}{suffix}.json.gz"
        for cohort, suffix in COHORTS.items()
        for case in parent.CASES
    }
    files = {p.name: _sha(p) for p in paths.values()}
    parent_lock = parent_dir / "prediction-lock.json"
    published = json.loads(parent_lock.read_bytes())["files"]
    if _sha(parent_lock) != PARENT_SEAL or any(published.get(k) != v for k, v in files.items()):
        raise ValueError("differential timing receipts differ from the published native replay")
    sources = (Path(__file__), Path(pilot_carrier.__file__), Path(timing.__file__))
    save_json(
        out / "source-lock.json",
        dict(
            parents=files,
            parent_prediction_sha256=PARENT_SEAL,
            protocol_sha256=_sha(out / "PROTOCOL.md"),
            sources={str(p.relative_to(ROOT)): _sha(p) for p in sources},
        ),
    )
    controls = []
    for edge in ("lower", "upper"):
        for condition in parent.CONTROLS:
            samples, target = parent.synthetic(edge, condition)
            for lane, (centers, _) in enumerate(timing.scout(samples, edge)):
                result = measured(samples, lane, edge, proposals(centers[:1]))
                controls.append(
                    dict(edge=edge, condition=condition, lane=lane, target=target, **result)
                )
    save_json(out / "control-predictions.json", controls)
    rows = []
    for (cohort, case), path in paths.items():
        binding = _load_case(case)
        for scheduled in capture(path):
            key = {k: scheduled[k] for k in ("case", "visit", "receiver", "iq_sha256")}
            if scheduled["status"] != "processed":
                rows.append(dict(**key, cohort=cohort, status="unavailable"))
                continue
            window = hinted_glrt_trial.load_selected(binding, scheduled)
            edge = window.target["edge"]
            lane = key["receiver"]
            centers = timing.scout(window.samples, edge)[lane][0]
            if centers != scheduled["measurement"]["centers"][lane]:
                raise ValueError("replayed timing candidates differ from the parent's saved array")
            result = measured(window.samples, lane, edge, proposals(centers))
            rows.append(dict(**key, cohort=cohort, edge=edge, status="ok", **result))
    if len(rows) != 32 or len({(r["case"], r["visit"]) for r in rows}) != 32:
        raise ValueError("expected 24 primary and eight disjoint confirmation visits")
    payload = b"".join(encoded(r) + b"\n" for r in rows)
    write(out / "predictions.jsonl.gz", gzip.compress(payload, mtime=0))
    members = ("source-lock.json", "control-predictions.json", "predictions.jsonl.gz")
    save_json(out / "prediction-lock.json", dict(files={n: _sha(out / n) for n in members}))


def difference(value, period):
    return (value + period / 2) % period - period / 2


def errors(row, target_epoch, target_hz):
    epoch_error = difference(row["epoch"] - target_epoch, timing.RATE / 750)
    scored = dict(mode=row["mode"], epoch=row["epoch"], epoch_error_samples=epoch_error)
    estimate = row["estimate"]
    if estimate is None:
        return scored
    absolute = estimate["absolute_hz"] - target_hz
    folded = difference(estimate["folded_hz"] - target_hz, timing.RATE / timing.LAG)
    nearest = pilot_carrier.GRID_HZ * round(target_hz / pilot_carrier.GRID_HZ)
    return dict(
        **scored,
        **estimate,
        absolute_error_hz=absolute,
        folded_error_hz=folded,
        bin_steps=abs(estimate["grid_hz"] - nearest) / pilot_carrier.GRID_HZ,
    )


def score(parent_dir, out):
    for n, digest in json.loads((out / "prediction-lock.json").read_bytes())["files"].items():
        if _sha(out / n) != digest:
            raise ValueError("CFO predictions changed")
    sources = json.loads((out / "source-lock.json").read_bytes())
    reference = {}
    for cohort, prefix in COHORTS.items():
        for case in parent.CASES:
            path = parent_dir / f"{case}{prefix}.json.gz"
            if _sha(path) != sources["parents"][path.name]:
                raise ValueError("parent waveform measurements changed")
            for r in capture(path):
                reference[cohort, case, r["visit"], r["receiver"]] = r
    rows = []
    for line in gzip.decompress((out / "predictions.jsonl.gz").read_bytes()).splitlines():
        data = json.loads(line)
        key = {k: data[k] for k in ("cohort", "case", "visit", "receiver")}
        original = reference[tuple(key.values())]
        if data["iq_sha256"] != original["iq_sha256"]:
            raise ValueError("different raw interval in CFO trial")
        target = original["target"]
        epoch = oracle_start.exact_epoch(target)
        target_hz = target["fractional_tracking_cfo_hz"]
        state = dict(**key, kind=original["kind"], target_epoch=epoch, target_cfo_hz=target_hz)
        for row in data.get("estimates", []):
            rows.append(
                dict(
                    **state,
                    **errors(row, epoch, target_hz),
                    projection_us=row["projection_us"],
                    setup_us=data["setup_us"],
                )
            )
        if not data.get("estimates"):
            rows.append(dict(**state, mode="rank1", status=data["status"]))
    save_rows(out / "carrier.csv", rows)
    controls = []
    for r in json.loads((out / "control-predictions.json").read_bytes()):
        labels = {k: r[k] for k in ("edge", "condition", "lane")}
        if not r["estimates"]:
            controls.append(dict(**labels, mode="rank1", epoch=None))
        for result in r["estimates"]:
            t = r["target"]
            if t["plant"]:
                controls.append(dict(**labels, **errors(result, t["epoch"], t["cfo_hz"])))
            else:
                controls.append(dict(**labels, mode=result["mode"], epoch=result["epoch"]))
    save_rows(out / "controls.csv", controls)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("predict", "score"))
    cli.add_argument("--parent", type=Path, default=parent.REPORT)
    cli.add_argument("--out", type=local_output, default=REPORT)
    args = cli.parse_args()
    {"predict": predict, "score": score}[args.action](args.parent, args.out)


if __name__ == "__main__":
    main()
