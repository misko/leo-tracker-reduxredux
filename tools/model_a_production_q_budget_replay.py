"""Two q-only v2 calls from a frozen v1 production attempt; no source fitting."""

import argparse
import importlib.util
import json
import signal
import time
from pathlib import Path

import numpy as np

from leo.analysis import _regional_orbits
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
from leo.analysis.shared_scan_model import (
    MODEL_VERSION,
    SharedScanObjective,
    audit_endpoint,
    bounded_shared_fit,
    donor_state,
)
from leo.application.channel_group_refinement import objective
from leo.application.shared_fast_position import plain, prepare_views
from leo.cli.shared_fast_position import WholeDeadline, load_input, persist
from leo.contracts.digests import sha256_digest
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def read(path):
    return json.loads(Path(path).read_text())


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha256_digest(path.read_bytes()))


def verify_parent(parent):
    parent = Path(parent).resolve()
    launch, terminal = (read(parent / n) for n in ("launch.json", "terminal.json"))
    if (
        launch["model_version"] != "shared-scan-q-v1"
        or terminal["model_version"] != "shared-scan-q-v1"
        or terminal["state"] not in {"complete", "unavailable"}
        or launch["input_sha256"] != terminal["input_sha256"]
        or terminal["unfinished_stages"]
        or terminal["reference_usage"] != "none"
    ):
        raise ValueError("Complete frozen v1 production outcome without reference required")
    paths = sorted((parent / "stages").glob("*.json"))
    actual = [binding(p) for p in paths]
    if actual != terminal["stage_receipts"]:
        raise ValueError("Original exact stage bytes/inventory changed")
    if binding(launch["input_path"])["sha256"] != launch["input_sha256"]:
        raise ValueError("Original public input changed")
    selected = read(parent / "stages/source-selection.json")
    prescreen = selected["A_prescreen"]
    if (
        selected["A"]
        != min(prescreen, key=lambda r: (r["J"], int(r["source"].split("-")[1])))["source"]
    ):
        raise ValueError("Original A training prescreen differs")
    eligible = []
    for index in range(6):
        path = parent / f"stages/B-{index}.json"
        if path.exists():
            row = read(path)["result"]
            if row.get("audit", {}).get("accepted"):
                eligible.append((row["fit"]["objective"], index))
    if not eligible or selected["B_index"] != min(eligible)[1]:
        raise ValueError("Original B training source differs")
    return launch, terminal, selected, actual


def reconstruct_sources(prepared, bank, prior, nodes, selected, stage_reader):
    """Same production raw/centered functions, exact saved complete sources and disks."""
    joint = objective(prepared["all"], bank, prior, nodes)
    a_name = selected["A"]
    a_rows = {
        stage: stage_reader(f"{a_name}-{stage}")["result"] for stage in ("low", "high", "final")
    }
    if not all(r["audit"]["accepted"] for r in a_rows.values()):
        raise ValueError("Original A low/high/final source must all be strict")
    high, final = (a_rows[k]["fit"] for k in ("high", "final"))
    shift = SequentialShift(tuple(high["group_receivers"]), high["group_offsets_hz"])
    raw = fixed_shift_objective(joint.base, shift)
    a = dict(
        name=a_name,
        model=SharedScanObjective(raw, shift),
        shift=shift,
        vector=np.asarray(final["vector"]),
        nuisance=np.asarray(final["nuisance"]),
        options=a_rows["final"]["options"],
    )
    b_row = stage_reader(f"B-{selected['B_index']}")["result"]
    if not b_row["audit"]["accepted"]:
        raise ValueError("Original joint B source must be strict")
    raw, shift, v, n, error = donor_state(joint, b_row["fit"])
    b = dict(
        name="B-all",
        model=SharedScanObjective(raw, shift),
        shift=shift,
        vector=v,
        nuisance=n,
        options=b_row["options"],
        donor_correction_error_hz=error,
    )
    for row in (a, b):
        row["nuisance"] = np.r_[row["nuisance"], np.zeros(row["model"].observation_parameter_count)]
        if row["options"]["fixed_position"] or row["options"]["local_radius_km"] != 25:
            raise ValueError("Original free25km source domain required")
    return [a, b]


