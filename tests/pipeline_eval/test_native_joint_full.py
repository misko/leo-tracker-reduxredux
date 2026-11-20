import pytest

from tools.pipeline_eval.qualification import native_joint_full as trial
from tools.pipeline_eval.qualification import native_joint_full_results as results
from tools.pipeline_eval.variants.projected_fit import Region


def test_alternate_queries_preserve_frozen_native_catalogue_and_clock():
    inputs = trial.base.phase.frozen_inputs()
    jobs = list(trial.omitted_controls(inputs))
    assert len({job["id"] for job, _ in jobs}) == 9
    assert all(job["cohort"] == "omitted" for job, _ in jobs)
    assert set(job["recording"] for job, _ in jobs) - inputs.keys() == {"DS26-0277"}
    for job, _ in jobs:
        ident = job["recording"]
        item = inputs.get(ident) or trial.base.native._load_case(ident)
        primary, _ = trial.query(item, "roof")
        data = dict(job["packet"])
        actual = dict(primary["packet"])
        assert data.pop("offer")["center"] != actual.pop("offer")["center"]
        assert data == actual


def test_signed_tile_margin_inverts_the_solver_tangent_projection():
    center = (42.0, -73.0)
    offer = dict(center=center, width_km=25.0)
    region = Region(
        "test",
        center,
        results.geodetic_to_ecef_km(*center, 0),
        results.ecef_to_enu_matrix(*center),
    )
    for xy, margin in (((0, 0), 12.5), ((12.5, -5), 0), ((-4, 27.5), -15)):
        assert results.roi_margin(region.site(xy)[1], offer) == pytest.approx(margin, abs=1e-7)
    assert results.roi_margin(None, offer) is None


def test_histograms_bind_edges_and_preserve_unavailable_geometry():
    assert results.histogram(iter([None, 0.5, 1, 1.1, 2, 3]), (1, 2)) == {
        "inclusive_upper_edges": [1, 2],
        "counts": [2, 2, 1],
        "unavailable": 1,
    }


def test_c_ablation_keeps_withheld_telemetry_apart_from_published_accuracy():
    rows = []
    for arm, c in (("c0", 0), ("fitted_c", 1)):
        for ident, publishes, cohort in (("ok", True, "roof"), ("held", False, "roof")):
            rows.append(
                dict(
                    id=ident,
                    cohort=cohort,
                    dataset="DS26",
                    arm=arm,
                    error_km=1 + c if publishes else None,
                    forced_error_km=1 + c,
                    conditional_rms_hz=100 - c,
                    held_score=0.4 + 0.1 * c,
                )
            )
    scores = results.ablation(rows)["DS26"]
    assert scores["error_km"]["n"] == scores["error_km"]["increased"] == 1
    assert scores["conditional_rms_hz"]["n"] == scores["conditional_rms_hz"]["decreased"] == 2
    assert scores["held_score"]["n"] == scores["held_score"]["increased"] == 2
