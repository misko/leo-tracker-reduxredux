"""Case-held signed peak agreement on the original field receiver packets."""

import argparse
from collections import Counter, defaultdict, deque
from math import isfinite, sqrt
from pathlib import Path
from random import Random
from statistics import fmean, median
import json

from signed_cfo_time_readout import FULL, SPARSE, canonical, document, tag
from within_aperture_chirp import RATE, SLOPE_STRESS, exposure


ROWS_SHA = "2994fe3bd068dc661fb7c4a6f9667e370218acae226106f7dd0b05636d71f8c5"
SEAL_SHA = "84fc1193f55485f66a20b703fc52540fb8c94301937769759e4ed07a75b3af92"
DEVELOPMENT = "DS30-0049"
COHORT_BYTES_LIMIT = 256 * 1024**2
LANE = ("edge", "channel", "actual_rf_hz")
RULE = ["full"] + ["short_primary"] * 7
CFO = "fractional_tracking_cfo_hz"
INTEGER = "integer_epoch_sample"
FRACTION = "fractional_epoch_offset_samples"


def differences(stock, mixed):
    return mixed[CFO] - stock[CFO], (mixed[INTEGER] - stock[INTEGER]) + (mixed[FRACTION] - stock[FRACTION])


def match(stock, mixed):
    """Pair only edges unique on both sides of the signed peak graph."""
    left, right, edges = Counter(), Counter(), []
    for i, a in enumerate(stock):
        for j, b in enumerate(mixed):
            df, de = differences(a, b)
            if abs(df) <= 250 and abs(de) <= 2:
                left[i] += 1
                right[j] += 1
                edges.append((i, j, df, de))
    unique = [(stock[i], mixed[j], df, de) for i, j, df, de in edges if left[i] == right[j] == 1]
    counts = dict(matched=len(unique), installed_only_peaks=len(stock)-len(left), mixed_only_peaks=len(mixed)-len(right),
                  ambiguous_installed_peaks=len(left)-len(unique), ambiguous_mixed_peaks=len(right)-len(unique))
    return unique, counts


def positives(row):
    result = [f for f in row["candidates"] if f["passed_fractional_margin_gate"] is True]
    if any(not all(isfinite(f[k]) for k in (CFO, INTEGER, FRACTION)) for f in result):
        raise ValueError("Nonfinite retained peak")
    return result


def prediction(factor, counter, short, rf, preceding):
    t = exposure(factor, short).centroid
    relative = t - exposure(factor, False).centroid
    timing = RATE * relative * (factor[CFO] / rf)
    frequency = None
    if len(preceding) == 2:
        (a, ta, fa), (b, tb, fb) = preceding
        gap, age = (b-a)/RATE + (tb-ta), (counter-b)/RATE + (t-tb)
        if 0 < gap and 0 < age and gap+age <= 8:
            rate = (fb-fa) / gap
            if abs(rate) <= SLOPE_STRESS and abs(factor[CFO]-fb) <= SLOPE_STRESS*age + 250:
                frequency = rate * relative
    return frequency, timing, t


def compare(left, right, expected):
    counts = {a: Counter() for a in ("anchor", "short")}
    cadence, history = Counter(), defaultdict(lambda: deque(maxlen=2))
    offsets, frames = defaultdict(list), Counter()
    prior = None
    if len(left) != len(right) or len(left) % 2:
        raise ValueError("Original stereo inventory differs")
    for i, (first, second) in enumerate(zip(left, right, strict=True)):
        if {k: v for k, v in first.items() if k != "candidates"} != {k: v for k, v in second.items() if k != "candidates"}:
            raise ValueError("Original signed RF or sample opportunity differs")
        key = tuple(second[k] for k in LANE)
        radio, counter = second["receiver_id"], second["valid_start_counter"]
        visit = second["visit_index"], key, counter
        if radio != i % 2 or (radio == 1 and visit != prior):
            raise ValueError("Chronology lost its stereo visit pairing")
        if radio == 0:
            if prior is not None and counter <= prior[2]:
                raise ValueError("Native hardware visits are not strictly ordered")
            prior = visit
            short = cadence[key] % 8 != 0
            cadence[key] += 1
        cohort = counts["short" if short else "anchor"]
        cohort["lanes"] += 1
        a, b = positives(first), positives(second)
        cohort["installed_peaks"] += len(a)
        cohort["mixed_peaks"] += len(b)
        side = "both_positive" if a and b else "installed_only_lanes" if a else "mixed_only_lanes" if b else "both_empty"
        cohort[side] += 1
        matches, coverage = match(a, b)
        cohort.update(coverage)
        cohort["both_positive_without_unique_match"] += bool(a and b and not matches)
        cohort["exact_native_factors"] += sum(canonical(x) == canonical(y) for x, y, _, _ in matches)
        stream = (radio, *key)
        h = history[stream]
        p_hz, p_epoch = None, None
        if len(b) == 1:
            p_hz, p_epoch, t = prediction(b[0], counter, short, key[-1], h)
            h.append((counter, t, b[0][CFO]))
        elif len(b) > 1:
            h.clear()
        if short:
            for x, y, df, de in matches:
                frames[f"{len(exposure(x, False).centres)}/{len(exposure(y, True).centres)}"] += 1
                # Timing is defined for every matched positive using its own mixed peak.
                if p_epoch is None:
                    _, p_epoch_row, _ = prediction(y, counter, True, key[-1], ())
                else:
                    p_epoch_row = p_epoch
                offsets[stream].append((df, de, p_hz, p_epoch_row))
    if (counts["anchor"]["lanes"] != expected.get("full", 0)
            or counts["short"]["lanes"] != expected.get("short_primary", 0)):
        raise ValueError("Reconstructed apertures differ from paid native calls")
    for c in counts.values():
        for role in ("installed", "mixed"):
            if c[role+"_peaks"] != c["matched"] + c[role+"_only_peaks"] + c["ambiguous_"+role+"_peaks"]:
                raise ValueError("Unaccounted positive factor")
    return counts, offsets, frames


