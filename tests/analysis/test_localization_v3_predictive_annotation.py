from types import SimpleNamespace

import algo07v3_serial_annotation_oracle as oracle
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import predictive_annotation as annotation
from leo.operations.localization_v3_parallel import map_annotation_training, map_predictive_folds


@pytest.mark.parametrize('skip,unobservable', [(False, False), (True, False), (False, True)])
@pytest.mark.parametrize('real_children', [False, True])
def test_paired_training_preserves_all_fold_and_proposal_results(
    monkeypatch, skip, unobservable, real_children
):
    d, inventory, seeds = fixture(monkeypatch, annotation, skip=skip, unobservable=unobservable)
    expected = annotation.annotate(d, inventory, 'target')
    monkeypatch.setattr(annotation, 'training_record',
                        lambda d, keep, arm: annotation.fit_training(d, d['node'], keep, arm))
    monkeypatch.setattr(annotation, 'restore_training', lambda d, keep, arm, record: record)
    calls = []

    def reverse_mapper(operation, tasks):
        calls.extend(tasks)
        rows = {item: operation(item) for item in reversed(tasks)}
        return [rows[item] for item in tasks]

    actual = annotation.annotate(
        d, inventory, 'target',
        map_training=map_annotation_training if real_children else reverse_mapper,
        map_folds=map_predictive_folds if real_children else map)
    assert fingerprint(actual) == fingerprint(expected)
    if not real_children:
        assert calls == [(s, a) for s in seeds if not (skip and s == 9) for a in annotation.ARMS]


@pytest.mark.parametrize('stateful', ['callback', 'policy'])
def test_paired_training_does_not_detach_stateful_annotation(monkeypatch, stateful):
    d, inventory, _ = fixture(monkeypatch, annotation, policy=stateful == 'policy')

    def forbidden(*args):
        raise AssertionError('Stateful annotation must stay serial')

    seen = []
    callback = (lambda seed, proposal: seen.append(seed)) if stateful == 'callback' else None
    annotation.annotate(d, inventory, 'target', on_proposal=callback,
                        map_training=forbidden, map_folds=forbidden)
    assert len(seen if callback else d['numerical_policy'].receipt) == 6


