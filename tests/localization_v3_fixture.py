"""Small synthetic scientific/publication evidence for owned boundary tests."""

from copy import deepcopy
from io import BytesIO

from PIL import Image

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.contracts.localization_v3 import MODEL


def evidence_fixture():
    observations = [dict(observation_id="a"), dict(observation_id="b")]
    owners = {"a": 69333}
    arm = dict(
        endpoint_latlon=[37.906, -122.545],
        associated_points=1,
        owner_sha256=canonical_digest(owners),
    )
    arms = {name: deepcopy(arm) for name in ("c0", "fitted_c")}
    model = "algo04-causal-numerical-recovery-v1"
    packet = dict(
        observations=observations,
        tracks=[],
        selected_model=model,
        arms=arms,
        objective_replay=dict(c0=0.0, fitted_c=0.0),
        rows={name: [dict(observation_id="a", norad=69333)] for name in arms},
        position_grid=dict(
            schema_version=1,
            kind="conditional-position-grid",
            matched_c_grid=True,
            conditioning="published satellite ownership and phase linearization fixed",
            endpoint_latlon={a: r["endpoint_latlon"] for a, r in arms.items()},
            box_width_km=25.0,
            evaluated_points=1,
            planned_points=1,
            complete=True,
            points=[
                dict(
                    east_km=0.0,
                    north_km=0.0,
                    latlon=[37.906, -122.545],
                    scores=dict(c0=10.0, fitted_c=11.0),
                )
            ],
        ),
        position_path=dict(
            schema_version=1,
            kind="recorded-position-path",
            region_center=[37.906, -122.545],
            box_width_km=25.0,
            selected_model=model,
            stages=[
                dict(
                    model_version=model,
                    arms={
                        a: dict(endpoint=[0.0, 0.0], rounds=[], history_available=False)
                        for a in arms
                    },
                )
            ],
        ),
    )
    evidence = dict(
        schema_version=1,
        model_version=MODEL,
        status="figures_ready",
        identity=dict(run_id="run", session_id="session", input_sha256="sha256:" + "1" * 64),
        provenance=dict(
            configuration_sha256="sha256:" + "2" * 64, implementation_sha256="sha256:" + "3" * 64
        ),
        audit=dict(
            reassociation_complete=dict(
                status="reassociation_evaluated",
                recovery_complete=True,
                recovery=dict(selected=None, final={a: dict(associated=1) for a in arms}),
            )
        ),
        selected=dict(owners={a: deepcopy(owners) for a in arms}, arms=deepcopy(arms)),
        presentation=packet,
        render=dict(
            title="fixture",
            renderer_revision="final-error-v7",
            reference_usage="evaluation_only",
            evaluation_reference=None,
        ),
    )
    stream = BytesIO()
    Image.new("RGB", (2, 2)).save(stream, format="PNG")
    return evidence, dict.fromkeys(PLOTS, stream.getvalue())
