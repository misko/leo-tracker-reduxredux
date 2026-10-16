"""Bounded exposed-data test of preserving independent channel-view hypotheses.

The recorded half-view scientific states seed a common bank/calibration model.
This is a development counterfactual; fresh train-only discovery is required
before any held-out/generalization claim. References are read only by evaluate.
"""

import argparse
import gzip
import json
import runpy
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from ds20_channel_corpus import ADAPTER, AUTHORITY, OUTPUT, ROOT, digest, write

from leo.analysis.channel_group_calibration import (
    GroupCalibrationObjective,
    fit_group_calibration,
    project_calibration_seed,
)
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import coordinates, zero_sum_basis
from leo.application.hard60_runner import HARD60_SCORE
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import RegionalPrior
from leo.contracts.regional_position_v3 import RegionalPositionDocumentV3
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def documents(session):
    path = AUTHORITY / "diagnostics/upstream-band-next-donor-inventory.json"
    inventory = json.loads(path.read_bytes())
    result, provenance = {}, {}
    for entry in inventory["views"]:
        if entry["session_id"] == session:
            source = Path(entry["document_path"])
            if digest(source) != entry["document_file_sha256"]:
                raise ValueError("Recorded view document hash differs")
            raw = source.read_bytes()
            if raw.startswith(b"\x1f\x8b"):
                raw = gzip.decompress(raw)
            envelope = json.loads(raw)
            if "publications" in envelope:
                raw = json.dumps(
                    envelope["publications"]["regional-position-v3"]["manifest"]["document"]
                ).encode()
            doc = RegionalPositionDocumentV3.model_validate_json(raw)
            result[entry["view"]] = doc.model_dump(mode="json")
            provenance[entry["view"]] = dict(path=str(source), sha256=digest(source))
    if set(result) != {"all", "low", "high"}:
        raise ValueError("Three recorded channel-view scientific hypotheses required")
    return result, provenance


def state(doc, observations):
    fit = doc["diagnostics"]["b7"]["attempts"]["B4W"]["fitted-c"]
    if not fit["converged"]:
        raise ValueError("A stationary B4W hypothesis is required")
    joint = fit["joint_state"]
    numbers = doc["methods"][0]["arms"][0]["selected"]["satellites"]
    vector = np.asarray(fit["vector"])
    if len(vector) != 7 + len(numbers):
        raise ValueError("Selected satellite bank differs from recorded B4W state")
    raw = np.asarray(joint["receiver_baseline_hz"])
    if raw.shape != observations.times_s.shape:
        raise ValueError("Frozen calibration rows differ from native observation view")
    affine = []
    for rx in (0, 1):
        mask = observations.receiver == rx
        x = np.column_stack([np.ones(mask.sum()), observations.times_s[mask] - 150])
        coef = np.linalg.lstsq(x, raw[mask], rcond=None)[0]
        if np.max(abs(x @ coef - raw[mask])) > 1e-5:
            raise ValueError("Frozen receiver baseline is not affine after knot restoration")
        affine.append(coef)
    return dict(
        vector=vector,
        numbers=numbers,
        shifts=vector[7] + zero_sum_basis(len(numbers)) @ vector[8:],
        baseline_affine=np.asarray(affine),
        time_center=observations.time_center_s,
        rf_center=observations.rf_center_hz,
        nodes=np.asarray(joint["clock_nodes_s"]),
        knots=np.asarray(joint["clock_knots_hz"]),
    )


def correction(scientific, observations):
    v = scientific["vector"]
    t, rx = observations.times_s, observations.receiver
    a = scientific["baseline_affine"]
    return (
        a[rx, 0]
        + a[rx, 1] * (t - 150)
        + v[2 + 2 * rx]
        + v[3 + 2 * rx] * (t - scientific["time_center"])
        + v[6] * (observations.rf_hz - scientific["rf_center"]) / 1e9
        + np.array(
            [
                np.interp(time, scientific["nodes"], scientific["knots"][r])
                for time, r in zip(t, rx, strict=True)
            ]
        )
    )


def variant_name(group_drift, group_clock):
    return (
        "hypothesis-carry-group-clock-v4"
        if group_clock
        else "hypothesis-carry-drift-v4"
        if group_drift
        else "hypothesis-carry-constant-v4"
    )