def losses(offsets, observed_col, predicted_col, grouping):
    samples = defaultdict(list)
    for group, rows in offsets.items():
        key = (group[0],) if grouping == "radio" else group if grouping == "stream" else ()
        samples[key].extend((row[observed_col], row[predicted_col]) for row in rows if row[predicted_col] is not None)
    a, ap, pp = 0., 0., 0.
    n = 0
    for points in samples.values():
        if not points:
            continue
        x, y = zip(*points, strict=True)
        xc, yc = (fmean(x), fmean(y)) if grouping != "raw" else (0., 0.)
        a += sum((v-xc)**2 for v in x)
        ap += sum((v-xc)*(w-yc) for v, w in points)
        pp += sum((w-yc)**2 for w in y)
        n += len(points)
    return dict(n=n, groups=sum(bool(v) for v in samples.values()), baseline_loss=a, cross=ap, predictor_energy=pp)


def signed_score(scope, sign):
    base, cross, power = (scope[k] for k in ("baseline_loss", "cross", "predictor_energy"))
    gain = 2*sign*cross-power
    return dict(scope, sign=sign, gain=gain, fractional_gain=gain/base if base else None,
                rms_before=sqrt(base/scope["n"]) if scope["n"] else None,
                rms_after=sqrt(max(0., base-gain)/scope["n"]) if scope["n"] else None)


def summarize(offsets, sign):
    stats = {}
    for j, name in enumerate(("cfo_hz", "epoch_samples")):
        radios = {}
        for rx in (0, 1):
            x = [row[j] for stream, points in offsets.items() if stream[0] == rx for row in points]
            if x:
                mean = fmean(x)
                radios[str(rx)] = dict(n=len(x), mean=mean, median=median(x), rms=sqrt(fmean(v*v for v in x)),
                                      centred_rms=sqrt(fmean((v-mean)**2 for v in x)), exact_zero=sum(v == 0 for v in x))
        stats[name] = dict(radios=radios, tests={group: signed_score(losses(offsets, j, j+2, group), sign[name])
                                               for group in ("raw", "radio", "stream")})
    return stats


def pool(cases, name, group, sign):
    scoped = [c["score"][name]["tests"][group] for c in cases]
    usable = [c for c in scoped if c["baseline_loss"] > 0]
    combined = {k: sum(c[k] for c in scoped) for k in ("n", "groups", "baseline_loss", "cross", "predictor_energy")}
    aggregate = signed_score(combined, sign)
    rng = Random(417)
    interval = None
    if usable:
        draws = [rng.choices(usable, k=len(usable)) for _ in range(2000)]
        distribution = sorted(sum(c["gain"] for c in s)/sum(c["baseline_loss"] for c in s) for s in draws)
        interval = [distribution[50], distribution[1949]]
    return dict(aggregate, cases=len(usable), improved_cases=sum(c["gain"] > 0 for c in usable), case_bootstrap95=interval)


def enroll(capture, ledger):
    seal = document(ledger / "rows-with-relocations-seal.json", SEAL_SHA)
    body = (ledger / "rows-with-relocations.jsonl").read_bytes()
    if tag(body) != seal["combined_sha256"] or tag(body) != "sha256:"+ROWS_SHA:
        raise ValueError("Immutable first-30 field rows changed")
    groups = defaultdict(dict)
    for line in body.splitlines():
        row = json.loads(line)
        if row["verified_pair"] is not True:
            continue
        path = Path(row["attempt"])
        if path.is_absolute() or ".." in path.parts or path.name != "result.json" or row["algorithm"] in groups[row["case"]]:
            raise ValueError("Unexpected verified result path or pair member")
        groups[row["case"]][row["algorithm"]] = (capture / path, row)
    if len(groups) != 30 or any(set(pair) != {"installed", "successor"} for pair in groups.values()):
        raise ValueError("Need exactly 30 original pairs")
    total = 0
    for pair in groups.values():
        for path, _ in pair.values():
            native, = (path.parent / "publication/fast-scan-automatic-work").glob("*/detections.json")
            total += native.stat().st_size
    if total > COHORT_BYTES_LIMIT:
        raise ValueError("Original packet census exceeds the predeclared metadata read allowance")
    return groups, total


