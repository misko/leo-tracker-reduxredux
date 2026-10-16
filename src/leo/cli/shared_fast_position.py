"""Versioned standalone shared-q inference for exported public TrackingInputs."""

import argparse
import json
import os
import signal
import time
from pathlib import Path

import numpy as np

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.shared_scan_model import MODEL_VERSION
from leo.application.regional_position_inputs import PositionInputUnavailable
from leo.application.shared_fast_position import POLICY, plain, prepare_views, run_shared_position
from leo.contracts.digests import sha256_digest
from leo.contracts.regional_position import RegionalPrior
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.operations.tle_archive import TleArchiveReader
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.sky.propagation import parse_element_sets


def persist(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(plain(value), stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


class Receipts:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, name):
        if not name or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:._-"
            for c in name
        ):
            raise ValueError("Invalid scientific stage identifier")
        return self.root / (name + ".json")

    def get(self, name):
        path = self.path(name)
        return json.loads(path.read_text()) if path.exists() else None

    def put(self, name, value):
        persist(self.path(name), value)


def load_input(document):
    """Same public export's timing reconstruction, without importing old tools."""
    source = dict(document.get("source", document))
    anchor = document.get("clock_anchor")
    clocks = document.get("delivery_clocks", [])
    if anchor is not None:
        if not clocks or anchor["sample_counter"] > min(
            (p["valid_start_counter"] for p in source["probes"]),
            default=anchor["sample_counter"],
        ):
            raise ValueError("UTC bracket does not cover tracking input")
        offsets = [c["realtime_ns"] - c["monotonic_ns"] for c in clocks]
        offsets.append(anchor["before"]["realtime_ns"] - anchor["before"]["monotonic_ns"])
        if max(offsets) - min(offsets) > 2_000_000_000:
            raise ValueError("Capture clock step exceeds association policy")
        timing = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
            session_id=source["session_id"],
            sample_rate_hz=source["sample_rate_hz"],
            session_start_device_sample_counter=anchor["sample_counter"],
            begin_before_realtime_ns=anchor["before"]["realtime_ns"],
            begin_before_monotonic_ns=anchor["before"]["monotonic_ns"],
            begin_after_realtime_ns=anchor["after"]["realtime_ns"],
            begin_after_monotonic_ns=anchor["after"]["monotonic_ns"],
            terminal_realtime_ns=clocks[-1]["realtime_ns"],
            terminal_monotonic_ns=clocks[-1]["monotonic_ns"],
        )
        source["timing"] = timing
        source["capture_start_utc_ns"] = timing.first_sample_estimate_utc_ns
        source["capture_end_utc_ns"] = timing.first_sample_estimate_utc_ns + round(
            (document["last_sample_counter"] - anchor["sample_counter"])
            * 1e9
            / source["sample_rate_hz"]
        )
    elif source.get("timing") is not None:
        source["timing"] = PersistentHopUtcTimingAuthorityV1.model_validate(source["timing"])
    source["probes"] = tuple(
        TrackingProbe(**dict(p, candidates=tuple(TrackingCandidate(**c) for c in p["candidates"])))
        for p in source["probes"]
    )
    return TrackingInput(**source)


class WholeDeadline(BaseException):
    """Whole process limit must not be caught as a recoverable stage failure."""


