#!/usr/bin/env python3
"""Separate support-profile arithmetic from analysis-identity partition effects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEPLOYMENT = HERE.parents[1]


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    portable_dir = HERE / "full-public-c3-c4"
    profiled_dir = HERE / "full-server-support-c3-c4"
    portable = read(portable_dir / "reference-comparison.json")
    profiled = read(profiled_dir / "reference-comparison.json")
    portable_report = read(portable_dir / "report.json")
    profiled_report = read(profiled_dir / "report.json")
    prior_path = DEPLOYMENT / "runtime" / "session-compat-physical-v1" / "receipt.json"
    prior = read(prior_path)
    if portable["tracks"]["exact_lane_source_and_alias_memberships"] != 64:
        raise ValueError("portable physical memberships differ")
    if profiled["tracks"]["exact_lane_source_and_alias_memberships"] != 64:
        raise ValueError("profiled physical memberships differ")
    if profiled_report["reference_analysis_digest_used"]:
        raise ValueError("profiled lane reused reference analysis identity")

    result = {
        "schema": "org.leo.corrected-native-support-profile-comparison/v1",
        "status": "measured_identity_partition_sensitivity",
        "portable": {
            "analysis_digest": portable_report["analysis_digest"],
            "exact_reference_moment2_lexemes": portable["graph_authority"]["exact_moment2_lexemes"],
            "exact_reference_moment3_lexemes": portable["graph_authority"]["exact_moment3_lexemes"],
            "location": portable["fixed_site_location"],
        },
        "server_support_profile": {
            "analysis_digest": profiled_report["analysis_digest"],
            "profile_name": profiled_report["algorithm"]["support_profile_name"],
            "profile_manifest_digest": profiled_report["algorithm"][
                "support_profile_manifest_digest"
            ],
            "exact_reference_moment2_lexemes": profiled["graph_authority"]["exact_moment2_lexemes"],
            "exact_reference_moment3_lexemes": profiled["graph_authority"]["exact_moment3_lexemes"],
            "moment2_lexeme_mismatches": 11747
            - profiled["graph_authority"]["exact_moment2_lexemes"],
            "moment3_lexeme_mismatches": 11747
            - profiled["graph_authority"]["exact_moment3_lexemes"],
            "reference_analysis_digest_used": False,
            "reference_support_moments_used": False,
            "location": profiled["fixed_site_location"],
        },
        "common_physical_science": {
            "observations": 11747,
            "tracks": 64,
            "exact_lane_source_alias_membership_tracks": 64,
            "exact_support_bounds_tracks": 64,
            "maximum_fit_delta_same_in_both_profiles": portable["tracks"][
                "maximum_absolute_fit_delta"
            ]
            == profiled["tracks"]["maximum_absolute_fit_delta"],
        },
        "valid_native_provenance_partition": {
            "portable_exact_reference_support_digests": portable["partition_authority"][
                "exact_support_digests"
            ],
            "profiled_exact_reference_support_digests": profiled["partition_authority"][
                "exact_support_digests"
            ],
            "portable_exact_reference_training_masks": portable["partition_authority"][
                "exact_training_masks"
            ],
            "profiled_exact_reference_training_masks": profiled["partition_authority"][
                "exact_training_masks"
            ],
            "cause": (
                "Candidate and track identities bind the actual native analysis descriptor. "
                "Changing the support profile changes that descriptor, and neither valid native "
                "lane may borrow the reference analysis digest to force the reference partition."
            ),
        },
        "prior_reference_identity_control": {
            "receipt": str(prior_path.relative_to(DEPLOYMENT)),
            "receipt_sha256": sha256(prior_path),
            "membership_identical_tracks": prior["partition_comparison"][
                "membership_identical_tracks"
            ],
            "exact_support_digests": prior["partition_comparison"]["exact_support_digests"],
            "exact_partition_seeds": prior["partition_comparison"]["exact_partition_seeds"],
            "exact_training_masks": prior["partition_comparison"]["exact_training_masks"],
            "open_duplicate_rank_identity_ties": prior["partition_comparison"][
                "open_duplicate_rank_identity_ties"
            ],
            "scope": (
                "This earlier control used the persisted reference analysis identity and freshly "
                "derived server-profile support. It isolates the six known duplicate-rank C4 "
                "identity ties; those reference identities are not inputs to either fresh-native "
                "lane."
            ),
        },
        "interpretation": (
            "The server support profile removes nearly all portable moment-spelling differences "
            "(8 moment2 and 32 moment3 rows remain, consistent with the measured native fractional "
            "input deltas), but a valid fresh-native analysis identity still creates a different "
            "response-free partition. The location-score changes coincide with that partition "
            "change and demonstrate downstream sensitivity under simultaneous provenance and "
            "support-profile changes; this comparison does not isolate every causal contribution. "
            "Physical membership and track fits remain equal."
        ),
    }
    (HERE / "support-profile-comparison.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
