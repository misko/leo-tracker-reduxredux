"""Use one physical receiver while retaining the recorded localization geometry."""

import json
from hashlib import sha256

import numpy as np

POLICY = "single-physical-receiver/v1"


def analyze_native(native, samples, receiver_id=0, *, include_timings=False):
    """Run a one-receiver context on its recorded lane without changing sample time."""
    if native.receiver_count != 1:
        raise ValueError("a single-receiver native context is required")
    if receiver_id not in (0, 1) or samples.ndim != 3 or samples.shape[1:] != (2, 2):
        raise ValueError("expected two recorded CI16 lanes and physical receiver 0 or 1")
    selected = np.ascontiguousarray(samples[:, receiver_id : receiver_id + 1, :])
    result = native.analyze(selected, include_timings=include_timings)
    (row,) = result["rows"]
    if row["receiver_id"] != 0:
        raise ValueError("unexpected logical receiver from the native single-receiver context")
    return dict(result, rows=[dict(row, receiver_id=receiver_id)])


def project_document(document, receiver_id=0):
    """Keep one lane's archived factors and empty the other lane's existing probes."""
    if receiver_id not in (0, 1):
        raise ValueError("physical receiver must be 0 or 1")
    source, provenance = document["source"], document["provenance"]
    probes = []
    for probe in source["probes"]:
        if probe["receiver_id"] not in (0, 1):
            raise ValueError("expected the two recorded physical receiver IDs")
        probes.append(probe if probe["receiver_id"] == receiver_id else dict(probe, candidates=[]))

    payload = json.dumps(
        [POLICY, receiver_id, source["analysis_manifest_sha256"], probes],
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    analysis_sha = "sha256:" + sha256(payload).hexdigest()
    return dict(
        document,
        source=dict(source, analysis_manifest_sha256=analysis_sha, probes=probes),
        provenance=dict(provenance, run_id="replay-" + analysis_sha[7:39], scope=POLICY),
    )
