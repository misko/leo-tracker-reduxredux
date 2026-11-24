"""Analyze fixed signed owner groups from authenticated saved receiver packets."""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from itertools import pairwise
import json
from math import fsum, isfinite, sqrt
from pathlib import Path
from statistics import fmean

from satellite_set_transfer import FIRST30, kendall, ledger
from signed_cfo_time import ARMS, MAX_GAP, SAMPLE_RATE, difference
from signed_cfo_time_readout import bind_pair, document, opportunities, owners, read_native, tag


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
FIELD = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
ENROLLMENT = Path("/tmp/leo-first30-native-ledger.aHNPOF")
CASES = ("DS30-0049", "DS30-0086", "DS30-0220")
DEVELOPMENT = "76ffa1841268d1f9dd8348a3549c8927655653abdcc804697b6a36f00aebf8ce"
FEATURES = "3a9547ed318c0a22b726e02a06adf161c144313f6ecbe0a781c9f23b06770c23"
INTERVENTIONS = {
    "matched-donor": "9e129a016bdd533d7c82706b402665bea6cd2d34c0628c0bda62fe414cae1a6a",
    "shifted-winner": "d5d07b8134c3a2e4c3f06745e6899f8ad02207b0997f5bab39332083887f3b87",
    "empty-recovery": "3e2a420f155cecc3193a13834122294230ec2de7aecd46fa75d06ec9881c4f38",
    "sparse-only-drop": "dcbc89c91c03b302343057f982207a90684c956e8d2d12e3d198119ebf1836bb",
}
HELD = {
    "DS30-0086": ("b6f0afe62a52313dd8b5aaddcbdb1cfb6f1bd14349752ed9bf2929f2ed7bf6f9",
                  "e98fac35839b13c3b002cc1ba53ce50111cb53f86e6bb735ca1985c1b89a6da9"),
    "DS30-0220": ("9d5baed1b5bac3791cda0340af30c9ea3123ab4ad719112e50ca4a9417e495ce",
                  "cbc1ae11c9a40f9d667bd45966d3dffc40b6c3b8d94a15fcdf9cbe38018a2455"),
}
CFO = "fractional_tracking_cfo_hz"
STREAM = ("edge", "channel", "actual_rf_hz")


def owner_groups(rows, lanes):
    result = defaultdict(list)
    for oid, (norad, role) in rows.items():
        lane = lanes[oid]
        if lane["factor"] is None or not isfinite(lane["factor"][CFO]):
            raise ValueError("Published owner has no finite signed native observation")
        group = (norad, role, lane["radio"], *(lane["row"][key] for key in STREAM))
        result[group].append(oid)
    return result


def pieces(ids, lanes):
    ordered = sorted(set(ids), key=lambda oid: lanes[oid]["counter"])
    cuts = [0] + [i for i, (left, right) in enumerate(pairwise(ordered), 1)
                  if lanes[right]["counter"] - lanes[left]["counter"] > MAX_GAP]
    for start, end in pairwise(cuts + [len(ordered)]):
        if start < end:
            yield ordered[start:end]


def proposals(groups, lanes):
    """Estimate signed CFO from bracketing anchors in the candidate packet alone."""
    result = {}
    for group in groups.values():
        for part in pieces(group, lanes):
            reference = [lanes[oid] for oid in part if not lanes[oid]["short"]]
            times = [row["counter"] for row in reference]
            for oid in part:
                lane = lanes[oid]
                t = lane["counter"]
                before, after = bisect_left(times, t)-1, bisect_right(times, t)
                if before < 0 or after == len(times) or max(t-times[before], times[after]-t) > MAX_GAP:
                    continue
                a, b = reference[before]["factor"][CFO], reference[after]["factor"][CFO]
                frequency = a + (b-a)*(t-times[before])/(times[after]-times[before])
                change = frequency-lane["factor"][CFO]
                if isfinite(change) and abs(change) <= 250:
                    result[oid] = .5 * change
    return result


