"""Authenticate complete fractional-runtime native input and blind request bindings."""

import json
from hashlib import sha256
from pathlib import Path

from .full_v5_check import NATIVE_LIBRARY, _sha

IDENTITY = "native-short-window-glrt/fractional-epoch"
ENCODER = json.JSONEncoder(
    allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")
)


def canonical_sha(value, *, newline=False):
    """Hash the same serialization as recording_to_v5 without a second full recording buffer."""
    result = sha256()
    for piece in ENCODER.iterencode(value):
        result.update(piece.encode())
    if newline:
        result.update(b"\n")
    return result.hexdigest()


def verify_native(document, expected_control_sha256, expected_library_sha256):
    """Validate actual lineage and challenge all complete native bytes against the stock replay."""
    source, provenance = document["source"], document["provenance"]
    candidate_library = "sha256:" + expected_library_sha256.removeprefix("sha256:")
    control_library = "sha256:" + _sha(NATIVE_LIBRARY)
    if document["schema_version"] != 2 or provenance["detector_sha256"] != candidate_library:
        raise ValueError("fresh native document is not bound to the measured fractional library")
    factor_input = [
        source["input_manifest_sha256"],
        source["probes"],
        provenance["excluded_windows"],
    ]
    analysis = "sha256:" + canonical_sha([IDENTITY, candidate_library, *factor_input])
    if (
        source["analysis_manifest_sha256"] != analysis
        or provenance["run_id"] != "replay-" + analysis[7:39]
    ):
        raise ValueError("fresh native manifest or run identity was changed")
    stock_analysis = "sha256:" + canonical_sha([IDENTITY, control_library, *factor_input])
    stock_view = dict(
        document,
        source=dict(source, analysis_manifest_sha256=stock_analysis),
        provenance=dict(
            provenance, detector_sha256=control_library, run_id="replay-" + stock_analysis[7:39]
        ),
    )
    normalized = canonical_sha(stock_view, newline=True)
    if normalized != expected_control_sha256.removeprefix("sha256:"):
        raise ValueError("complete ordinary bytes differ beyond the three detector lineage fields")
    return dict(
        control_native_sha256=normalized,
        candidate_detector_sha256=candidate_library,
        candidate_analysis_sha256=analysis,
        complete_native_science_exact=True,
        retained_probe_rows=len(source["probes"]),
        excluded_visits=len(provenance["excluded_windows"]),
    )


def verify_request(fresh, archived, *, native_path, native_sha256):
    """Check the truth-free v5 request apart from the freshly bound path and native identity."""
    job, parent = fresh["job"], archived["job"]
    actual = "sha256:" + native_sha256.removeprefix("sha256:")
    identity = job["identity"]
    if (
        job["native_input"] != dict(path=str(native_path), sha256=actual)
        or identity["input_sha256"] != actual
        or identity["run_id"] != "experiment-" + actual[7:39]
        or job["evaluation_reference"] is not None
    ):
        raise ValueError("fresh blind request lacks its actual complete native identity")
    normalized = dict(
        fresh,
        job=dict(
            job,
            output_root=parent["output_root"],
            native_input=parent["native_input"],
            identity=dict(
                identity,
                input_sha256=parent["identity"]["input_sha256"],
                run_id=parent["identity"]["run_id"],
            ),
        ),
    )
    if normalized != archived:
        raise ValueError("fresh request differs beyond paths and the new native-content identity")


def compare_lanes(fresh: Path, control: Path, *, expected_binary, control_binary):
    """Compare literal canonical records. Remove only measured stage clocks and binary lineage."""
    counts = dict(visits=0, segments=0, lanes=0)
    for lane in range(2):
        name = f"replayed-{lane}.jsonl"
        with (fresh / name).open("rb") as left, (control / name).open("rb") as right:
            for index, (a, b) in enumerate(zip(left, right, strict=True)):
                if a == b and b.startswith(b'{"clock_anchor":'):
                    counts["visits"] += 1
                    continue
                if a == b and json.loads(b) == {"kind": "worker", "worker": lane}:
                    counts["lanes"] += 1
                    continue
                trial, oracle = json.loads(a), json.loads(b)
                if trial["kind"] == oracle["kind"] == "segment":
                    for value, digest in ((trial, expected_binary), (oracle, control_binary)):
                        if value.pop("library_sha256") != "sha256:" + digest.removeprefix(
                            "sha256:"
                        ):
                            raise ValueError("raw lane segment does not bind the expected binary")
                        value.pop("detector_cpu_s")
                        value.pop("wall_s")
                    if trial == oracle:
                        counts["segments"] += 1
                        continue
                raise ValueError(f"native raw lane {lane} row {index} differs: {oracle['kind']}")
    return counts