def execute(session, *, group_drift=False, group_clock=False):
    group_drift = group_drift or group_clock
    begun = time.monotonic()
    membership = json.loads((OUTPUT / "membership.json").read_bytes())
    member = next(m for m in membership["members"] if m["session_id"] == session)
    if member["role"] != "development":
        raise ValueError("The exploratory hypothesis prototype is restricted to development")
    variant = variant_name(group_drift, group_clock)
    directory = OUTPUT / "local" / variant / session
    if (directory / "terminal.json").exists():
        raise ValueError("Terminal already exists; do not repeat an immutable trial")
    docs, origins = documents(session)
    source_path = Path(member["input"]["path"])
    if digest(source_path) != member["input"]["sha256"]:
        raise ValueError("Frozen DS20 input changed")
    source = runpy.run_path(str(ADAPTER))["load_tracking_input"](
        json.loads(source_path.read_bytes())
    )
    origin = source.timing.session_start_device_sample_counter
    starts = np.array(
        [
            p.valid_start_counter - origin + p.probe_start_ms * source.sample_rate_hz // 1000
            for p in source.probes
        ]
    )
    ends = starts + source.probe_ms * source.sample_rate_hz // 1000
    nodes = np.arange(
        np.floor(starts.min() / source.sample_rate_hz / 30) * 30,
        np.ceil(ends.max() / source.sample_rate_hz / 30) * 30 + 1,
        30.0,
    )
    prepared = {}
    for view, channels in membership["views"].items():
        filtered = replace(source, probes=tuple(p for p in source.probes if p.channel in channels))
        prepared[view] = prepare_position_windows(filtered)
    hypotheses = {name: state(doc, prepared[name].observations) for name, doc in docs.items()}
    snapshot_digest = docs["all"]["diagnostics"]["snapshot_sha256"]
    if any(doc["diagnostics"]["snapshot_sha256"] != snapshot_digest for doc in docs.values()):
        raise ValueError("Channel hypotheses have different causal TLE snapshots")
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = next(s for s in archive.list_snapshots() if s.digest == snapshot_digest)
    catalogue = parse_element_sets(archive.read(snapshot))
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    )
    prior = RegionalPrior(**docs["all"]["configuration"]["prior"])
    full = prepared["all"]
    bank, _ = build_regional_bank(
        catalogue, indices, full.start_utc_ns, full.observations, prior, maximum_seconds=180
    )
    numbers = sorted({number for s in hypotheses.values() for number in s["numbers"]})
    lookup = {int(n): i for i, n in enumerate(bank.numbers)}
    shared_bank = bank.select([lookup[n] for n in numbers])
    protocol = dict(
        policy="preserve-channel-hypotheses-development-v4",
        session_id=session,
        membership_sha256=digest(OUTPUT / "membership.json"),
        input_sha256=digest(source_path),
        sources=origins,
        catalogue_numbers=numbers,
        snapshot_sha256=snapshot_digest,
        prior=docs["all"]["configuration"]["prior"],
        starts=["low", "high", "all"],
        seconds_per_fit=45,
        iterations=600,
        arms=["fitted-c", "zero-c"],
        group_sigma_hz=50000,
        group_drift_sigma_hz_s=2 if group_drift else None,
        differential_clock_prior="same smooth-clock precision as common clock"
        if group_clock
        else None,
        clock_prior_scale=4,
        clock_nodes_s=nodes.tolist(),
        seed_projection="Bounded linear projection into the actual fitting constraints",
        additional_satellite_slopes="none",
        scope=(
            "All-data exposed development hypotheses. "
            "No fresh discovery or independent validation claim."
        ),
        reference_usage="none before terminal seal",
        numerical_sources={
            str(p): digest(p)
            for p in [
                Path(__file__),
                ROOT / "src/leo/analysis/channel_group_calibration.py",
                ROOT / "src/leo/analysis/frozen_group_calibration.py",
            ]
        },
    )
    write(directory / "protocol.json", protocol)
    for path, sha in protocol["numerical_sources"].items():
        source_file = Path(path)
        snapshot = directory / "source-snapshot" / source_file.name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(source_file.read_bytes())
        if digest(snapshot) != sha:
            raise ValueError("Numerical source snapshot differs from declared trial")
    results = {}
    for view in ("low", "high", "all"):
        observations = prepared[view].observations
        base = Hard60Objective(observations, shared_bank, prior, HARD60_SCORE)
        clock = JointClockObjective(base, nodes, np.zeros((2, len(nodes))), 4)
        model = GroupCalibrationObjective(
            clock,
            observations.channel >= 5,
            group_drift_sigma_hz_s=2 if group_drift else None,
            group_clock=group_clock,
        )
        # Project the two functional calibrations into the new common model.
        low = correction(hypotheses["low"], observations)
        high = correction(hypotheses["high"], observations)
        target = np.where(observations.channel >= 5, high, low)
        projection = project_calibration_seed(model, target)
        coefficients = projection["coefficients"]
        projection_rms = projection["rms_hz"]
        starts = {}
        for seed_name in ("low", "high", "all"):
            scientific = hypotheses[seed_name]
            shifts = {
                number: shift
                for number, shift in zip(scientific["numbers"], scientific["shifts"], strict=True)
            }
            # Retain independently inferred timings for candidates absent in this start.
            for other in ("low", "high", "all"):
                for number, shift in zip(
                    hypotheses[other]["numbers"], hypotheses[other]["shifts"], strict=True
                ):
                    shifts.setdefault(number, shift)
            values = np.array([shifts[n] for n in numbers])
            values -= values.mean() - np.clip(values.mean(), -9.9, 9.9)
            values *= min(1.0, 19.9 / max(19.9, float(abs(values).max())))
            vector = np.r_[
                scientific["vector"][:2],
                coefficients[:5],
                values.mean(),
                model.basis.T @ (values - values.mean()),
            ]
            nuisance = coefficients[5:]
            attempts = {}
            for arm in ("fitted-c", "zero-c"):
                try:
                    fit = fit_group_calibration(
                        model,
                        vector,
                        nuisance,
                        arm=arm,
                        seconds=45,
                        iterations=600,
                        local_center=vector[:2],
                        local_radius_km=25,
                    )
                    freeze_group_calibration(model, fit)
                    attempts[arm] = fit
                except (ValueError, TimeoutError) as error:
                    attempts[arm] = dict(converged=False, reason=f"{type(error).__name__}: {error}")
            starts[seed_name] = attempts
            write(directory / f"{view}-attempts.json", json_value(starts))
        selected = {}
        for arm in ("fitted-c", "zero-c"):
            eligible = [(name, row[arm]) for name, row in starts.items() if row[arm]["converged"]]
            if eligible:
                name, fit = min(eligible, key=lambda pair: (pair[1]["objective"], pair[0]))
                selected[arm] = dict(start=name, fit=fit)
            else:
                selected[arm] = dict(state="unavailable", reason="No stationary common-model start")
        results[view] = dict(
            windows=len(observations.window_ids),
            projection_rms_hz=projection_rms,
            projection_active_bounds=projection["active_bounds"],
            attempts=starts,
            selected=selected,
        )
    for path, sha in protocol["numerical_sources"].items():
        if digest(Path(path)) != sha:
            raise ValueError("Frozen trial source changed during execution")
    write(
        directory / "terminal.json",
        json_value(
            dict(
                protocol_sha256=digest(directory / "protocol.json"),
                results=results,
                elapsed_s=time.monotonic() - begun,
                reference_usage="none",
            )
        ),
    )
    print(
        json.dumps(
            {
                name: {
                    arm: value.get("start", value.get("state"))
                    for arm, value in row["selected"].items()
                }
                for name, row in results.items()
            }
        ),
        flush=True,
    )


