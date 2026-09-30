"""Exact-track archived orbit candidates, with explicit control-supported tiers."""

import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "local"


def candidate_tier(candidate):
    if (candidate.get("abstention_recommended", True)
            or not candidate.get("leading_candidate_persisted_on_heldout", False)
            or candidate.get("training_leader_heldout_rank") != 1
            or not candidate.get("leading_catalog_number")):
        return None
    nominal = candidate.get("nominal_heldout_negative_log_score")
    controls = [candidate.get(k) for k in (
        "radio_null_heldout_negative_log_score",
        "wrong_time_minus_500_heldout_negative_log_score",
        "wrong_time_plus_500_heldout_negative_log_score",
    )]
    supported = nominal is not None and all(c is not None and nominal < c for c in controls)
    return "control_supported_candidate" if supported else "heldout_candidate"


def bind_candidates(product):
    labels = defaultdict(list)
    for candidate in product.get("tle_candidates", []):
        tier = candidate_tier(candidate)
        if tier:
            for track in candidate["tracklet_ids"]:
                labels[track].append(dict(
                    norad_id=candidate["leading_catalog_number"], tier=tier,
                    physical_group=candidate["physical_group_id"], evidence=candidate,
                ))
    result = {}
    for track, choices in labels.items():
        ids = {c["norad_id"] for c in choices}
        if len(ids) != 1:
            result[track] = dict(tier="conflicting_candidates", norad_id=None, choices=choices)
        else:
            best = max(choices, key=lambda c: c["tier"] == "control_supported_candidate")
            result[track] = dict(best, choices=choices)
    return result


def main():
    from extend import sha, write

    rows, sources = [], {}
    for dataset, root in (
        ("DS9", BASE.parent / "2026_09_28_ds9_post_ds8"),
        ("DS10", BASE.parent / "2026_09_29_ds10_post_ds9/local"),
    ):
        manifest = root / "manifest.json"
        sources[str(manifest)] = sha(manifest)
        for member in json.loads(manifest.read_text())["captures"]:
            path = root / "analysis" / (member["session_id"] + ".json")
            assert sha(path) == member["analysis_evidence_sha256"]
            sources[str(path)] = sha(path)
            evidence = json.loads(path.read_text())
            product = evidence["tracking"]["product"]
            assert product["input_manifest_sha256"] == member["manifest_sha256"]
            assert (product["analysis_manifest_sha256"]
                    == evidence["glrt"]["metrics_manifest_sha256"])
            for track, label in bind_candidates(product).items():
                rows.append(dict(
                    dataset=dataset, session=member["session_id"], track_id=track,
                    source=str(path), source_sha256=sha(path),
                    observer_site=product["observer_site"],
                    capture_manifest=member["manifest_sha256"],
                    analysis_manifest=product["analysis_manifest_sha256"], **label,
                ))
    counts = Counter((r["dataset"], r["tier"]) for r in rows)
    write(OUT / "associations.json", dict(
        rows=rows, source_sha256=sources, method_sha256=sha(Path(__file__)),
        counts={str(k): v for k, v in counts.items()},
        limitation="Orbit candidates only, not decoded or independently verified identities. "
        "Control-supported means nominal held-out NLL beats all three stored controls. "
        "No minimum effect-size claim; grouped receiver tracks are not independent.",
    ))
    print(json.dumps({str(k): v for k, v in counts.items()}, indent=2))


if __name__ == "__main__":
    main()
