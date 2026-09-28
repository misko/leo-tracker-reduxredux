import numpy as np
import pytest
from cluster_signals import (
    canonical,
    clustered_plot,
    distance_hierarchy,
    distribution_distance,
    family_distance,
    hamming,
    qualifies_word,
)


def test_family_invariance_and_raw_distance_distinction():
    word = "001011" * 10
    shifted = word[1:] + word[:1]
    inverse = shifted.translate(str.maketrans("01", "10"))
    assert canonical(word) == canonical(inverse)
    assert family_distance(word, inverse) == 0
    assert hamming(word, shifted) > 0
    with pytest.raises(ValueError):
        canonical("?" * 60)


def test_js_distance_distinguishes_missing_from_matching_data():
    assert distribution_distance({}, {"a": 1}) is None
    assert distribution_distance({"a": 2}, {"a": 8}) == 0
    assert distribution_distance({"a": 1}, {"b": 1}) == pytest.approx(1)
    assert distribution_distance({"a": 1, "b": 1}, {"a": 2, "b": 2}) == 0


def test_word_gate_requires_complete_independent_receiver_agreement():
    row = dict(
        shared=60, word="01" * 30, peer_word="01" * 30, selection=0.4, held=0.4, wrong_max=0.3
    )
    assert qualifies_word(row)
    assert not qualifies_word({**row, "shared": 59})
    assert not qualifies_word({**row, "peer_word": "10" * 30})
    assert not qualifies_word({**row, "wrong_max": 0.4})
    assert not qualifies_word({"word": "01" * 30})


@pytest.mark.parametrize(
    "matrix",
    [
        [[0, np.nan], [np.nan, 0]],
        [[0, -1], [-1, 0]],
        [[0, 1], [2, 0]],
        [[1, 0], [0, 0]],
        [[0, 1]],
    ],
)
def test_bad_distance_matrices_are_rejected(matrix):
    with pytest.raises(ValueError):
        distance_hierarchy(matrix, ["a", "b"])


def test_no_ward_assumption_and_insufficient_samples():
    with pytest.raises(ValueError, match="Euclidean"):
        distance_hierarchy([[0, 1], [1, 0]], ["a", "b"], "ward")
    assert distance_hierarchy(np.zeros((0, 0)), []).shape == (0, 4)
    assert distance_hierarchy([[0]], ["a"]).shape == (0, 4)


def test_dendrogram_and_heatmap_rows_align(tmp_path, monkeypatch):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    captured = []
    monkeypatch.setattr(Figure, "savefig", lambda fig, *a, **kw: captured.append(fig))
    matrix = np.array([[0, 0.1, 0.9], [0.1, 0, 0.8], [0.9, 0.8, 0]])
    labels = ["a", "b", "c"]
    clustered_plot(matrix, labels, tmp_path / "tree.png", "test")
    tree_ax, heat_ax = captured[0].axes[:2]
    tree_top_to_bottom = [t.get_text() for t in tree_ax.get_yticklabels()][::-1]
    heat_labels = [t.get_text() for t in heat_ax.get_yticklabels()]
    assert heat_labels == tree_top_to_bottom
    order = [labels.index(label) for label in heat_labels]
    np.testing.assert_array_equal(heat_ax.images[0].get_array(), matrix[np.ix_(order, order)])
    plt.close("all")
