"""Sealed whole-probe replication of the frozen eight-tone pilot model."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.storage import RecordingStore
from tools.research.joint_template_source_isolation import fit_templates, seeded_group_split
from tools.research.replay_joint_pilot_isolation import COUNT, FS, ROOT, serial, tones


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_nominees(row):
    result = {}
    for rx in ("0", "1"):
        by_rank = {
            p["candidate_rank"]: p
            for component in row["receiver_components"][rx]
            for p in component
        }
        result[rx] = [by_rank[rank] for rank in row["nominees"][rx]]
    return result


def run_models(iq, picks, index):
    """Identical frozen within-snippet calibration and response policy as stream-1."""
    n = np.arange(COUNT)
    split = seeded_group_split(n // 250, seed=20260925 + index)
    mask = (n % 250 >= 16) & (n % 250 < 234)
    result = dict(training_group_ids=np.unique((n // 250)[split]).tolist(), receivers={})
    for rx in (0, 1):
        a, b = picks[str(rx)]
        exact = np.array(
            [tones(int(p["local_epoch_sample"]), p["tracking_cfo_hz"]) for p in (a, b)]
        )
        rolled = np.array(
            [tones(int(p["local_epoch_sample"]), p["tracking_cfo_hz"], 17) for p in (a, b)]
        )
        swapped = np.array(
            [tones(int(q["local_epoch_sample"]), p["tracking_cfo_hz"]) for p, q in ((a, b), (b, a))]
        )
        models = dict(
            exact_ab=exact,
            single_a=exact[:1],
            single_b=exact[1:],
            exact_a_rolled_b=np.array([exact[0], rolled[1]]),
            rolled_a_exact_b=np.array([rolled[0], exact[1]]),
            both_rolled=rolled,
            swapped_epochs=swapped,
        )
        fitted = {}
        for name, model in models.items():
            fitted[name] = asdict(
                fit_templates(
                    iq[mask, rx], model[:, :, mask], n[mask], split[mask], sample_rate_hz=FS
                )
            )
        result["receivers"][str(rx)] = dict(
            models=fitted,
            held_energy=float(np.sum(abs(iq[mask & ~split, rx]) ** 2)),
            train_indices_sha256=hashlib.sha256(
                n[mask & split].astype("<i8").tobytes()
            ).hexdigest(),
            held_indices_sha256=hashlib.sha256(
                n[mask & ~split].astype("<i8").tobytes()
            ).hexdigest(),
        )
    return result


def selected_opportunities(population, partition):
    rows = sorted(population["opportunities"], key=lambda r: r["sample_start"])
    if len(rows) != 10 or len({r["sample_start"] for r in rows}) != 10:
        raise ValueError("ten unique opportunities required")
    selected = [(i, r) for i, r in enumerate(rows) if r["partition"] == partition]
    if len(selected) != 5:
        raise ValueError("five whole probes per partition required")
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--partition", choices=("train", "held"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--training-directory", type=Path)
    args = parser.parse_args()
    if args.freeze:
        if args.seal.exists():
            raise ValueError("seal already exists")
        sources = [
            args.population.resolve(),
            Path(__file__),
            ROOT / "tools/research/joint_template_source_isolation.py",
            ROOT / "tools/research/replay_joint_pilot_isolation.py",
            ROOT / "src/leo/analysis/starlink/templates.py",
            ROOT / "reports/2026_09_23_stream0_pilot_replication_protocol.md",
        ]
        args.seal.write_text(
            json.dumps({str(p.relative_to(ROOT)): digest(p) for p in sources}, indent=2) + "\n"
        )
        return
    if args.partition is None or args.output is None:
        raise ValueError("partition and output required")
    seal = json.loads(args.seal.read_text())
    for name, expected in seal.items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"sealed source changed: {name}")
    if str(args.population.resolve().relative_to(ROOT)) not in seal:
        raise ValueError("population not sealed")
    population = json.loads(args.population.read_text())
    if population["edge"] != "upper":
        raise ValueError("frozen template requires verified upper edge")
    chosen = selected_opportunities(population, args.partition)
    if args.partition == "held":
        if args.training_directory is None:
            raise ValueError("training completion required")
        completion = json.loads((args.training_directory / "completion.json").read_text())
        expected = [r["sample_start"] for _, r in selected_opportunities(population, "train")]
        if completion["probe_starts"] != expected or completion["seal_sha256"] != digest(args.seal):
            raise ValueError("training completion or seal mismatch")
        for name, expected_digest in completion["output_hashes"].items():
            if digest(args.training_directory / name) != expected_digest:
                raise ValueError("training result changed")
    args.output.mkdir(parents=True, exist_ok=False)
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    outputs = {}
    try:
        bundle = store.inspect(population["session_id"])
        reader = store.reader(bundle, "stream-0", verify=True)
        for index, row in chosen:
            result = dict(
                index=index,
                sample_start=row["sample_start"],
                time_s=row["time_s"],
                partition=args.partition,
                status=row["status"],
            )
            if row["status"] == "eligible":
                raw = reader.read(row["sample_start"], COUNT, receiver_ids=(0, 1))
                iq = (raw[:, :, 0].astype(float) + 1j * raw[:, :, 1].astype(float)) / 32768
                picks = resolve_nominees(row)
                result.update(raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest(), nominees=picks)
                result.update(run_models(iq, picks, index))
            path = args.output / f"probe-{index}.json"
            path.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False) + "\n")
            outputs[path.name] = digest(path)
            print(index, row["time_s"], row["status"], flush=True)
    finally:
        store.close()
    (args.output / "completion.json").write_text(
        json.dumps(
            dict(
                probe_starts=[r["sample_start"] for _, r in chosen],
                seal_sha256=digest(args.seal),
                output_hashes=outputs,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