def measure_cfo(groups):
    # Every group uses the same evaluation rows before and after correction.
    count = proposed = 0
    raw = centered = corrected = affine = slope_energy = 0.
    for group in groups:
        if len(group) < 3:
            continue
        times, deltas, corrections = zip(*group, strict=True)
        times = [(t-times[0])/SAMPLE_RATE for t in times]
        tc, fc = fmean(times), fmean(deltas)
        t = [x-tc for x in times]
        y = [v-fc for v in deltas]
        updated = [a+(b or 0.) for a, b in zip(deltas, corrections, strict=True)]
        cc = fmean(updated)
        d = [x-cc for x in updated]
        slope = fsum(a*b for a, b in zip(t, y, strict=True))/fsum(a*a for a in t)
        count += len(group)
        proposed += sum(c is not None for c in corrections)
        raw += fsum(x*x for x in deltas)
        centered += fsum(x*x for x in y)
        corrected += fsum(x*x for x in d)
        affine += fsum((v-slope*x)**2 for x, v in zip(t, y, strict=True))
        slope_energy += fsum((slope*x)**2 for x in t)
    return dict(rows=count, proposed=proposed, eligible_fraction=proposed/count if count else None,
                rms_hz=sqrt(raw/count) if count else None, centered_rms_hz=sqrt(centered/count) if count else None,
                corrected_centered_rms_hz=sqrt(corrected/count) if count else None,
                affine_residual_rms_hz=sqrt(affine/count) if count else None,
                centered_energy_explained_by_slope=slope_energy/centered if centered else None,
                centered_loss_gain=(centered-corrected)/centered if centered else None,
                qualifies=count > 0 and proposed >= 40 and proposed/count >= .1
                and centered > 0 and (centered-corrected)/centered >= .05)


def time_interval(part, members, lanes):
    ordered = [lanes[oid]["counter"] for oid in part if oid in members]
    return (ordered[0], ordered[-1]) if ordered else None


def group_readout(old, candidate, a, b):
    old_groups, new_groups = owner_groups(old, a), owner_groups(candidate, b)
    corrections = proposals(new_groups, b)
    strict, by_piece, held_anchors, discordance = [], [], [], []
    span = [0, 0, 0]
    counts = Counter()
    shared = old.keys() & candidate.keys()
    counts.update(added=len(candidate.keys()-old), removed=len(old.keys()-candidate),
                  shared_same_owner_role=sum(old[i] == candidate[i] for i in shared),
                  shared_changed_norad=sum(old[i][0] != candidate[i][0] for i in shared),
                  shared_changed_role=sum(old[i][1] != candidate[i][1] for i in shared))
    for key in sorted(old_groups.keys() | new_groups.keys()):
        left, right = set(old_groups.get(key, ())), set(new_groups.get(key, ()))
        for piece in pieces(left | right, a):
            x, y = time_interval(piece, left, a), time_interval(piece, right, b)
            counts["pieces"] += 1
            counts["paired_pieces"] += x is not None and y is not None
            span[0] += x[1]-x[0] if x else 0
            span[1] += y[1]-y[0] if y else 0
            span[2] += max(0, min(x[1], y[1])-max(x[0], y[0])) if x and y else 0
            retained = []
            for oid in piece:
                if oid not in left or oid not in right:
                    continue
                v, w = a[oid]["factor"], b[oid]["factor"]
                delta, _, close, _ = difference(v, w)
                correction = corrections.get(oid)
                if b[oid]["short"] and close:
                    counts["strict_short"] += 1
                    strict.append(delta)
                    retained.append((a[oid]["counter"], delta, correction))
                elif b[oid]["short"]:
                    counts["short_disagree"] += 1
                    discordance.append(delta)
                else:
                    counts["shared_anchors"] += 1
                    counts["shared_identical_anchor_factors"] += v == w
                    if v == w and correction is not None:
                        held_anchors.append(correction)
            by_piece.append(retained)
    union = span[0]+span[1]-span[2]
    strict_score = measure_cfo(by_piece)
    # The advancement denominator includes strict matches in short or singleton pieces.
    strict_score["fraction_of_all_strict"] = strict_score["proposed"]/len(strict) if strict else None
    strict_score["qualifies"] &= bool(strict and strict_score["fraction_of_all_strict"] >= .1)
    n_short_proposed = sum(b[oid]["short"] for oid in corrections)
    proposed_on_strict = sum(p is not None for group in by_piece for _, _, p in group)
    return dict(owner_rows=[len(old), len(candidate)], satellite_counts=[len({x[0] for x in r.values()})
                for r in (old, candidate)], counts=dict(counts), interval_seconds=[x/SAMPLE_RATE for x in span],
                interval_jaccard_loss=1-span[2]/union if union else None,
                strict_short_mean_hz=fmean(strict) if strict else None,
                strict_short_rms_hz=sqrt(fmean(x*x for x in strict)) if strict else None,
                discordant_short_rms_hz=sqrt(fmean(x*x for x in discordance)) if discordance else None,
                correction=strict_score, all_proposed_short=n_short_proposed,
                outside_strict_shared_short=n_short_proposed-proposed_on_strict,
                equal_anchor_controls=len(held_anchors),
                equal_anchor_new_rms_hz=sqrt(fmean(x*x for x in held_anchors)) if held_anchors else None)


