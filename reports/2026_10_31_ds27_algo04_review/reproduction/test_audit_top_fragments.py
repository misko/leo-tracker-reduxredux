import json
from pathlib import Path
import tempfile
import unittest

from audit_top_fragments import annotation_evidence, held_ids, omission_status, recovery_evidence, shared_target_diagnostics, source_match


class AuditTests(unittest.TestCase):
    def test_bundle_and_subset_matches_preserve_exact_fragment_coverage(self):
        self.assertEqual(source_match(["a", "b"], ["a"], ["a", "b", "c"])["relation"],
                         "bundle_contains_parent")
        match = source_match(["a", "b"], ["a"], ["b"])
        self.assertTrue(match["disjoint_from_ranked_fragment"])
        self.assertFalse(match["entire_fragment_covered"])
        self.assertIsNone(source_match(["a"], ["a"], ["different"]))

    def test_native_order_reconstructs_held_ids_instead_of_sorted_hash_order(self):
        track = dict(observation_ids=["z", "a", "m"])
        observations = {oid: dict(time_s=t) for oid, t in zip(track["observation_ids"], [0, 13, 25])}
        target = dict(observation_ids=["a", "m", "z"])
        split = dict(block_s=12, held_blocks=[0, 2])
        self.assertEqual(held_ids(target, [track], observations, split), ["z", "m"])
        split["target_held_indices"] = [1]
        with self.assertRaisesRegex(ValueError, "Stored held indices"):
            held_ids(target, [track], observations, split)

    def test_bundle_order_requires_exact_increasing_native_times(self):
        target = dict(graph_bundle=True, observation_ids=["b", "a"])
        observations = {"a": dict(time_s=0), "b": dict(time_s=1)}
        with self.assertRaisesRegex(ValueError, "Bundle target order"):
            held_ids(target, [], observations, dict(block_s=12, held_blocks=[0]))

    def test_missing_target_is_not_invented_as_budget_failure(self):
        self.assertEqual(omission_status(dict(attempts=[], stages=[]), {"T"}),
                         "not_selected_by_frozen_target_schedule")
        decision = dict(selected_track_ids=["T"], stages=[dict(name="target-0-annotation",
                                                               status="budget_exhausted")])
        self.assertEqual(omission_status(decision, {"T"}), "explicit_budget_omission")

    def test_retained_residual_vector_is_used_only_with_exact_length_mapping(self):
        track = dict(observation_ids=["z", "a", "m"])
        observations = [dict(observation_id=oid, time_s=t) for oid, t in zip(track["observation_ids"], [0, 13, 25])]
        score = dict(negative_twice_log_density=1, rms_hz=2, held_residual_hz=[3, 4])
        value = dict(scores=dict(conditional_target=score), final_phase_change_s=.1,
                     minimum_target_elevation_deg=1, target_phase_boundary_mass=0)
        proposal = dict(norad=10, candidate_index=0, alias=0,
                        arms={a: value for a in ("c0", "fitted_c")})
        document = dict(annotation=dict(status="prediction_mismatch", norad=10, votes=[]),
                        folds=[dict(seed=1, split=dict(block_s=12, held_blocks=[0, 2]),
                                    proposals=[proposal])])
        result = annotation_evidence(document, dict(target=dict(observation_ids=["a", "m", "z"])),
                                     [track], observations, {"m"})
        self.assertEqual(result["top_norad_hypothesis"], 10)
        self.assertTrue(result["hypothesis_only"])
        self.assertEqual(result["folds"][0]["held_observation_ids"], ["z", "m"])
        self.assertEqual(result["folds"][0]["held_ranked_fragment_mask"], [False, True])
        score["held_residual_hz"] = [3]
        result = annotation_evidence(document, dict(target=dict(observation_ids=["a", "m", "z"])),
                                     [track], observations, {"m"})
        self.assertTrue(result["folds"][0]["retained_held_residual_mapping"].startswith("unproven"))
        self.assertNotIn("held_residual_hz", result["folds"][0])

    def test_shared_profiled_rms_is_not_mislabeled_as_raw_rms(self):
        observations = [dict(observation_id="a", time_s=1, measured_cfo_hz=100),
                        dict(observation_id="b", time_s=2, measured_cfo_hz=102)]
        document = dict(target_entries=[dict(component="T", observation_ids=["b", "a"])])
        value = dict(target_diagnostics=[dict(component="T", norad=1, times_s=[1, 2],
                     CFO_hz=[100, 102], predicted_CFO_hz=[90, 90], residual_hz=[-1, 1],
                     RMS_hz=1, bias_hz=11)])
        result = shared_target_diagnostics(document, value, {"a"}, observations)[0]
        self.assertEqual(result["mapping"], "exact_native_ids_times_and_alias")
        self.assertEqual(result["profiled_RMS_hz"], 1)
        self.assertGreater(result["raw_RMS_hz"], 11)
        self.assertEqual(result["raw_residual_hz"], [10, 12])
        self.assertEqual(result["bias_removed_residual_hz"], [-1, 1])

    def test_unpublished_shadow_ids_suppress_inventory_without_fabricating_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "all-large-track-recovery/job"
            folder.mkdir(parents=True)
            policy = dict(proposed_associated_ids=["published", "rx2-shadow-a", "rx2-shadow-b"],
                          gates=dict(tracks=[dict(component="RX1-CH8-T001", norad=69482,
                                                  observation_ids=["published"])]))
            (folder / "inventory.json").write_text(json.dumps(dict(tracks=[], policy={a: policy for a in ("c0", "fitted_c")})))
            (folder / "publication_support.json").write_text(json.dumps(dict(arms={
                a: dict(owners={"published": 69482}, unreported_postfit_ids=["rx2-shadow-a", "rx2-shadow-b"])
                for a in ("c0", "fitted_c")})))
            (root / "decision.json").write_text(json.dumps(dict(attempts=[], stages=[])))
            row = dict(all_track_observation_ids=["rx2-shadow-a", "rx2-shadow-b"],
                       observation_ids=["rx2-shadow-a", "rx2-shadow-b"])
            result = recovery_evidence(root, row, [], [], {}, {a: {"published": 69482} for a in ("c0", "fitted_c")})
            self.assertEqual(result["status"], "unpublished_postfit_ids_suppress_recovery_inventory")
            proof = result["inventory_publication_comparisons"][0]["arms"]["fitted_c"]
            self.assertEqual(proof["published_parent_owners"], {})
            self.assertFalse(proof["shadow_owner_map_present"])
            self.assertEqual(proof["saved_shadow_owner_hypotheses"], {})
            self.assertEqual(result["inventory_matches"], [])


if __name__ == "__main__":
    unittest.main()
