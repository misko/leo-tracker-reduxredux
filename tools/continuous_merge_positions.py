"""Matched full B7 replays from the merge census; reference-free until evaluation."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from continuous_merge_study import LOCAL, REPORT, plain, sha, write

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.application.hard60_b7 import B7_POLICY, run_b7
from leo.application.regional_position_inputs import PreparedPositionWindows
from leo.application.regional_position_runner import RegionalSliceExpired
from leo.cli.regional_position import configuration
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

VARIANTS = ("baseline", "replace-guard", "append-guard", "replace-no-guard")


def load_prepared(path):
    d = json.loads(path.read_bytes())
    observations = d["observations"]
    obs = PositionObservations(
        **{k: tuple(v) if k == "window_ids" else np.asarray(v) for k, v in observations.items()}
    )
    return PreparedPositionWindows(
        obs,
        tuple(d["candidate_ids"]),
        tuple(tuple(r) for r in d["bootstrap_tracks"]),
        d["start_utc_ns"],
        d["evidence_sha256"],
        d["trajectory_configuration_sha256"],
    )


def freeze(case):
    destination = case / "positions"
    if (destination / "experiment.json").exists():
        raise ValueError("position protocol already exists")
    census = json.loads((case / "census.json").read_bytes())
    if census["status"] != "complete":
        raise ValueError("prepared input is unavailable")
    prepared = load_prepared(case / "baseline.json")
    for variant in VARIANTS[1:]:
        other = load_prepared(case / (variant + ".json"))
        assert other.candidate_ids == prepared.candidate_ids
        for field in (
            "window_ids",
            "times_s",
            "measured_hz",
            "rf_hz",
            "receiver",
            "channel",
            "margin",
        ):
            assert np.array_equal(
                getattr(prepared.observations, field), getattr(other.observations, field)
            )
    prior = RegionalPrior()
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    payload, exclusions = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    )
    begun = time.monotonic()
    bank, receipt = build_regional_bank(
        catalogue,
        indices,
        prepared.start_utc_ns,
        prepared.observations,
        prior,
        maximum_seconds=180,
    )
    destination.mkdir(parents=True, exist_ok=True)
    np.savez(
        destination / "bank.npz",
        numbers=bank.numbers,
        nodes_s=bank.nodes_s,
        position_km=bank.position_km,
        velocity_km_s=bank.velocity_km_s,
    )
    write(
        destination / "experiment.json",
        {
            "session_id": census["member"]["session_id"],
            "dataset": census["member"]["dataset"],
            "role": census["member"]["role"],
            "study_protocol_sha256": sha(REPORT / "protocol.json"),
            "prepared_bindings": {v: sha(case / (v + ".json")) for v in VARIANTS},
            "bank_sha256": sha(destination / "bank.npz"),
            "bank_receipt": receipt,
            "snapshot_sha256": snapshot.digest,
            "catalogue_exclusions": exclusions,
            "configuration": configuration(),
            "configuration_sha256": canonical_digest(configuration()),
            "b7_policy": B7_POLICY,
            "tool_sha256": sha(Path(__file__)),
            "scope": (
                "Full default 400-point B7 search and original recovery/tail policy; "
                "matched original observations, initial candidate bank, priors and search budgets. "
                "c arms share fitted-c upstream conditioning and final bank within each variant. "
                "Final banks may differ between merge conditions as part of the intervention."
            ),
            "reference_usage": "none",
            "bank_preparation_seconds": time.monotonic() - begun,
        },
    )
    print(
        json.dumps({"bank_candidates": len(bank.numbers), "elapsed_s": time.monotonic() - begun}),
        flush=True,
    )


def execute(case, variant, maximum_seconds):
    destination = case / "positions"
    p = json.loads((destination / "experiment.json").read_bytes())
    if p["tool_sha256"] != sha(Path(__file__)):
        raise ValueError("position tool changed")
    if p["study_protocol_sha256"] != sha(REPORT / "protocol.json"):
        raise ValueError("merge study protocol changed")
    if p["configuration_sha256"] != canonical_digest(configuration()):
        raise ValueError("pipeline implementation/configuration changed")
    if p["bank_sha256"] != sha(destination / "bank.npz"):
        raise ValueError("bank changed")
    if p["prepared_bindings"][variant] != sha(case / (variant + ".json")):
        raise ValueError("prepared merge input changed")
    output = destination / variant
    if (output / "terminal.json").exists():
        print("already terminal")
        return
    prepared = load_prepared(case / (variant + ".json"))
    with np.load(destination / "bank.npz") as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    binding = canonical_digest({"experiment": p, "variant": variant})
    store = RegionalCheckpointStore(output, p["session_id"], binding)
    begun = time.monotonic()
    status, result, reason = "yielded", None, None
    with store.writer():
        try:
            result = run_b7(
                prepared.observations,
                bank,
                RegionalPrior(),
                prepared.bootstrap_tracks,
                store,
                maximum_seconds=maximum_seconds,
            )
            status = "complete"
        except RegionalSliceExpired as error:
            reason = str(error)
        except (ValueError, TimeoutError) as error:
            status, reason = "failed", f"{type(error).__name__}: {error}"
    write(
        output / "last-slice.json",
        {
            "status": status,
            "reason": reason,
            "elapsed_s": time.monotonic() - begun,
            "binding": binding,
        },
    )
    if status != "yielded":
        write(
            output / "terminal.json",
            {
                "status": status,
                "reason": reason,
                "result": plain(result),
                "reference_usage": "none",
                "binding": binding,
            },
        )
    print(
        json.dumps(
            {
                "variant": variant,
                "status": status,
                "reason": reason,
                "elapsed_s": time.monotonic() - begun,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "execute"))
    parser.add_argument("dataset", choices=("DS20", "DS16"))
    parser.add_argument("session_id")
    parser.add_argument("--variant", choices=VARIANTS, default="baseline")
    parser.add_argument("--maximum-seconds", type=float, default=420)
    args = parser.parse_args()
    case = LOCAL / args.dataset / args.session_id
    if args.command == "freeze":
        freeze(case)
    else:
        execute(case, args.variant, args.maximum_seconds)