def test_insufficient_distinct_geometry_stops_before_any_frequency_fit(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Insufficient timestamp support must skip RF fits")

    monkeypatch.setattr(annotation, "fit_training", forbidden)
    target = dict(track_id="target", track_index=0, current_large=True)
    track = dict(key="short", times=np.arange(4.0), values=np.arange(4.0))
    p = SimpleNamespace(members=[], flat_times=np.arange(300.0))
    d = dict(scan=SimpleNamespace(tracks=[track]), problems={"c0": (p, np.zeros(2))})
    result = annotation.annotate(d, dict(tracks=[target]), "target")
    assert result["result"]["geometry_only_early_exit"]
    assert result["result"]["annotation"]["status"] == "insufficient_partitions"
    assert result["result"]["no_accepted_associations"]
    assert not result["nominations"] and not result["attempts"]


def fixture(monkeypatch, module, *, policy=False, skip=False, unobservable=False):
    times = np.arange(20.0, dtype=float)
    track = dict(key="target", times=times, values=np.sin(times), rf_hz=11.5e9)
    target = dict(track_id="target", track_index=0, current_large=True)
    p = SimpleNamespace(members=[], flat_times=np.arange(30.0))
    scan = SimpleNamespace(
        tracks=[track],
        norads=np.array([100, 200]),
        sky=dict(
            time_s=np.arange(4.0),
            position_km=np.zeros((2, 4, 3)),
            velocity_km_s=np.zeros((2, 4, 3)),
        ),
        search_region=SimpleNamespace(latlon=lambda x: tuple(x)),
    )
    d = dict(scan=scan, problems={"c0": (p, np.zeros(2))}, keep=np.ones(30, bool), node={})
    if policy:
        d["numerical_policy"] = SimpleNamespace(receipt=[])
    seeds = [13, 9, 4]
    monkeypatch.setattr(module, "partition_schedule", lambda *a, **k: (seeds, {}))

    def split(full, focus, seed, plan):
        held = np.zeros(len(full), bool)
        held[-4:] = True
        if skip and seed == 9:
            held[:] = False
        return ~held, held, dict(seed=seed, target_held_indices=np.flatnonzero(held[30:]))

    monkeypatch.setattr(module, "planned_split", split)

    def fit(context, node, keep, arm):
        if policy:
            context["numerical_policy"].receipt.append((arm, keep.copy()))
        return p, np.zeros(2), dict(final_phase_change_s=0.0, seen=node.get("callbacks", 0))

    monkeypatch.setattr(module, "fit_training", fit)
    monkeypatch.setattr(
        module,
        "nominate",
        lambda *a: (
            [dict(candidate_index=j, phase_s=1.0, position=np.zeros(2)) for j in (0, 1)],
            dict(evidence="training only"),
        ),
    )
    monkeypatch.setattr(
        module, "paired_phase_frequency", lambda bank, tt, *a: (np.zeros(len(tt)), np.ones(len(tt)))
    )
    monkeypatch.setattr(module, "profile_rate", lambda *a: {"alias": np.array([0])})
    monkeypatch.setattr(module, "corrected", lambda *a: track["values"])

    def models(context, p, x, i, j, **kwargs):
        return (
            np.full((1, 20), float(j)),
            np.eye(20)[None],
            np.array([-np.inf if unobservable and j == 1 else 0.0]),
            np.array([1.0]),
            np.array([[20.0] * 20]),
            {"candidate": j},
        )

    monkeypatch.setattr(module, "prediction_models", models)
    monkeypatch.setattr(
        module,
        "mixture_prediction",
        lambda observed, means, *a: dict(
            training_mixture_weights=np.ones(1),
            negative_twice_log_density=float(means.sum()),
            rms_hz=10.0,
        ),
    )
    return d, dict(tracks=[target]), seeds


@pytest.mark.parametrize("skip,unobservable", [(False, False), (True, False), (False, True)])
def test_fold_port_preserves_oracle_results_even_when_computed_in_reverse(
    monkeypatch, skip, unobservable
):
    old, inventory, seeds = fixture(monkeypatch, oracle, skip=skip, unobservable=unobservable)
    expected = oracle.annotate(old, inventory, "target")
    current, inventory, _ = fixture(monkeypatch, annotation, skip=skip, unobservable=unobservable)
    calls = []

    def mapper(operation, values):
        assert list(values) == seeds
        answers = {}
        for seed in reversed(values):
            calls.append(seed)
            answers[seed] = operation(seed)
        return [answers[seed] for seed in values]

    actual = annotation.annotate(current, inventory, "target", map_folds=mapper)
    assert calls == list(reversed(seeds))
    assert fingerprint(actual) == fingerprint(expected)


@pytest.mark.parametrize("stateful", ["callback", "numerical_policy"])
def test_stateful_annotation_keeps_original_serial_effects(monkeypatch, stateful):
    outputs, receipts = [], []
    for module in (oracle, annotation):
        d, inventory, _ = fixture(monkeypatch, module, policy=stateful == "numerical_policy")

        def callback(seed, proposal, d=d):
            d["node"]["callbacks"] = d["node"].get("callbacks", 0) + 1
            proposal["callback_sequence"] = d["node"]["callbacks"]

        def forbidden(*args):
            raise AssertionError("Stateful callback/policy must keep serial execution")

        kwargs = dict(on_proposal=callback) if stateful == "callback" else {}
        if module is annotation:
            kwargs["map_folds"] = forbidden
        outputs.append(module.annotate(d, inventory, "target", **kwargs))
        receipts.append(d["node"] if stateful == "callback" else d["numerical_policy"].receipt)
    assert fingerprint(outputs[0]) == fingerprint(outputs[1])
    assert fingerprint(receipts[0]) == fingerprint(receipts[1])