def exact_changes(a, b, corrected, old, mixed, latest):
    count = Counter()
    for oid in a:
        x, y, z = (p[oid]["factor"] for p in (a, b, corrected))
        if y != z:
            count["changed_winners"] += 1
            if oid in latest:
                count["changed_now_owned"] += 1
        if oid in latest and old.get(oid) == latest[oid] and mixed.get(oid) != latest[oid]:
            count["restored_stock_owner"] += 1
            count["restored_with_exact_stock_tuple"] += x == z
    return dict(count)


def load_original(pair):
    sources = {}
    for label, (path, row) in pair.items():
        result = document(path, row["attempt_result_sha256"])
        pub = path.parent / "publication"
        if (result["algorithm"] != label or result["outcome"] != "complete"
                or result["evidence"]["receipt"]["terminal_sha256"] != row["terminal_sha256"]):
            raise ValueError("Original case no longer binds a completed publication")
        native = read_native(pub, result["native_sha256"])
        sources[label] = (result, pub, native, opportunities(native))
    x, y = (sources[x][0] for x in ("installed", "successor"))
    if x["raw_identity"] != y["raw_identity"]:
        raise ValueError("Field pair changed the signed source or offer")
    return sources


def evidence_rows(witness, native_pin, owner_pins):
    detail = witness["detail"]
    if (detail["input_sha256"] != native_pin
            or {arm: entry["owner_sha256"] for arm, entry in detail["arms"].items()} != owner_pins):
        raise ValueError("The saved selected rows belong to another detector input or owner map")
    return owners(witness["owner_rows"], owner_pins)


def compare_case(case, pair):
    sources = load_original(pair)
    stock, mixed = sources["installed"], sources["successor"]
    left, right = stock[0], mixed[0]
    a, b = stock[3], mixed[3]
    bind_pair(stock[2], mixed[2], a, b)
    witness = document(mixed[1] / "exact-named-raw-witness.json")["evidence"]
    if witness["detail"]["terminal_sha256"] != right["evidence"]["receipt"]["terminal_sha256"]:
        raise ValueError("Candidate ordered rows belong to another terminal")
    new = evidence_rows(witness, right["native_sha256"], right["evidence"]["owners"])
    if case == CASES[0]:
        control = document(MEASUREMENTS / "ds30-0049-saved-crossover.json.gz", DEVELOPMENT)
        archived = control["cells"]["successor-installed"]
        if archived["native_sha256"] != left["native_sha256"] or any(
                archived["arms"][arm]["owner_sha256"] != left["evidence"]["owners"][arm] for arm in ARMS):
            raise ValueError("The same-solver control does not reproduce installed/full")
        old = owners(control["ordered_owner_rows"]["successor-installed"], left["evidence"]["owners"])
    else:
        pin, _ = HELD[case]
        receipt = document(MEASUREMENTS / f"field-installed-packet-saved-{case[-4:]}.json", pin)
        claim = receipt["source_artifacts"]["candidate_witness"]
        candidate_witness = document(Path(claim["path"]), claim["sha256"])["evidence"]
        if receipt["native_sha256"] != left["native_sha256"] or not all(receipt["exact_owner_map"].values()):
            raise ValueError("The held full packet lacks a verified exact owner-map crossover")
        old = evidence_rows(candidate_witness, left["native_sha256"], left["evidence"]["owners"])
    result = dict(native_sha256=[left["native_sha256"], right["native_sha256"]],
                  owner_sha256=[left["evidence"]["owners"], right["evidence"]["owners"]],
                  arms={arm: group_readout(old[arm], new[arm], a, b) for arm in ARMS})
    variants = {}
    if case == CASES[0]:
        for name, pin in INTERVENTIONS.items():
            receipt_name = "shifted-winner-repair" if name == "shifted-winner" else name
            saved = document(MEASUREMENTS / f"ds30-0049-{receipt_name}.json.gz", pin)
            (path,) = Path(f"/dev/shm/leo-v3-{name}-0049-01/substituted/fast-scan-automatic-work").glob("*/detections.json")
            native_pin = saved["receipt"]["input"]
            variant = document(path, native_pin)
            modified = opportunities(variant)
            bind_pair(stock[2], variant, a, modified)
            evidence = saved["witness"]["evidence"]
            owner_pins = {arm: entry["owner_sha256"] for arm, entry in evidence["detail"]["arms"].items()}
            changed = evidence_rows(evidence, native_pin, owner_pins)
            variants[name] = dict(native_sha256=native_pin, owner_sha256=owner_pins, arms={})
            for arm in ARMS:
                info = group_readout(old[arm], changed[arm], a, modified)
                info["intervention"] = exact_changes(a, b, modified, old[arm], new[arm], changed[arm])
                variants[name]["arms"][arm] = info
    return result, variants


