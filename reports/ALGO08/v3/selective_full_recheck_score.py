"""Review the sealed recheck only after both candidate outputs are immutable."""

import gzip
from hashlib import sha256
import json
from pathlib import Path

from selective_full_recheck import CASES, HERE, inputs, lane, read


RECEIPT = HERE / "measurements/selective-full-recheck-receipt.json.gz"
PIN = "ac9c418d24420d69cb3ea4149a121e5e42a02b54e32a30ad477a573da5498dcf"
NAMED = {
    "DS30-0163": ("algo08-v2-3c930ea608338c1f278e7879f165e57b", "0a517f46e394b59649030dd836717c8bf18cb075eae8fcc48a1ad9c68cc946ce"),
    "DS30-0008": ("algo08-v2-520337201d261a86a47ce34b124019f2", "8ef7f1804231afc9fac00877b42b46a7578249a0426647f4d30629af1e380d0b"),
}


def ratio(common, measured, named):
    return dict(shared=common, candidate=measured, named=named, precision=common / measured if measured else None,
                recall=common / named if named else None)


def stats(named, candidate, digest):
    n, c = [{key for key, factors in view.items() if factors} for view in (named, candidate)]
    nids, cids = [{(key, digest(factor)) for key, factors in view.items() for factor in factors}
                  for view in (named, candidate)]
    return dict(lane=ratio(len(n & c), len(c), len(n)), factor=ratio(len(nids & cids), len(cids), len(nids)))


def score():
    from leo.contracts.digests import canonical_digest

    blob = RECEIPT.read_bytes()
    if sha256(blob).hexdigest() != PIN:
        raise ValueError("The two unopened candidate predictions changed")
    frozen = json.loads(gzip.decompress(blob))
    output = {}
    for case, (run, _, _, _, _, branch) in CASES.items():
        docs = frozen["cases"][case]
        after = docs["detections.json"]["document"]
        receipt = docs["receipt.json"]["document"]
        clock = docs["clock.json"]["document"]["clock"]
        before, _, _, scope, _, _, _ = inputs(case)
        id_, pin = NAMED[case]
        named = read(run / branch / "fast-scan-automatic-work" / id_ / "detections.json", pin)
        if (clock["exit_code"] or receipt["position_solvers"] or receipt["original_backing_reads"] or
                receipt["output_sha256"] != canonical_digest(after) or receipt["legacy_candidate_sha256"] != canonical_digest(before)
                or any(packet["source"]["input_manifest_sha256"] != scope["digest"] for packet in (before, after, named))):
            raise ValueError("The compared complete prefixes must be qualified independently")
        for packet in (before, after):
            if (any(packet[k] != named[k] for k in ("clock_anchor", "delivery_clocks", "last_sample_counter"))
                    or packet["provenance"]["excluded_windows"] != named["provenance"]["excluded_windows"]
                    or packet["source"]["raw_recording_authority_digest"] != named["source"]["raw_recording_authority_digest"]
                    or [{k: v for k, v in row.items() if k != "candidates"} for row in packet["source"]["probes"]]
                        != [{k: v for k, v in row.items() if k != "candidates"} for row in named["source"]["probes"]]):
                raise ValueError("Exactly the original typed lane metadata and issued exclusions are required")
        reference, base, candidate = ({lane(row): row["candidates"] for row in p["source"]["probes"]}
                                      for p in (named, before, after))
        selected = {tuple(row["lane"]) for row in receipt["decisions"] if row["selected"]}
        changed = {key for key in base if canonical_digest(base[key]) != canonical_digest(candidate[key])}
        identical = {key for key in base if base[key] and canonical_digest(base[key]) == canonical_digest(reference[key])}
        losses = sorted(identical & changed)
        recovered = sorted(key for key in changed if reference[key] and canonical_digest(candidate[key]) == canonical_digest(reference[key]))
        output[case] = dict(named_sha256=pin, before=stats(reference, base, canonical_digest),
                            after=stats(reference, candidate, canonical_digest), selected=sorted(selected),
                            selected_mismatched_before=sum(canonical_digest(base[k]) != canonical_digest(reference[k]) for k in selected),
                            changed=sorted(changed), exact_recoveries=recovered, prior_exact_nonempty_lanes=len(identical),
                            previously_exact_lanes_lost=losses, outside_shortlist_changes=sorted(changed - selected),
                            subject_route=receipt["held"]["choice"], original_lanes=len(base),
                            measurement_scope="incremental detached replay after exact saved candidate acquisition")
    return dict(cases=output, independently_sealed_candidates_sha256=PIN,
                scope="same original receiver opportunities with offline named-policy comparison")


if __name__ == "__main__":
    print(json.dumps(score(), sort_keys=True, indent=2, allow_nan=False))
