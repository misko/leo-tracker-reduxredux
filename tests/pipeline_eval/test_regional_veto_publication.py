from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from leo.analysis.localization_v4 import backend
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import ALGO08V2, PLOTS
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools import algo08_position, algo08_scan
from tools.pipeline_eval.qualification import experimental_publication, paired_publication
from tools.pipeline_eval.variants import v5_core
from tools.pipeline_eval.variants.experimental import regional_bound_guard
from tools.pipeline_eval.variants.experimental.regional_reassignment import probes


ARMS = ("c0", "fitted_c")


def packet(region, endpoint):
    center = list(region.center)
    endpoint_latlon = list(map(float, region.latlon(endpoint)))
    frame = dict(region_center=center, box_width_km=region.width_km)
    arms = {arm: dict(endpoint_latlon=endpoint_latlon, associated_points=0,
                      owner_sha256=canonical_digest([])) for arm in ARMS}
    return dict(
        arms=arms, observations=[], objective_replay={},
        position_grid=dict(frame, schema_version=1, kind="conditional-position-grid", matched_c_grid=True,
                           conditioning="published satellite ownership and phase linearization fixed",
                           endpoint_latlon=dict.fromkeys(ARMS, endpoint_latlon),
                           points=[dict(east_km=0., north_km=0., latlon=center,
                                        scores=dict.fromkeys(ARMS, 0.))],
                           evaluated_points=1, planned_points=1, complete=True),
        position_path=dict(frame, schema_version=2, kind="recorded-position-path", selected_model=ALGO08V2,
                           stages=[dict(model_version=ALGO08V2, arms={arm: dict(
                               endpoint=endpoint, rounds=[], history_available=False) for arm in ARMS})]),
    )