def read_case(case, pair):
    full, mixed = [], []
    for role, target in (("installed", full), ("successor", mixed)):
        path, row = pair[role]
        result = document(path, row["attempt_result_sha256"])
        pub = path.parent / "publication"
        native_path, = (pub / "fast-scan-automatic-work").glob("*/detections.json")
        native = document(native_path, result["native_sha256"])
        source, detector = native["source"], native["provenance"]["detector_sha256"]
        auth = result["raw_identity"]
        if (result["algorithm"] != role or result["outcome"] != row["outcome"] or source["sample_rate_hz"] != RATE
                or source["session_id"] != auth["session_id"] or source["input_manifest_sha256"] != auth["inventory_sha256"]
                or source["raw_recording_authority_digest"] != auth["raw_authority_sha256"]
                or source["analysis_manifest_sha256"] != canonical(["cancellation", auth["raw_authority_sha256"], detector[7:], source["probes"]])):
            raise ValueError(f"Unbound native receiver packet: {case}")
        target.extend((result, native, detector, pub))
    f_result, a, detector, _ = full
    m_result, b, mixed_detector, pub = mixed
    raw = document(pub / "unified-short-bootstrap.json")
    held, native_audit = raw["held_anchor_route"], raw["receiver_audit"]["native"]
    recipe = held["receiver_recipe"]
    if (f_result["raw_identity"] != m_result["raw_identity"] or f_result["authority_sha256"] != m_result["authority_sha256"]
            or detector != "sha256:"+FULL or mixed_detector != canonical(recipe)
            or recipe["installed_sha256"] != FULL or recipe["shortened_sha256"] != SPARSE
            or recipe["streams"] != list(LANE) or recipe["rule"] != RULE or native_audit["rule"] != RULE
            or recipe["aperture_samples"] != [200_000, 80_000] or held["refinement_calls"]
            or recipe["held_native_8ms"]["measurement"] != "original signed 8 ms native CFO, no subsequent fixed-epoch 20 ms remeasurement"
            or held["native_sha256"] != m_result["native_sha256"]
            or held["selected"] != sum(len(p["candidates"]) for p in b["source"]["probes"])
            or any(a[key] != b[key] for key in ("clock_anchor", "delivery_clocks", "last_sample_counter"))
            or a["provenance"]["excluded_windows"] != b["provenance"]["excluded_windows"]):
        raise ValueError(f"Original receiver identity, aperture, clocks or acquisition differs: {case}")
    counts, offsets, frames = compare(a["source"]["probes"], b["source"]["probes"], native_audit["native_calls"])
    return dict(case=case, counts=counts, frames=frames, choice=held["choice"]["route"],
                selection={k: held[k] for k in ("observed", "selected", "refinement_calls")},
                native_sha256=dict(installed=f_result["native_sha256"], mixed=m_result["native_sha256"]),
                raw_authority_sha256=m_result["raw_identity"]["raw_authority_sha256"]), offsets


def evaluate(capture, ledger):
    pairs, size = enroll(capture, ledger)
    development, rows = read_case(DEVELOPMENT, pairs[DEVELOPMENT])
    signs = {name: -1 if losses(rows, i, i+2, "radio")["cross"] < 0 else 1
             for i, name in enumerate(("cfo_hz", "epoch_samples"))}
    development.update(score=summarize(rows, signs), role="development")
    clocks = {case: min(row["child_started_unix_ns"] for _, row in pair.values()) for case, pair in pairs.items()}
    cases = []
    for case in sorted(pairs, key=clocks.__getitem__):
        if case == DEVELOPMENT:
            cases.append(development)
            continue
        result, rows = read_case(case, pairs[case])
        role = "held" if clocks[case] > clocks[DEVELOPMENT] else "earlier_smoke"
        cases.append(dict(result, role=role, score=summarize(rows, signs)))
    held = [r for r in cases if r["role"] == "held"]
    totals = {scope: dict(sum((Counter(r["counts"][scope]) for r in cases), Counter())) for scope in ("anchor", "short")}
    return dict(rows_sha256=ROWS_SHA, native_bytes=size, learned_signs=signs, counts=totals, cases=cases,
                held={name: {group: pool(held, name, group, sign) for group in ("raw", "radio", "stream")}
                      for name, sign in signs.items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.capture, args.ledger), sort_keys=True, indent=2, allow_nan=False))
