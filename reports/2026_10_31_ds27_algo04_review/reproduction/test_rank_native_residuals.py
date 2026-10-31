import copy
import contextlib
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest

from rank_native_residuals import PERIOD_HZ, canonical_tracks, digest, export_plot_packet, fragment_rows, parent_ranking, polynomial, published_owners, rank, runs


def source(times, ids=None):
    ids = ids or [str(i) for i in range(len(times))]
    return dict(key="SCAN-RX1-CH1-T000", receiver=1, channel=1, rf_hz=11e9,
                observation_ids=ids, times=times, values=list(times), indices=list(range(len(times))),
                pieces=[dict(indices=list(range(len(times))), start_s=min(times), end_s=max(times),
                             reference_time_s=0, time_scale_s=1, coefficients_hz=[0, 1])])


def observed(track):
    return [dict(observation_id=oid, time_s=t, measured_cfo_hz=v, receiver=1, channel=1)
            for oid, t, v in zip(track["observation_ids"], track["times"], track["values"], strict=True)]


class RankingTests(unittest.TestCase):
    def test_chosen_v3_owners_never_include_unchosen_candidate(self):
        def proof(oid):
            return dict(state="complete", model_version="algo03-causal-predictive-v1",
                        selected=dict(arms=dict(fitted_c=dict(associated_ids=[oid], owners={oid: 1}))))
        terminal = dict(state="complete", model_version="algo04-causal-numerical-v1",
                        decision="ALGO03_fallback", incumbent=proof("old"), candidate=proof("new"))
        self.assertEqual(published_owners(terminal), {"old": 1})
        terminal["decision"] = "ALGO04_additive"
        self.assertEqual(published_owners(terminal), {"new": 1})

    def test_fallback_uses_exact_published_baseline_tracks_and_linear(self):
        arm = dict(gates=dict(tracks=[dict(norad=1, observation_ids=["a"])]),
                   linear_gates=[dict(norad=2, observation_ids=["b"])])
        baseline = dict(state="complete", model_version="algo02-causal-family-v1",
                        arms=dict(fitted_c=arm))
        prior = dict(state="complete", model_version="algo03-causal-predictive-v1",
                     decision="ALGO02_fallback", selected=None, baseline=baseline)
        self.assertEqual(set(published_owners(prior)), {"a", "b"})

    def test_fallback_source_proof_labels_only_exact_published_ids_and_known_owners(self):
        arm = dict(gates=dict(tracks=[dict(norad=1, observation_ids=["a"])]),
                   linear_gates=[dict(observation_ids=["b"])])
        baseline = dict(state="complete", model_version="algo02-causal-family-v1",
                        arms=dict(fitted_c=arm))
        prior = dict(state="complete", model_version="algo03-causal-predictive-v1",
                     decision="ALGO02_fallback", selected=None, baseline=baseline,
                     source_support=dict(fitted_c=dict(owners={"a": 1, "b": 2})))
        self.assertEqual(published_owners(prior), {"a": 1, "b": 2})
        for invalid in ({"a": 1, "b": 2, "unpublished": 3}, {"a": 2, "b": 2},
                        {"a": 1, "b": None}):
            prior["source_support"]["fitted_c"]["owners"] = invalid
            with self.assertRaisesRegex(ValueError, "Fallback source-support"):
                published_owners(prior)

    def test_claimed_point_splits_a_short_gap_and_partial_track_stays_partial(self):
        track = source([0, 1, 2, 3, 4])
        rows, summary = fragment_rows("S", [track], observed(track), {"2": 1})
        self.assertEqual([r["observation_ids"] for r in rows], [["0", "1"], ["3", "4"]])
        self.assertTrue(all(not r["parent_wholly_unassociated"] for r in rows))
        self.assertTrue(all(r["parent_residual_span_s"] == 4 for r in rows))
        self.assertEqual(sum(r["points"] for r in rows), summary["residual_graph_unique_points"])

    def test_gap_threshold_and_polynomial_boundary_split_without_interpolation(self):
        track = source([0, 2, 7, 13, 14])
        self.assertEqual(runs(track, set()), [[0, 1, 2], [3, 4]])
        track["pieces"] = [dict(indices=[0, 1], start_s=0, end_s=2),
                           dict(indices=[2, 3, 4], start_s=7, end_s=14)]
        self.assertEqual(runs(track, set(), 10), [[0, 1], [2, 3, 4]])

    def test_identical_alias_components_collapse_and_partial_overlap_is_not_unioned(self):
        a = source([0, 1, 2])
        alias = copy.deepcopy(a)
        alias["key"] = "alias-variant"
        alias["values"] = [v + PERIOD_HZ for v in a["values"]]
        rows, summary = fragment_rows("S", [a, alias], observed(a), {})
        self.assertEqual(summary["duplicate_alias_tracks_collapsed"], 1)
        self.assertEqual(sum(r["points"] for r in rows), 3)
        self.assertEqual(len(rows[0]["source_variants"]), 2)
        overlap = source([1, 2, 3], ["1", "2", "new"])
        with self.assertRaisesRegex(ValueError, "Partial graph-source overlap"):
            canonical_tracks([a, overlap])

    def test_outside_graph_points_are_counted_and_never_promoted_to_tracks(self):
        track = source([0, 1])
        observations = observed(track) + [dict(observation_id="outside", time_s=3,
                                             measured_cfo_hz=99, receiver=1, channel=1)]
        rows, summary = fragment_rows("S", [track], observations, {})
        self.assertEqual(summary["unassociated_untracked_points"], 1)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("outside", rows[0]["observation_ids"])

    def test_existing_polynomial_residual_and_alias_wrap_do_not_create_new_points(self):
        track = source([0, 1, 2])
        observations = observed(track)
        observations[2]["measured_cfo_hz"] -= PERIOD_HZ
        rows, _ = fragment_rows("S", [track], observations, {})
        self.assertEqual(rows[0]["alias_lift_changes"], 1)
        self.assertAlmostEqual(rows[0]["maximum_noninteger_alias_lift_error_hz"], 0)
        self.assertEqual(rows[0]["fragment_point_minus_polynomial_rms_hz"], 0)
        self.assertEqual(polynomial(dict(reference_time_s=0, time_scale_s=1,
                                         coefficients_hz=[1, 2, 3]), 0), -.5)

    def test_duplicate_physical_observation_ids_are_rejected(self):
        track = source([0, 1], ["duplicate", "duplicate"])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            canonical_tracks([track])

    def test_bound_index_ranks_fitted_owners_and_rejects_changed_native_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            track = source([0, 1, 2, 3, 8, 9, 10])
            saved = dict(associated_ids=["2"], owners={"2": 1})
            candidate = dict(state="complete", model_version="algo03-causal-predictive-v1",
                             selected=dict(arms={a: saved for a in ("c0", "fitted_c")}))
            terminal = dict(state="complete", model_version="algo04-causal-numerical-v1",
                            decision="ALGO04_additive", candidate=candidate, session_id="S")
            paths = {}
            for name, value in (("terminal", terminal), ("tracks", [track]),
                                ("observations", observed(track))):
                path = root / (name + ".json")
                path.write_text(json.dumps(value))
                paths[name + "_path"] = str(path)
                paths[name + "_sha256"] = digest(path)
            index = root / "index.json"
            index.write_text(json.dumps(dict(cases=[dict(case="S", state="complete", **paths)])))
            with contextlib.redirect_stdout(io.StringIO()):
                report = rank(index, root / "output")
            self.assertEqual(report["tracks"][0]["observation_ids"], ["3", "4", "5", "6"])
            self.assertEqual(report["tracks"][0]["duration_s"], 7)
            self.assertFalse(report["tracks"][0]["parent_wholly_unassociated"])
            index.write_text(json.dumps(dict(cases=[dict(case="S", state="failed", **paths)])))
            with contextlib.redirect_stdout(io.StringIO()):
                failed = rank(index, root / "failed-output")
            self.assertEqual(failed["complete_cases"], 0)
            unknown = failed["unavailable"][0]["native_graph_fragments"][0]
            self.assertEqual(unknown["ownership_status"], "unknown_no_qualified_association_result")
            self.assertNotIn("parent_associated_points", unknown)
            self.assertNotIn("parent_wholly_unassociated", unknown)
            index.write_text(json.dumps(dict(cases=[dict(case="S", state="complete", **paths)])))
            Path(paths["observations_path"]).write_text("[]")
            with self.assertRaisesRegex(ValueError, "Changed frozen input"):
                rank(index, root / "changed-output")

    def test_plot_packet_is_deterministic_path_free_and_contains_exact_plot_inputs(self):
        track = source([0, 1, 2])
        observations = observed(track)
        rows, _ = fragment_rows("S", [track], observations, {"0": 1})
        rows[0].update(rank=1, terminal_path="/private/terminal.json")
        contexts = dict(S=dict(tracks=[track], observations=observations, associated={"0"}))
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "one.gz", Path(directory) / "two.gz"
            export_plot_packet(first, rows, contexts)
            export_plot_packet(second, rows, contexts)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            packet = json.loads(gzip.decompress(first.read_bytes()))
            self.assertNotIn("terminal_path", packet["top10"][0])
            self.assertEqual(packet["cases"]["S"]["associated_ids"], ["0"])
            self.assertEqual(packet["cases"]["S"]["observations"], observations)

    def test_secondary_parent_span_retains_claimed_hole_without_claiming_continuity(self):
        track = source([0, 1, 2, 3, 4])
        rows, _ = fragment_rows("S", [track], observed(track), {"2": 1})
        parents = parent_ranking(rows)
        self.assertEqual(len(parents), 1)
        self.assertEqual(parents[0]["duration_s"], 4)
        self.assertEqual(parents[0]["longest_native_fragment_duration_s"], 1)
        self.assertEqual(parents[0]["remaining_observation_ids"], ["0", "1", "3", "4"])


if __name__ == "__main__":
    unittest.main()