@pytest.mark.parametrize(("enabled", "boundary", "far_votes", "withheld"), (
    (False, True, True, False),
    (True, True, True, True),
    (True, False, True, False),
    (True, True, False, False),
))
def test_regional_veto_flows_through_normal_terminal_and_publication(
    tmp_path, monkeypatch, enabled, boundary, far_votes, withheld,
):
    output = tmp_path / "output"
    output.mkdir()
    detector = tmp_path / "detector.so"
    detector.write_bytes(b"fixture detector")
    detector_digest = sha256(detector.read_bytes()).hexdigest()
    release = tmp_path / "release"
    tracks_config = release / "assets" / "tracks.json"
    tracks_config.parent.mkdir(parents=True)
    tracks_config.write_text('{"config": {}}')
    track_digest = sha256(tracks_config.read_bytes()).hexdigest()
    monkeypatch.setattr(experimental_publication, "RELEASE", release)
    monkeypatch.setattr(algo08_scan, "PINS", {"tracks.json": track_digest, "cancellation-factors.so": detector_digest})
    region = dict(center=[-32., 115.], screen_center=[-31.5, 115.5], width_km=25.)
    region_path = tmp_path / "offer.json"
    region_path.write_text(json.dumps(region))
    archive = tmp_path / "tle"
    args = SimpleNamespace(recording=tmp_path / "opaque", bulk_root=output, archive=archive, region=region_path)
    spec = dict(solver="stock", detector=str(detector), detector_sha256=detector_digest)
    if enabled:
        spec["regional_veto"] = True

    inventory = dict(recording_name="opaque", window_count=1)
    inventory_digest = canonical_digest(inventory)
    session = "fast-" + inventory_digest[7:39]
    monkeypatch.setattr(FastScanStore, "inventory", lambda *_args, **_kwargs: (session, inventory_digest, inventory))
    measurements = [dict(channel=1, receiver_id=rx, candidates=[]) for rx in range(2)]
    raw = canonical_digest([inventory_digest, [canonical_digest("fixture samples")]])
    native = dict(source=dict(probes=measurements, session_id=session, input_manifest_sha256=inventory_digest,
                              raw_recording_authority_digest=raw,
                              analysis_manifest_sha256=canonical_digest([
                                  "cancellation", raw, spec["detector_sha256"], measurements])),
                  provenance=dict(rf_mapping_authorities=[], processed_windows=1, window_count=1, invalid_capture=0))
    monkeypatch.setattr(algo08_scan, "acquire", lambda *_: native)

    def prepare(document, reader, _config, *, screen_latitude_deg, screen_longitude_deg):
        assert document == native and isinstance(reader, TleArchiveReader) and reader.root == archive
        assert [screen_latitude_deg, screen_longitude_deg] == region["screen_center"]
        return prepared

    monkeypatch.setattr(backend, "read_manifest", lambda _: {})
    monkeypatch.setattr(backend, "validate_manifest", lambda _manifest, **_kwargs: dict(binary="fixture"))
    monkeypatch.setattr(algo08_position.orbit_projector, "Projector", lambda path: None)
    monkeypatch.setattr(algo08_position, "NativeBound", lambda binary: None)
    monkeypatch.setattr(algo08_position, "numerical_bindings", lambda projector: nullcontext())
    monkeypatch.setattr(algo08_position, "prepare_native_scan", prepare)
    monkeypatch.setattr(algo08_position, "_prepared_values", lambda ready: ready)

    prepared = {"tracks": object()}
    endpoint = [0., region["width_km"] / 2 if boundary else 0.]
    generated, rendered, scored = [], [], []

    def infer(ready, offer, _bound, _stage, *, selected_evidence):
        assert ready is prepared and list(offer.center) == region["center"]
        selected_evidence(ready, {"arms": {arm: {"endpoint_east_north_km": endpoint} for arm in ARMS},
                                  "offer": offer}, None)
        return dict(status="ok", arms={arm: {"latlon": list(map(float, offer.latlon(endpoint)))}
                                      for arm in ARMS}, metrics={})

    def selected_packet(ready, signed, fit):
        assert ready is prepared and fit is None
        science = packet(signed["offer"], endpoint)
        generated.append(science)
        return science

    def render(science, *, title, evaluation_reference):
        assert science is generated[0] and title == "opaque" and evaluation_reference is None
        rendered.append(True)
        figures = {}
        for index, name in enumerate(PLOTS):
            stream = BytesIO()
            Image.new("RGBA", (1, 1), (index, 1, 0, 255)).save(stream, format="PNG")
            figures[name] = stream.getvalue()
        return figures

    def score(tracks, reader, offer):
        assert tracks is prepared["tracks"] and isinstance(reader, TleArchiveReader) and reader.root == archive
        scored.append(True)
        rows = list(probes(offer))
        far = [offer.width_km * 2.5, 0.]
        for row in rows:
            value = 2. if far_votes and row["xy_km"] == far else 1. if row["side"] == "inside" else 0.
            row["receiver_scores"] = {"1": value, "2": value}
        return {"points": rows}

    monkeypatch.setattr(v5_core, "infer", infer)
    monkeypatch.setattr(algo08_position, "selected_packet", selected_packet)
    monkeypatch.setattr(algo08_scan, "render", render)
    monkeypatch.setattr(regional_bound_guard, "causal_probes", score)

    receipt = experimental_publication.run(args, spec)
    assert v5_core.infer is infer
    assert len(scored) == int(enabled and boundary)
    assert len(generated) == len(rendered) == int(not withheld)
    assert receipt["region"] == region
    result = paired_publication.evidence(output, receipt, 0, read_only=True)
    assert result["raw_authority"] == raw
    store = FastStandardAnalysisStore(output)
    run = receipt["run_id"]
    publication = store.detail(run)
    assert publication["state"] == ("withheld" if withheld else "complete")
    assert publication["region"] == region
    if withheld:
        assert result["reason"] == publication["reason"] == "both_receivers_support_far_exterior"
        assert result["arms"] == {arm: {"latlon": None} for arm in ARMS}
        assert result["artifacts"] == [] and not list(output.rglob("*.png"))
        assert store.position_path(run) is None and store.position_grid(run) is None
    else:
        assert tuple(item["name"] for item in result["artifacts"]) == PLOTS
        assert len(list(output.rglob("*.png"))) == len(PLOTS)
        assert all(result["arms"][arm]["latlon"] is not None for arm in ARMS)
        assert result["scientific_digests"].keys() == {"grid", "path"}