def readout():
    pairs = ledger(ENROLLMENT, FIELD, 30, FIRST30)
    results, variants = {}, {}
    for case in CASES:
        results[case], interventions = compare_case(case, pairs[case])
        variants.update(interventions)
    return dict(protocol_sha256=tag((HERE / "owner-path-correction-protocol.md").read_bytes()),
                cases=results, variants_0049=variants, advances=all(results[case]["arms"][arm]["correction"]["qualifies"]
                for case in HELD for arm in ARMS))


def geographic_score(path):
    seal = document(path, FEATURES)
    cases, variants = {}, {}
    source = document(MEASUREMENTS / "ds30-0049-saved-crossover.json.gz", DEVELOPMENT)["cells"]
    cases[CASES[0]] = {arm: {name: source[cell]["arms"][arm]["error_m"] for name, cell in (
        ("installed/full", "installed-installed"), ("installed/mixed", "installed-successor"),
        ("charted/full", "successor-installed"), ("charted/mixed", "successor-successor"))} for arm in ARMS}
    for case, (_, pin) in HELD.items():
        prior = document(MEASUREMENTS / f"field-receiver-solver-cross-{case[-4:]}.json.gz", pin)
        cases[case] = {arm: {cell: 1_000*error for cell, error in prior["score"]["arms"][arm]["error_km"].items()}
                       for arm in ARMS}
    for name, pin in INTERVENTIONS.items():
        receipt_name = "shifted-winner-repair" if name == "shifted-winner" else name
        saved = document(MEASUREMENTS / f"ds30-0049-{receipt_name}.json.gz", pin)
        variants[name] = {arm: saved["score"]["arms"][arm]["counterfactual_m"] for arm in ARMS}
    changes = {case: {arm: {solver: rows[solver+"/mixed"]-rows[solver+"/full"] for solver in ("installed", "charted")}
                      for arm, rows in trend.items()} for case, trend in cases.items()}
    predictors = {arm: {} for arm in ARMS}
    for arm in ARMS:
        rows = {case: entry["arms"][arm] for case, entry in seal["cases"].items()}
        series = dict(absolute_owner_count_delta={c: abs(r["owner_rows"][1]-r["owner_rows"][0]) for c,r in rows.items()},
                      interval_jaccard_loss={c: r["interval_jaccard_loss"] for c,r in rows.items()},
                      centered_cfo_rms={c: r["correction"]["centered_rms_hz"] for c,r in rows.items()})
        for name, x in series.items():
            predictors[arm][name] = {solver: kendall([(x[case], changes[case][arm][solver]) for case in CASES])
                                     for solver in ("installed", "charted")}
    return dict(features_sha256=FEATURES, error_m=cases, localizations_0049_interventions_m=variants,
                receiver_effect_m=changes, descriptive_ranks=predictors, advances=seal["advances"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, help="Add archived outcomes to the exact sealed feature receipt")
    args = parser.parse_args()
    print(json.dumps(geographic_score(args.score) if args.score else readout(), indent=2, sort_keys=True,
                     allow_nan=False))
