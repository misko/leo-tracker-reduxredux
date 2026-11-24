from collections import Counter
from io import BytesIO

from PIL import Image
import pytest

from leo.analysis.position_grid import ARMS, sample_position_grid
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.fast_standard_analysis import ALGO08V2, PLOTS
from leo.presentation.position_path import recorded_fit_path
from reports.ALGO08.v3.live_adaptive_grid import IncompleteAdaptiveGrid, adaptive_sampler, quality
from reports.ALGO08.v3.live_adaptive_grid_entry import NAMESPACE, read_manifest, read_sidecar, write_research


ENDPOINTS = dict(c0=(.1, .2), fitted_c=(.2, .3))


def quadratic(arm, xy):
    offset = ENDPOINTS[arm]
    return sum((a-b)**2 for a, b in zip(xy, offset, strict=True))


def test_only_real_calls_form_the_adaptive_grid_in_reference_order():
    counts = Counter()

    def measured(arm, xy):
        counts[arm, xy] += 1
        return quadratic(arm, xy)

    active = adaptive_sampler(measured, ENDPOINTS)
    full = sample_position_grid(quadratic, ENDPOINTS)
    assert active["planned_points"] == active["evaluated_points"] < full["evaluated_points"]
    assert active["reference_layout"]["candidates"] == full["evaluated_points"]
    assert len(counts) == 2*active["evaluated_points"] and set(counts.values()) == {1}
    assert active["points"] == [p for p in full["points"] if p in active["points"]]
    assert quality(active, full)["passed"]
    hidden = next(p for p in full["points"] if p not in active["points"])
    hidden["scores"]["c0"] = -100.
    assert not quality(active, full)["passed"]


def test_deadline_discards_the_adaptive_document():
    times = iter((0., 0., 0., .01, 2.))
    with pytest.raises(IncompleteAdaptiveGrid, match="deadline"):
        adaptive_sampler(quadratic, ENDPOINTS, maximum_seconds=1., clock=lambda: next(times))


def test_research_namespace_binds_path_phase_and_eight_pngs_and_denies_partial(tmp_path):
    offer = Algo08Region((-33., 20.), 25.)
    run = "algo08-v2-saved-test"
    arms = {a: dict(endpoint_latlon=list(offer.center), associated_points=2, owner_sha256=a) for a in ARMS}
    science = dict(schema_version=3, run_id=run, model_version=ALGO08V2, selected_model=ALGO08V2,
                   state="complete", reference_usage="evaluation_only", region=offer.document(), glrt_points=3,
                   arms=arms, terminal_sha256="terminal", input_sha256="input")
    path = recorded_fit_path([dict(model_version=ALGO08V2, arms=arms)], ALGO08V2,
                             region_center=offer.center, box_width_km=25., schema_version=2)
    sample = adaptive_sampler(lambda *_: 3., {a: (0., 0.) for a in ARMS})
    sample.update(region_center=list(offer.center), endpoint_latlon={a: arms[a]["endpoint_latlon"] for a in ARMS})
    for row in sample["points"]:
        # The test uses the same regional transform as the real preparation.
        from leo.analysis.localization_v3.region import SearchRegion

        row["latlon"] = list(SearchRegion(offer.center).latlon((row["east_km"], row["north_km"])))
    stream = BytesIO()
    Image.new("RGBA", (3, 3)).save(stream, format="PNG")
    media = dict.fromkeys(PLOTS, stream.getvalue())
    with pytest.raises(ValueError, match="accounting"):
        write_research(tmp_path, run, science, media, dict(sample, complete=False), path, ["signed phase"])
    assert not (tmp_path/NAMESPACE).exists()
    write_research(tmp_path, run, science, media, sample, path, ["signed phase"])
    assert not (tmp_path/"fast-scan-standard-v2").exists()
    assert read_manifest(tmp_path, run)["phase_state_sha256"] == "signed phase"
    measured, recorded = (read_sidecar(tmp_path, run, name) for name in ("sample", "path"))
    assert measured["binding"] == recorded["binding"]
    assert len(read_manifest(tmp_path, run)["publication"]["artifacts"]) == len(PLOTS)
