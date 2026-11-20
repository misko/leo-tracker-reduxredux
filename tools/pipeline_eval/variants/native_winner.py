"""Select one native fractional GLRT observation on each processed probe."""

import hashlib
import json

MINIMUM_MARGIN = 0.060
POLICY = "native-fractional-glrt-winner/v1"


def select_candidate(candidates, *, minimum_margin=MINIMUM_MARGIN):
    """Return a complete native candidate at the fixed margin, with rank as tie breaker."""
    return max(
        (c for c in candidates if c["fractional_margin"] >= minimum_margin),
        key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
        default=None,
    )


def apply_document(document):
    """Preserve recording/clock authority while rebinding derived experimental evidence."""
    source, provenance = document["source"], document["provenance"]
    probes = []
    for probe in source["probes"]:
        winner = select_candidate(probe["candidates"])
        probes.append(dict(probe, candidates=[] if winner is None else [winner]))

    identity = json.dumps(
        [POLICY, MINIMUM_MARGIN, source["analysis_manifest_sha256"], probes],
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    analysis_sha = "sha256:" + hashlib.sha256(identity).hexdigest()
    return dict(
        document,
        source=dict(source, analysis_manifest_sha256=analysis_sha, probes=probes),
        provenance=dict(provenance, run_id="replay-" + analysis_sha[7:39], scope=POLICY),
    )
