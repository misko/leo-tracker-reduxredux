from pathlib import Path
import runpy

import numpy as np

from leo.analysis.polynomial_tracklets import TrackConfig


unique = runpy.run_path(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/duplicate_graph_proposals.py"))[
    "unique_proposals"]


def model(offset=0., degree=2):
    return dict(indices=np.arange(8), reference_time_s=3.5, time_scale_s=3.5,
                degree=degree, coefficients_hz=np.array([offset, *([0.] * degree)]))


def test_first_equivalent_proposal_remains_with_same_aliases_and_gate():
    times, values = np.arange(8.), np.full(8, 120.)
    original = model(125.)
    redundant = model(np.nextafter(125., 126.))
    kept = unique(times, values, [original, redundant], TrackConfig())
    assert len(kept) == 1 and kept[0] is original


def test_disagreements_in_shape_alias_or_gate_remain_available():
    times = np.arange(8.)
    config = TrackConfig(alias_spacing_hz=2.**18)
    values = np.full(8, -config.association_sigma*config.noise_sigma_hz)
    original = model()
    other_degree = model(degree=1)
    lifted = model(config.alias_spacing_hz)
    gate_changed = model(-np.spacing(config.alias_spacing_hz)/2)
    changed_support = model()
    changed_support["indices"] = np.arange(7)
    hypotheses = [original, other_degree, lifted, gate_changed, changed_support]
    retained = unique(times, values, hypotheses, config)
    assert [id(m) for m in retained] == [id(m) for m in hypotheses]
