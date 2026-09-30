"""Discovery-stable sign transfer and constrained frame-counter probes."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / "2026_09_29_ds10_signal_extension/local/paired"
OUT = BASE / "local"


def counter_templates(frames):
    templates, labels = [], []
    for period in (2, 4, 8, 16, 32, 64):
        for phase in range(period):
            for invert in (False, True):
                templates.append((((np.array(frames) + phase) % period) >= period / 2) ^ invert)
                labels.append((period, phase, invert))
    return np.array(templates), labels


def counter_audit(discovery, evaluation, train_frames, test_frames):
    train, labels = counter_templates(train_frames)
    test, _ = counter_templates(test_frames)
    frequency = discovery.mean(axis=0)
    active = (frequency >= .2) & (frequency <= .8)
    candidates = np.flatnonzero(active)
    if not len(candidates):
        return dict(abstention="No discovery-variable coordinates")
    fit = (train[:, :, None] == discovery[None, :, candidates]).mean(axis=1)
    winner = fit.argmax(axis=0)
    predicted = test[winner].T
    truth = evaluation[:, candidates]
    constant = frequency[candidates] >= .5
    scores = (predicted == truth).mean(axis=0) - (truth == constant).mean(axis=0)
    controls = []
    for shift in range(1, len(truth)):
        shifted = np.roll(truth, shift, axis=0)
        controls.append(float(((predicted == shifted).mean(axis=0)
                               - (shifted == constant).mean(axis=0)).max()))
    p = (1 + sum(v >= scores.max() for v in controls)) / (1 + len(controls))
    return dict(coordinates=candidates.tolist(),
                chosen_models=[labels[k] for k in winner],
                discovery_accuracy=fit[winner, np.arange(len(winner))].tolist(),
                heldout_accuracy=(predicted == truth).mean(axis=0).tolist(),
                improvement_over_frozen_constant=scores.tolist(),
                maximum_improvement=float(scores.max()), circular_maxima=controls,
                within_visit_maximum_p=p, across_three_visits_bonferroni_p=min(1., p * 3),
                limitation="Power-of-two square-wave probes use physical frame index; not a "
                "decoded counter. RX0 selects, later RX1 evaluates. Max controls over every "
                "discovery-variable coordinate. Too few frames for fine significance resolution.")


def main():
    OUT.mkdir(exist_ok=True)
    visits = []
    for path in sorted(SOURCE.glob("*/*-data-soft.npz")):
        summary = json.loads((path.parent / "summary.json").read_text())
        h = summary["header"]
        if "evaluation_frames" not in h:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == h["sha256"]
        with np.load(path) as data:
            assert np.array_equal(data["bins0"], data["bins1"])
            a, b = data["z0"][:, :6].real >= 0, data["z1"][:, :6].real >= 0
            bins = data["bins0"].tolist()
        train, test = h["discovery_frames"], h["evaluation_frames"]
        p, q = a[train].mean(axis=0), b[train].mean(axis=0)
        majority = p >= .5
        stable = (p <= .1) | (p >= .9)
        consensus = stable & ((q <= .1) | (q >= .9)) & (majority == (q >= .5))
        visits.append(dict(name=path.parent.name, sha256=digest, bins=bins, train=train, test=test,
                           a=a, b=b, majority=majority, stable=stable, consensus=consensus,
                           counter=counter_audit(a[train].reshape(len(train), -1),
                                                 b[test].reshape(len(test), -1), train, test)))
    stable_rows = []
    for donor in visits:
        for target in visits:
            assert donor["bins"] == target["bins"]
            for mode in ("stable", "consensus"):
                mask = donor[mode]
                scores = [(target[rx][target["test"]][:, mask]
                           == donor["majority"][mask]).mean() for rx in ("a", "b")]
                stable_rows.append(dict(donor=donor["name"], target=target["name"], mode=mode,
                                        positions=int(mask.sum()), frames=len(target["test"]),
                                        receiver_agreements=[float(s) for s in scores],
                                        coordinates=[(int(s + 2), donor["bins"][k])
                                                     for s, k in zip(*np.where(mask),
                                                                     strict=True)]))
    result = dict(stability=stable_rows,
                  counter=[dict(visit=v["name"], **v["counter"]) for v in visits],
                  sources={v["name"]: v["sha256"] for v in visits},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Stable signs can be universal template constants; transfer alone "
                  "is not identity. All three visits share a conditional candidate. Stable masks "
                  "selected on earlier frames only, applied without alignment or polarity search. "
                  "These are exploratory reused observations, not pristine confirmation.")
    (OUT / "within-visit.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in result["counter"]:
        print(r["visit"], "counter max", r["maximum_improvement"], "corrected p",
              r["across_three_visits_bonferroni_p"])
    for r in stable_rows:
        if r["mode"] == "consensus":
            print(r["donor"], r["target"], r["positions"], r["receiver_agreements"])


if __name__ == "__main__":
    main()
