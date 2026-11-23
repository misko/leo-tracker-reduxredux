"""Choose a whole short-receiver route using held full-anchor detection probabilities."""

import argparse
from collections import Counter, defaultdict
from math import log
from pathlib import Path
from random import Random
from time import perf_counter, process_time

from anchor_exposure import enroll, positive
from anchor_holds import erased_rows, history_rows


HERE = Path(__file__).resolve().parent
MEDIUM = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-short-raw-diagnostic-pairs/DS30-0057/candidate")
SOUTH = Path("/var/tmp/leo-full-short-south-transfer-final/containing")
CASES = {
    "north": (Path("/dev/shm/leo-eight-ms-north/12ms"),
              "sha256:2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427"),
    "DS30-0016": (Path("/dev/shm/leo-eight-ms-DS30-0016-warm/12ms"),
                  "sha256:c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
    "south": (SOUTH, "sha256:a10693d167757124a036cfcd63e90966760e52b755f4bb834605ccaf74426d2e"),
    "DS30-0057": (MEDIUM, "sha256:a9a0df0458963066bfcd11de0b22b23605ad44acdc3d3e628ccd8f40312064cd"),
}
REFERENCE = "b7585cb260661e4424d8be3d4eea0263f52f01ef2ad48e2f1719a037462419f3"
RADIOS = (0, 1)
ROUTES = ("unfiltered", "history")
BLOCKS = (128, 256)
DRAWS = 2_000


def original(case):
    from aperture_trial import read
    from discovery_margin import factor_weights
    from full_short_raw import RECIPE_SHA
    from full_short_run import checked_recipe
    from leo.contracts.digests import canonical_digest

    root, digest = CASES[case]
    (path,) = (root / "fast-scan-automatic-work").glob("*/detections.json")
    native = read(path)
    seal = read(root / "full-short-recipe.json")
    if (canonical_digest(native) != digest or native["provenance"]["detector_sha256"] != "sha256:" + RECIPE_SHA
            or not native["source"]["qualified"] or seal["saved_digest"] is not None or seal["recipe"] != checked_recipe()
            or seal["receiver_audit"]["selected"] != sum(factor_weights(native, unit=True)[1].values())):
        raise ValueError("Expected the genuine archived unfiltered mixed-aperture packet")
    return native


def predict(masked, history):
    cycles = defaultdict(list)
    for index, (visit, slot, radio, stream, _, events) in enumerate(enroll(masked)):
        cycles[radio, stream, slot // 8].append((index, visit, slot % 8, events[1], int(positive(history[index]))))
    predictions, incomplete = [], Counter()
    for (radio, stream, _), cycle in cycles.items():
        index, visit, slot, full_unfiltered, full_history = cycle[0]
        if slot or full_unfiltered or full_history:
            raise ValueError("Unmasked anchor reached the prediction stage")
        if len(cycle) != 8:
            incomplete[radio] += 1
            continue
        donors = cycle[1:]
        counts = dict(zip(ROUTES, (sum(row[i] for row in donors) for i in (3, 4)), strict=True))
        if counts["history"] > counts["unfiltered"]:
            raise ValueError("History selection created an unmeasured candidate")
        predictions.append(dict(index=index, visit=visit, radio=radio, stream=stream, n=len(donors), counts=counts,
                                probabilities={key: (value + .5) / (len(donors) + 1) for key, value in counts.items()}))
    return predictions, dict(incomplete)


def route(summary):
    return "history" if all(summary[radio]["delta_log_score"] > 0. for radio in RADIOS) else "unfiltered"


def score(predictions, observed):
    rows = []
    for prediction in predictions:
        outcome = int(positive(observed[prediction["index"]]))
        probabilities = prediction["probabilities"]
        scores = {name: log(p if outcome else 1. - p) for name, p in probabilities.items()}
        rows.append(dict(prediction, outcome=outcome, log_scores=scores,
                         delta_log_score=scores["history"] - scores["unfiltered"]))
    return rows


def summarize(rows):
    summary = {}
    for radio in RADIOS:
        held = [row for row in rows if row["radio"] == radio]
        reliability = {name: defaultdict(Counter) for name in ROUTES}
        for row in held:
            for name, k in row["counts"].items():
                reliability[name][k]["anchors"] += 1
                reliability[name][k]["positive"] += row["outcome"]
        summary[radio] = dict(held=len(held), positive=sum(row["outcome"] for row in held),
                              log_score={name: sum(row["log_scores"][name] for row in held) for name in ROUTES},
                              delta_log_score=sum(row["delta_log_score"] for row in held),
                              brier={name: (sum((row["outcome"] - row["probabilities"][name]) ** 2 for row in held) / len(held)
                                            if held else None) for name in ROUTES},
                              reliability={name: {k: dict(bins) for k, bins in strata.items()}
                                           for name, strata in reliability.items()})
    return summary


def block_calibration(rows, case, width):
    blocks = defaultdict(list)
    for row in rows:
        blocks[row["visit"] // width].append(row)
    totals = []
    for active in blocks.values():
        totals.append(tuple((sum(row["delta_log_score"] for row in active if row["radio"] == radio),
                             sum(row["radio"] == radio for row in active)) for radio in RADIOS))
    if not totals:
        return dict(blocks=0, draws=0, mean_delta_percentile95={}, fraction_both_radios_positive=None)
    rng = Random(f"anchor-cycle-route-1:{case}:{width}")
    diffs = defaultdict(list)
    jointly_positive = 0
    for _ in range(DRAWS):
        pairs = rng.choices(totals, k=len(totals))
        values = []
        for radio in RADIOS:
            total = sum(block[radio][0] for block in pairs)
            count = sum(block[radio][1] for block in pairs)
            values.append(total / count)
            diffs[radio].append(values[-1])
        jointly_positive += all(value > 0 for value in values)
    intervals = {}
    for radio, values in diffs.items():
        values.sort()
        intervals[radio] = [values[int(p * (len(values) - 1))] for p in (.025, .975)]
    return dict(blocks=len(totals), draws=DRAWS, mean_delta_percentile95=intervals,
                fraction_both_radios_positive=jointly_positive / DRAWS)


def select_route(document, *, audit=False):
    """Return the frozen choice with optional held-cycle evidence for the saved audit."""
    training, held = erased_rows(document)
    masked = dict(document, source=dict(document["source"], probes=training))
    history = history_rows(training)
    predictions, skips = predict(masked, history)
    if audit:
        from leo.contracts.digests import canonical_digest

        before_labels = canonical_digest(predictions)
    rows = score(predictions, document["source"]["probes"])
    totals = {radio: dict(delta_log_score=sum(row["delta_log_score"] for row in rows if row["radio"] == radio))
              for radio in RADIOS}
    result = dict(route=route(totals), log_score_gain_by_radio={radio: row["delta_log_score"] for radio, row in totals.items()})
    if audit:
        result.update(masked=canonical_digest(training), erased_history=canonical_digest(history),
                      prediction_digest=before_labels, held_before_partial_cycle_drop=len(held),
                      incomplete_cycles=skips, radio=summarize(rows), cycles=rows)
    return result


def cycle_audit(document, case):
    from leo.contracts.digests import canonical_digest
    from north_factor_swap import continued

    start = process_time(), perf_counter()
    selected = select_route(document)
    elapsed = dict(selector_cpu_s=process_time()-start[0], selector_elapsed_s=perf_counter()-start[1])
    restore_at = process_time(), perf_counter()
    restored = continued(document)
    elapsed.update(restore_cpu_s=process_time()-restore_at[0], restore_elapsed_s=perf_counter()-restore_at[1])
    detailed = select_route(document, audit=True)
    if any(detailed[name] != value for name, value in selected.items()):
        raise ValueError("Audit and timed selection disagree")
    elapsed["selected_total_cpu_s"] = elapsed["selector_cpu_s"] + (elapsed["restore_cpu_s"] if selected["route"] == "history" else 0.)
    return dict(detailed, input=canonical_digest(document), restored_history=canonical_digest(restored),
                block_calibration={width: block_calibration(detailed["cycles"], case, width) for width in BLOCKS}, clocks=elapsed)


def archived_outcome(assessment, case, archive):
    reference = archive["containing"][case]
    if assessment["input"] != reference["unfiltered_packet"]:
        raise ValueError("The preselected detector input differs from the archive")
    selected = assessment["route"]
    other = "history" if selected == "unfiltered" else "unfiltered"
    errors = reference[f"{selected}_error_km"]
    delta_v3 = [a-b for a, b in zip(errors, reference["installed_error_km"], strict=True)]
    delta_other = [a-b for a, b in zip(errors, reference[f"{other}_error_km"], strict=True)]
    omissions = {name: row for name, row in archive["missing"].items() if name.startswith(case + "_")}
    return dict(reference=reference, delta_selected_vs_v3_km=delta_v3, delta_selected_vs_other_km=delta_other,
                passes_250m=all(delta <= .25 for delta in delta_v3), dominated=all(delta > 0. for delta in delta_other),
                omissions=omissions)


def main(raw_scores, scored, cases):
    from aperture_trial import read, write
    from dense_full_short_raw import checked
    from dense_geographic_trial import host

    system = host()
    assessments = {case: cycle_audit(original(case), case) for case in cases}
    write(raw_scores, dict(machine=system, cases=assessments))
    archive = read(checked(HERE / "measurements/anchor-route-selector.json", REFERENCE))
    revealed = {case: archived_outcome(assessment, case, archive) for case, assessment in assessments.items()}
    write(scored, dict(machine=system, cases=assessments, reference_sha256=REFERENCE, revealed=revealed))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("raw_scores", type=Path)
    cli.add_argument("scored", type=Path)
    cli.add_argument("cases", choices=CASES, nargs="+")
    main(**vars(cli.parse_args()))
