"""The selected graph model cannot relabel a predecessor's fallback endpoint."""

import copy

import pytest

from leo.contracts.fast_graph_position import MODEL_VERSION as V1
from leo.contracts.fast_graph_position_v2 import MODEL_VERSION as V2
from leo.contracts.fast_graph_position_v3 import MODEL_VERSION as V3
from leo.storage.graph_position_view import GraphPositionView


def terminal(model, latitude, **extra):
    position = dict(latitude_deg=latitude, longitude_deg=-122.5)
    return dict(
        model_version=model,
        state="complete",
        position=position,
        arms={a: dict(endpoint_latlon=[latitude, -122.5]) for a in ("c0", "fitted_c")},
        **extra,
    )


class Baseline:
    source = dict(run_id="run", job_id="source-v1", model_version=V1)

    def __init__(self):
        self.result = terminal(V1, 37.9)

    def inputs(self):
        return iter([self.source])

    def terminal(self, job):
        assert job == self.source
        return self.result, dict(sha256="baseline")


class Store:
    def __init__(self, source, model, result):
        self.source = source
        self.descriptor = dict(job_id=model, model_version=model)
        self.result = result
        self.status_value = dict(state="complete")
        self.error = None
        self.jobs = []

    def job(self, source):
        assert source == self.source
        self.jobs.append(copy.deepcopy(source))
        return self.descriptor

    def status(self, identifier):
        assert identifier == self.descriptor["job_id"]
        return self.status_value

    def terminal(self, job):
        assert job == self.descriptor
        if self.error:
            raise self.error
        return self.result, dict(sha256="validated")


def ports(*, baseline_fallback=False):
    baseline = Baseline()
    prior = terminal(
        V2,
        37.9 if baseline_fallback else 37.91,
        decision="ALGO02_fallback" if baseline_fallback else "ALGO03_single",
        baseline=baseline.result,
        baseline_seconds=10.0,
        recovery_seconds=20.0,
        failure="No qualified ALGO03 addition" if baseline_fallback else None,
        selected=None if baseline_fallback else dict(arms=terminal(V2, 37.91)["arms"]),
    )
    candidate = Store(baseline.source, V2, prior)
    numerical_proof = terminal(V2, 37.92, selected=dict(arms=terminal(V2, 37.92)["arms"]))
    result = dict(
        model_version=V3,
        state="complete",
        decision="ALGO04_additive",
        incumbent=prior,
        candidate=numerical_proof,
        position=numerical_proof["position"],
        incumbent_seconds=30.0,
        numerical_seconds=40.0,
        total_seconds=70.0,
    )
    numerical = Store(candidate.descriptor, V3, result)
    return baseline, candidate, numerical


def view(tmp_path, *, baseline_fallback=False):
    baseline, candidate, numerical = ports(baseline_fallback=baseline_fallback)
    reader = GraphPositionView(
        tmp_path, V3, baseline=baseline, candidate=candidate, numerical=numerical
    )
    return reader, baseline, candidate, numerical


def test_v3_consumes_v2_job_and_presents_only_the_numerical_candidate(tmp_path):
    reader, baseline, candidate, numerical = view(tmp_path)
    result = reader.detail("run")
    assert numerical.jobs == [candidate.descriptor]
    assert result["selected_model"] == V3
    assert result["decision"] == "ALGO04_additive"
    assert not result["fallback"]
    assert result["selected"]["model_version"] == V3
    assert result["position"] == numerical.result["candidate"]["position"]
    assert result["selected"]["arms"]["fitted_c"]["endpoint_latlon"] == [37.92, -122.5]
    assert result["baseline"]["position"] == baseline.result["position"]
    assert result["incumbent"]["position"] == candidate.result["position"]
    assert result["numerical_seconds"] == 40.0 and result["total_seconds"] == 70.0


@pytest.mark.parametrize(
    "baseline_fallback,model,decision",
    [
        (False, V2, "ALGO03_fallback"),
        (True, V1, "ALGO02_fallback"),
    ],
)
@pytest.mark.parametrize("state", ["missing", "running", "failed", "corrupt", "complete_fallback"])
def test_v3_keeps_truthfully_labeled_predecessor_for_every_unqualified_case(
    tmp_path, baseline_fallback, model, decision, state
):
    reader, baseline, candidate, numerical = view(tmp_path, baseline_fallback=baseline_fallback)
    if state == "missing":
        numerical.status_value = None
    elif state in {"running", "failed"}:
        numerical.status_value = dict(state=state, failure="Numerical attempt " + state)
    elif state == "corrupt":
        numerical.error = ValueError("Invalid receipt")
    else:
        numerical.result.update(
            decision="ALGO03_fallback",
            position=candidate.result["position"],
            failure="Candidate would change an incumbent owner",
        )
    result = reader.detail("run")
    assert result["selected_model"] == V3
    assert result["selected"]["model_version"] == model
    assert result["decision"] == decision and result["fallback"]
    assert result["position"] == candidate.result["position"]
    assert result["baseline"]["position"] == baseline.result["position"]
    if state == "complete_fallback":
        assert result["reason"] == "Candidate would change an incumbent owner"
    elif state == "corrupt":
        assert result["reason"] == "ALGO04 result unavailable: ValueError"


def test_v3_does_not_read_numerical_store_until_v2_completes(tmp_path):
    reader, baseline, candidate, numerical = view(tmp_path)
    candidate.status_value = None
    result = reader.detail("run")
    assert numerical.jobs == []
    assert result["decision"] == "ALGO02_fallback"
    assert result["selected"]["model_version"] == V1
    assert result["position"] == baseline.result["position"]
    assert "Awaiting qualified ALGO03" in result["reason"]


@pytest.mark.parametrize("model", [V1, V2])
def test_old_selections_never_query_v3(tmp_path, model):
    baseline, candidate, numerical = ports(baseline_fallback=True)
    reader = GraphPositionView(
        tmp_path, model, baseline=baseline, candidate=candidate, numerical=numerical
    )
    result = reader.detail("run")
    assert numerical.jobs == []
    assert result["selected_model"] == model
    assert result["selected"]["model_version"] == model
    assert result["position"] == baseline.result["position"]


def test_unrecognized_model_is_not_implicitly_activated(tmp_path):
    with pytest.raises(ValueError, match="explicitly selected"):
        GraphPositionView(tmp_path, "latest")


def test_default_v3_composition_uses_the_shared_incumbent_port_without_writes(tmp_path):
    reader = GraphPositionView(tmp_path, V3)
    assert reader.numerical.incumbent is reader.candidate
    assert reader.candidate.baseline is reader.baseline
    assert reader.detail("missing")["state"] == "unavailable"
    assert list(tmp_path.iterdir()) == []
