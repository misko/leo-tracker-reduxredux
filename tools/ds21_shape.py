"""Measured DS21 Model B: native supported channel trajectories, GLS constants."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.regional_position_score import ALIAS_HZ, coordinates
from leo.analysis.research.doppler_shape_orbits import (
    DopplerShapeOrbitObjective,
    fit_doppler_shape,
    held_shape_score,
)


def supported_sequences(observations, tracks=None, *, maximum_gap_s=4.0, split_alias=True):
    """Freeze disjoint supported chains; no interpolation or inferred long tracks.

    Training tracks are the existing RF-blind Hough tracklets. Restricting them
    to original receiver/channel/RF lanes preserves their observed branch.
    Raw alias crossings split a chain conservatively rather than unwrap anew.
    Held chains use metadata only and include all non-singleton lane support.
    """
    if tracks is None:
        lanes = {}
        for row in range(len(observations.window_ids)):
            key = (
                int(observations.receiver[row]),
                int(observations.channel[row]),
                float(observations.rf_hz[row]),
            )
            lanes.setdefault(key, []).append(row)
        tracks = tuple(lanes.values())
    sequences, used = [], set()
    for track in tracks:
        rows = sorted(
            set(track), key=lambda r: (observations.times_s[r], observations.window_ids[r])
        )
        chunk = []
        for row in rows:
            if row in used:
                if len(chunk) >= 2:
                    sequences.append(tuple(chunk))
                    used.update(chunk)
                chunk = []
                continue
            broken = False
            if chunk:
                previous = chunk[-1]
                broken = (
                    observations.times_s[row] - observations.times_s[previous] > maximum_gap_s
                    or observations.receiver[row] != observations.receiver[previous]
                    or observations.channel[row] != observations.channel[previous]
                    or observations.rf_hz[row] != observations.rf_hz[previous]
                    or (
                        split_alias
                        and abs(observations.measured_hz[row] - observations.measured_hz[previous])
                        > ALIAS_HZ / 2.0
                    )
                )
            if broken:
                if len(chunk) >= 2:
                    sequences.append(tuple(chunk))
                    used.update(chunk)
                chunk = []
            chunk.append(row)
        if len(chunk) >= 2:
            sequences.append(tuple(chunk))
            used.update(chunk)
    return tuple(sequences)


def sequence_audit(observations, sequences):
    return {
        "sequences": len(sequences),
        "observations": sum(map(len, sequences)),
        "shape_dof": sum(len(r) - 1 for r in sequences),
        "spans_s": [float(np.ptp(observations.times_s[list(r)])) for r in sequences],
        "maximum_observed_gap_s": max(
            (float(np.max(np.diff(observations.times_s[list(r)]))) for r in sequences), default=None
        ),
        "unscored_windows": len(observations.window_ids) - sum(map(len, sequences)),
    }


def run(label, *, output=None, maximum_seconds=20.0, maximum_iterations=600):
    import ds21_common as shared
    from ds21_common import OUTPUT, digest, immutable, load_case

    output = OUTPUT if output is None else output
    begun = time.monotonic()
    case = load_case(label, output=output)
    directory = output / "local/model-b-shape-v1" / label
    source_root = Path(__file__).parents[1]
    sources = [
        Path(__file__),
        Path(shared.__file__),
        source_root / "src/leo/analysis/research/doppler_shape_model.py",
        source_root / "src/leo/analysis/research/doppler_shape_orbits.py",
        source_root / "src/leo/analysis/regional_position_score.py",
    ]
    snapshots = {}
    for source in sources:
        target = directory / "source-snapshot" / source.name
        source_bytes = source.read_bytes()
        if target.exists():
            if target.read_bytes() != source_bytes:
                raise ValueError(f"Frozen Model B source differs: {source.name}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_bytes)
        snapshots[source.name] = digest(target)
    protocol = {
        "model": "offset-invariant-doppler-shape",
        "label": label,
        "common_protocol_sha256": case["protocol_sha256"],
        "source_snapshots": snapshots,
        "source_sha256": digest(Path(__file__)),
        "model_sha256": digest(
            Path(__file__).parents[1] / "src/leo/analysis/research/doppler_shape_orbits.py"
        ),
        "maximum_seconds_per_start": maximum_seconds,
        "maximum_iterations": maximum_iterations,
        "maximum_case_slice_seconds": 500.0,
        "sigma_hz": 400.0,
        "timing": "one common orbit shift; sigma2s; bound10s",
        "sequence": (
            "existing training bootstrap tracklets; exact receiver/channel/RF; "
            "gap<=4s; raw alias crossings split"
        ),
        "absolute_offsets": "one free constant per supported sequence; no track slopes",
        "c_arms": "same observations,bank,three starts,priors,budgets; constant-RF c projected out",
        "held": (
            "all metadata lane chains gap<=4s; no CFO selection; "
            "frozen training-weighted bank mixture"
        ),
        "reference_usage": "none",
    }
    immutable(directory / "protocol.json", protocol)
    starts = [[row["east_km"], row["north_km"]] for row in case["discovery"]["selected"]]
    rows = []
    for view, prepared in case["prepared"].items():
        observations = prepared.observations
        sequences = supported_sequences(observations, prepared.bootstrap_tracks)
        audit = sequence_audit(observations, sequences)
        short = sequence_audit(
            observations,
            supported_sequences(observations, prepared.bootstrap_tracks, maximum_gap_s=0.1),
        )
        if not sequences:
            rows.append(
                {
                    "view": view,
                    "state": "unavailable",
                    "reason": "no supported shape chains",
                    "support": audit,
                    "short_chain_audit": short,
                }
            )
            continue
        objective = DopplerShapeOrbitObjective(observations, case["bank"], case["prior"], sequences)
        for arm in ("zero-c", "fitted-c"):
            path = directory / f"{view}-{arm}.json"
            if path.exists():
                rows.append(json.loads(path.read_bytes()))
                continue
            if time.monotonic() - begun + 3.0 * maximum_seconds + 10.0 >= 500.0:
                checkpoint = {
                    "label": label,
                    "model": "B",
                    "state": "checkpointed",
                    "next_view": view,
                    "next_arm": arm,
                    "completed_rows": len(rows),
                }
                print(json.dumps(checkpoint), flush=True)
                return checkpoint
            result = fit_doppler_shape(
                objective,
                starts,
                rf_arm=arm,
                maximum_seconds=maximum_seconds,
                maximum_iterations=maximum_iterations,
            )
            result.update(
                view=view,
                label=label,
                support=audit,
                short_chain_audit=short,
                common_protocol_sha256=case["protocol_sha256"],
                prepared_sha256=prepared.evidence_sha256,
            )
            winner = result["winner"]
            if winner:
                winner["coordinates_deg"] = coordinates(case["prior"], winner["theta"][:2])
                if view in case["held"]:
                    held = case["held"][view]
                    held_sequences = supported_sequences(held, split_alias=False)
                    if held_sequences:
                        held_objective = DopplerShapeOrbitObjective(
                            held, case["bank"], case["prior"], held_sequences
                        )
                        result["held_shape"] = held_shape_score(
                            objective, winner["theta"], held_objective, fitted_c=arm == "fitted-c"
                        )
                        result["held_support"] = sequence_audit(held, held_sequences)
            immutable(path, result)
            rows.append(result)
            print(
                json.dumps(
                    {
                        "label": label,
                        "view": view,
                        "arm": arm,
                        "winner": None
                        if winner is None
                        else {
                            k: winner[k]
                            for k in ("theta", "objective", "gradient_norm", "information")
                        },
                        "support": audit,
                    }
                ),
                flush=True,
            )
    terminal = {
        "label": label,
        "model": "B",
        "protocol_sha256": digest(directory / "protocol.json"),
        "rows": rows,
        "state": "complete",
        "reference_usage": "none",
    }
    immutable(directory / "terminal.json", terminal)
    return terminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--maximum-seconds", type=float, default=20.0)
    parser.add_argument("--maximum-iterations", type=int, default=600)
    args = parser.parse_args()
    run(
        args.label,
        output=args.output,
        maximum_seconds=args.maximum_seconds,
        maximum_iterations=args.maximum_iterations,
    )


if __name__ == "__main__":
    main()
