"""The new model has a separate immutable terminal identity."""

import pytest

from leo.contracts.fast_graph_position import KIND, MODEL_VERSION, validate_terminal


@pytest.mark.parametrize("state", ["failed", "unavailable"])
def test_unqualified_terminal_has_no_position(state):
    document = dict(schema_version=1, kind=KIND, model_version=MODEL_VERSION,
                    input_sha256="sha256:input", state=state, position=None)
    assert validate_terminal(document, input_sha256="sha256:input") is document
    document["position"] = dict(latitude_deg=0., longitude_deg=0.)
    with pytest.raises(ValueError):
        validate_terminal(document, input_sha256="sha256:input")


def test_terminal_cannot_change_input_identity():
    with pytest.raises(ValueError):
        validate_terminal(dict(schema_version=1, kind=KIND, model_version=MODEL_VERSION,
                               input_sha256="sha256:other", state="failed", position=None),
                          input_sha256="sha256:input")