def run(parent, output, oracle_source, oracle_sha256, *, tle_root=Path("/var/lib/leo/tle")):
    parent, output, oracle_source = (Path(x).resolve() for x in (parent, output, oracle_source))
    if output.exists() or output.is_relative_to(parent) or parent.is_relative_to(output):
        raise ValueError("Fresh separate replay namespace required")
    if binding(oracle_source)["sha256"] != oracle_sha256:
        raise ValueError("Pinned immutable v1 mathematical oracle required")
    launch, original, selected, pins = verify_parent(parent)
    roots = [Path(__file__).resolve(), Path(_regional_orbits.__file__).resolve(), oracle_source]
    for module in (
        "leo.analysis.shared_scan_model",
        "leo.application.shared_fast_position",
        "leo.cli.shared_fast_position",
    ):
        roots.append(Path(importlib.import_module(module).__file__).resolve())
    protocol = dict(
        model_version=MODEL_VERSION,
        parent=str(parent),
        parent_launch=binding(parent / "launch.json"),
        parent_terminal=binding(parent / "terminal.json"),
        original_stage_files=pins,
        source_files=[binding(p) for p in roots],
        maximum_optimizer_calls=2,
        qualification_objectives=6,
        fit_solver_seconds=60,
        fit_total_seconds=65,
        actual_objectives_per_fit=5000,
        iterations=600,
        whole_seconds=360,
        source_fits=0,
        discovery_calls=0,
        reference_usage="none",
        held_usage="none",
    )
    persist(output / "protocol.json", protocol)
    persist(output / "launch.json", dict(protocol=binding(output / "protocol.json")))
    begun = time.monotonic()
    previous_handler, previous_timer = (
        signal.getsignal(signal.SIGALRM),
        signal.getitimer(signal.ITIMER_REAL),
    )

    def stop(*_):
        raise WholeDeadline("Bounded q-only replay deadline")

    signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, 360)
    rows, result = [], dict(state="failed", reference_usage="none", held_usage="none")
    try:
        prepared, nodes = prepare_views(load_input(read(launch["input_path"])))
        prior = RegionalPrior(**original["provenance"]["prior"])
        if (
            prepared["all"].evidence_sha256 != original["provenance"]["evidence_sha256"]
            or nodes.tolist() != original["provenance"]["clock_nodes_s"]
        ):
            raise ValueError("Original prepared observations/frame/clock nodes differ")
        archive = TleArchiveReader(tle_root)
        snapshots = [
            s
            for s in archive.list_snapshots()
            if s.digest == original["provenance"]["tle_sha256"]
            and s.collected_utc_ns == original["provenance"]["tle_collected_utc_ns"]
        ]
        if len(snapshots) != 1:
            raise ValueError("Exact original causal TLE snapshot required")
        snapshot = snapshots[0]
        if snapshot.collected_utc_ns >= prepared["all"].start_utc_ns - 505_000_000_000:
            raise ValueError("Original causal TLE guard differs")
        payload = archive.read(snapshot)
        if sha256_digest(payload.encode()) != original["provenance"]["tle_payload_sha256"]:
            raise ValueError("Original TLE payload differs")
        filtered, _ = exclude_labelled_starlink_debris(payload)
        catalogue = parse_element_sets(filtered)
        indices = np.array(
            [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")],
            int,
        )
        full_bank, _ = build_regional_bank(
            catalogue,
            indices,
            prepared["all"].start_utc_ns,
            prepared["all"].observations,
            prior,
            maximum_seconds=180,
        )
        union = read(parent / "stages/candidate-union.json")
        if full_bank.numbers.tolist() != original["provenance"]["full_candidate_numbers"]:
            raise ValueError("Original propagated full bank inventory differs")
        bank = full_bank.select(union["indices"])
        if bank.numbers.tolist() != union["numbers"]:
            raise ValueError("Original union numbers/order differ")
        sources = reconstruct_sources(
            prepared,
            bank,
            prior,
            nodes,
            selected,
            lambda n: read(parent / "stages" / (n + ".json")),
        )
        spec = importlib.util.spec_from_file_location(
            "frozen_r1_shared_model_oracle", oracle_source
        )
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        qualifications = []
        for row in sources:
            model, v, n = (row[k] for k in ("model", "vector", "nuisance"))
            old = oracle.SharedScanObjective(model.original, row["shift"])
            a, b = model.evaluate_joint(v, n), old.evaluate_joint(v, n)
            errors = [
                float(np.max(abs(np.asarray(a[i]) - np.asarray(b[i])), initial=0)) for i in range(3)
            ]
            if max(errors) > 1e-9:
                raise ValueError("v2 initial objective/complete gradients differ from frozen v1")
            historical = read(parent / "stages" / f"shared-all-{row['name']}.json")["result"]
            replay = audit_endpoint(model, historical["fit"], historical["options"])
            if (
                abs(replay["objective"] - historical["audit"]["objective"]) > 1e-7
                or abs(replay["stationarity"] - historical["audit"]["stationarity"]) > 1e-7
            ):
                raise ValueError("Frozen original q endpoint no longer replays")
            if row["name"] == selected["A"]:
                expected = next(
                    r["J"] for r in selected["A_prescreen"] if r["source"] == row["name"]
                )
                if abs(a[0] - expected) > 1e-7:
                    raise ValueError("Original exact A zero-q initializer differs")
            qualifications.append(
                dict(
                    source=row["name"],
                    initial_J=a[0],
                    oracle_errors=errors,
                    old_endpoint_replay=replay,
                    seed=dict(vector=v, nuisance=n),
                    original_options=row["options"],
                )
            )
        persist(
            output / "qualification.json",
            dict(
                rows=plain(qualifications),
                objective_calls=6,
                optimizer_calls=0,
                reference_usage="none",
            ),
        )
        for row in sources:
            name = row["name"]
            persist(
                output / f"{name}-launch.json",
                dict(
                    source=name,
                    seed=plain(dict(vector=row["vector"], nuisance=row["nuisance"])),
                    options=row["options"],
                ),
            )
            fitted = bounded_shared_fit(
                row["model"],
                row["vector"],
                row["nuisance"],
                local_center=row["options"]["local_center"],
                local_radius_km=row["options"]["local_radius_km"],
            )
            persist(output / f"{name}-result.json", fitted)
            rows.append(dict(source=name, **fitted))
        verify_parent(parent)
        if any(binding(p["path"]) != p for p in protocol["source_files"]):
            raise ValueError("Frozen replay/math source changed")
        eligible = [r for r in rows if r["audit"]["accepted"]]
        result = dict(
            state="complete",
            model_version=MODEL_VERSION,
            rows=plain(rows),
            selection=None
            if not eligible
            else plain(min(eligible, key=lambda r: (r["fit"]["objective"], r["source"]))),
            optimizer_calls=len(rows),
            objective_calls=sum(r["actual_objective_calls"] for r in rows),
            qualification_objectives=6,
            source_fits=0,
            reference_usage="none",
            held_usage="none",
        )
        persist(output / "terminal.json", result)
        persist(
            output / "seal.json", dict(files=[binding(p) for p in sorted(output.glob("*.json"))])
        )
    except BaseException as error:
        result.update(state="failed", reason=str(error), error_type=type(error).__name__)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)
        persist(
            output / "termination.json",
            dict(
                state=result["state"],
                elapsed_seconds=time.monotonic() - begun,
                optimizer_calls_returned=len(rows),
                reference_usage="none",
            ),
        )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--oracle-source", required=True, type=Path)
    p.add_argument("--oracle-sha256", required=True)
    p.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = p.parse_args()
    outcome = run(
        args.parent, args.output, args.oracle_source, args.oracle_sha256, tle_root=args.tle_root
    )
    print(
        json.dumps(
            dict(
                state=outcome["state"],
                accepted=sum(r["audit"]["accepted"] for r in outcome["rows"]),
                objective_calls=outcome["objective_calls"],
            )
        )
    )