def json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_value(v) for v in value]
    return value


def evaluate(session, *, group_drift=False, group_clock=False, legacy=False):
    variant = "hypothesis-carry-v1" if legacy else variant_name(group_drift, group_clock)
    directory = OUTPUT / "local" / variant / session
    terminal = json.loads((directory / "terminal.json").read_bytes())
    protocol = json.loads((directory / "protocol.json").read_bytes())
    docs, _ = documents(session)
    reference = (docs["all"]["reference_latitude_deg"], docs["all"]["reference_longitude_deg"])
    prior = RegionalPrior(**protocol["prior"])
    summary = {}
    for name, row in terminal["results"].items():
        summary[name] = {}
        for arm, selected in row["selected"].items():
            if "fit" not in selected:
                summary[name][arm] = selected
                continue
            fit = selected["fit"]
            point = coordinates(prior, fit["vector"][:2])
            lat, lon, a, b = np.radians([*point, *reference])
            h = np.sin((lat - a) / 2) ** 2 + np.cos(lat) * np.cos(a) * np.sin((lon - b) / 2) ** 2
            summary[name][arm] = dict(
                start=selected["start"],
                error_m=float(2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))),
                posterior_rms_hz=fit["posterior_rms_hz"],
                signal_windows=fit["signal_windows"],
            )
    write(
        directory / "evaluation.json",
        dict(
            terminal_sha256=digest(directory / "terminal.json"),
            reference_usage="Only after terminal seal",
            summary=summary,
        ),
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("execute", "evaluate"))
    parser.add_argument("session_id")
    parser.add_argument("--group-drift", action="store_true")
    parser.add_argument("--group-clock", action="store_true")
    parser.add_argument("--legacy", action="store_true", help="Read the first exploratory receipt")
    args = parser.parse_args()
    if args.command == "execute":
        execute(args.session_id, group_drift=args.group_drift, group_clock=args.group_clock)
    else:
        evaluate(
            args.session_id,
            group_drift=args.group_drift,
            group_clock=args.group_clock,
            legacy=args.legacy,
        )
