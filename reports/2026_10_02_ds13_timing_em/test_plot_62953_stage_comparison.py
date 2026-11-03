import numpy as np

from plot_62953_stage_comparison import map_raw_seed_rows_to_family_rows


def test_seed_rows_map_through_recorded_alias_family_lineage():
    manifest = {
        "family_representatives": [4, 8],
        "alias_grouping": {
            "families": [
                {
                    "representative_candidate_id": "b",
                    "lineage": [
                        {"candidate_id": "a", "input_row_index": 3},
                        {"candidate_id": "b", "input_row_index": 4},
                    ],
                },
                {
                    "representative_candidate_id": "c",
                    "lineage": [{"candidate_id": "c", "input_row_index": 8}],
                },
            ]
        },
    }
    assignments = [{"track_index": 7, "rows": [3, 8]}]
    mapped = map_raw_seed_rows_to_family_rows(manifest, assignments)
    assert mapped[0]["track_index"] == 7
    np.testing.assert_array_equal(mapped[0]["rows"], [0, 1])