def run(input_path, output, *, maximum_seconds=1200.0, tle_root=Path("/var/lib/leo/tle")):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1200:
        raise ValueError("Whole shared-scan allowance must be in(0,1200]seconds")
    input_path, output = Path(input_path).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Attempt namespace exists; failed/shared work is never retried")
    if output == input_path or output in input_path.parents:
        raise ValueError("Output overlaps public input authority")
    payload = input_path.read_bytes()
    identity = dict(
        schema_version=1,
        kind="fast-scan.shared-position",
        model_version=MODEL_VERSION,
        input_sha256=sha256_digest(payload),
    )
    persist(
        output / "launch.json",
        dict(
            **identity, maximum_seconds=maximum_seconds, policy=POLICY, input_path=str(input_path)
        ),
    )
    begun = time.monotonic()
    result = dict(
        **identity,
        state="failed",
        position=None,
        selection=None,
        reference_usage="none",
        held_usage="none",
        fitted_c=True,
        source_generation_policy=POLICY["source_generation_policy"],
    )
    old_alarm, old_term = signal.getsignal(signal.SIGALRM), signal.getsignal(signal.SIGTERM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)

    def stop(signum, frame):
        raise WholeDeadline("Bounded shared-scan process terminated")

    signal.signal(signal.SIGALRM, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.setitimer(signal.ITIMER_REAL, maximum_seconds)
    try:
        source = load_input(json.loads(payload))
        result["session_id"] = source.session_id
        receipts = Receipts(output / "stages")
        receipts.put("preparation-launch", dict(input_sha256=identity["input_sha256"]))
        prepared, nodes = prepare_views(source)
        prior = RegionalPrior()
        provenance = dict(
            input_manifest_sha256=source.input_manifest_sha256,
            analysis_manifest_sha256=source.analysis_manifest_sha256,
            evidence_sha256=prepared["all"].evidence_sha256,
            prior=plain(vars(prior)),
            clock_nodes_s=nodes,
            preparation="all available qualified original GLRT windows; no held split",
        )
        receipts.put("preparation", provenance)
        archive = TleArchiveReader(tle_root)
        cutoff = prepared["all"].start_utc_ns - 505_000_000_000
        snapshot = archive.select_latest_before(cutoff)
        if snapshot.collected_utc_ns >= cutoff:
            raise ValueError("Strictly causal TLE snapshot required")
        tle_payload = archive.read(snapshot)
        filtered, exclusions = exclude_labelled_starlink_debris(tle_payload)
        catalogue = parse_element_sets(filtered)
        indices = np.asarray(
            [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")],
            int,
        )
        receipts.put("bank-launch", dict(tle_sha256=snapshot.digest))
        bank, bank_receipt = build_regional_bank(
            catalogue,
            indices,
            prepared["all"].start_utc_ns,
            prepared["all"].observations,
            prior,
            maximum_seconds=180,
        )
        provenance.update(
            tle_sha256=snapshot.digest,
            tle_collected_utc_ns=snapshot.collected_utc_ns,
            tle_payload_sha256=sha256_digest(tle_payload.encode("utf-8")),
            catalogue_exclusions=[entry.model_dump(mode="json") for entry in exclusions],
            full_candidate_numbers=bank.numbers.tolist(),
        )
        receipts.put("bank", dict(receipt=plain(vars(bank_receipt)), provenance=provenance))
        result["provenance"] = plain(provenance)
        remaining = maximum_seconds - (time.monotonic() - begun)
        inferred = run_shared_position(
            source, prepared, bank, prior, nodes, receipts, maximum_seconds=remaining
        )
        result.update(**inferred, state="complete")
        result["provenance"]["candidate_numbers"] = inferred["candidate_numbers"]
        if sha256_digest(input_path.read_bytes()) != identity["input_sha256"]:
            raise ValueError("Public input changed during inference")
    except PositionInputUnavailable as error:
        result.update(state="unavailable", position=None, selection=None, reason=str(error))
    except BaseException as error:
        result.update(
            state="failed",
            position=None,
            selection=None,
            reason=str(error),
            error_type=type(error).__name__,
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, *old_timer)
        signal.signal(signal.SIGALRM, old_alarm)
        signal.signal(signal.SIGTERM, old_term)
        result["elapsed_seconds"] = time.monotonic() - begun
        stage_paths = sorted((output / "stages").glob("*.json"))
        result["stage_receipts"] = [
            dict(path=str(p), sha256=sha256_digest(p.read_bytes())) for p in stage_paths
        ]
        result["unfinished_stages"] = [
            p.stem.removesuffix("-launch")
            for p in stage_paths
            if p.stem.endswith("-launch")
            and not p.with_name(p.stem.removesuffix("-launch") + ".json").exists()
        ]
        result["cost_exact"] = not result["unfinished_stages"]
        persist(output / "terminal.json", result)
    return plain(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--maximum-seconds", type=float, default=1200.0)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args(argv)
    result = run(
        args.input, args.output, maximum_seconds=args.maximum_seconds, tle_root=args.tle_root
    )
    print(
        json.dumps(
            dict(
                state=result["state"],
                model_version=MODEL_VERSION,
                session_id=result.get("session_id"),
                output=str(args.output),
                elapsed_seconds=result["elapsed_seconds"],
            )
        )
    )
    return 0 if result["state"] in {"complete", "unavailable"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
