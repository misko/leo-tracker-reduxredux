"""Retrospective opposite-radio membership on archived native Graph pieces."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from statistics import fmean, median

from first30_native_agreement import DEVELOPMENT, ROWS_SHA, differences, enroll, positives
from signed_cfo_time_readout import FULL, PINS, RELEASE, bind_pair, canonical, document, graph, opportunities, qualified_candidate, read_native
from signed_cfo_time import SAMPLE_RATE


N_HELD = 8
MAX_GAP = 8*SAMPLE_RATE
MODE = {False: "full", True: "short"}


@dataclass(frozen=True)
class Sample:
    counter: int
    short: bool
    donor: dict
    installed: dict | None
    mixed: dict | None


def segments(points):
    segment = []
    for point in points:
        if segment and point.counter-segment[-1].counter > MAX_GAP:
            yield segment
            segment = []
        if segment and point.counter <= segment[-1].counter:
            raise ValueError("Original donor piece is not ordered")
        segment.append(point)
    if segment:
        yield segment


def calibration(points, start, stop, width):
    controls = [p for p in points if (not p.short and start+width < p.counter < stop-width
                                     and p.installed is not None and p.mixed is not None
                                     and canonical(p.installed) == canonical(p.mixed))]
    if len(controls) < 2 or controls[-1].counter-controls[0].counter < 2*SAMPLE_RATE:
        return None
    offsets = [differences(p.donor, p.installed) for p in controls]
    df, de = map(median, zip(*offsets, strict=True))
    if any(abs(f-df) > 250 or abs(e-de) > 2 for f, e in offsets):
        return None
    return df, de


def detected(donor, peak, offset):
    if peak is None:
        return False
    df, de = differences(donor, peak)
    return abs(df-offset[0]) <= 250 and abs(de-offset[1]) <= 2


def membership(source, offset):
    installed, mixed = (detected(source.donor, peak, offset) for peak in (source.installed, source.mixed))
    return ("both" if installed and mixed else "installed_only" if installed else "mixed_only" if mixed else "neither")


def edge_contrast(start, end):
    if sum(start.values()) != sum(end.values()) or not sum(start.values()):
        raise ValueError("Expected equal nonempty aperture exposures")
    return (end["mixed_only"]-end["installed_only"]-start["mixed_only"]+start["installed_only"])/sum(start.values())


def piece(points):
    start, stop = points[0].counter, points[-1].counter
    if len(points) < 8 or stop-start < MAX_GAP:
        return "short_piece", None
    width = min(4*SAMPLE_RATE, (stop-start)/4)
    offset = calibration(points, start, stop, width)
    if offset is None:
        return "unqualified_anchor_alignment", None
    report = {}
    for short in (False, True):
        first = [p for p in points if p.short == short and p.counter <= start+width]
        last = [p for p in reversed(points) if p.short == short and p.counter >= stop-width]
        paired = min(len(first), len(last))
        if not paired:
            continue
        beginnings = Counter(membership(p, offset) for p in first[:paired])
        endings = Counter(membership(p, offset) for p in last[:paired])
        report[MODE[short]] = dict(pairs=paired, start=beginnings, end=endings, contrast=edge_contrast(beginnings, endings),
                                  start_distance_s=[(p.counter-start)/SAMPLE_RATE for p in first[:paired]],
                                  end_distance_s=[(stop-p.counter)/SAMPLE_RATE for p in last[:paired]])
    return ("both_apertures" if len(report) == 2 else next(iter(report), "no_edges")), report


def evaluate_graph(native, observed, compare):
    if list(observed) != list(compare):
        raise ValueError("Target packet chronology differs")
    # Only the stock packet builds Graph; the result of replay touches neither
    # a selected satellite nor any target-radio alignment result.
    _, pieces, info = graph(native, observed)
    opposite = {(item["row"]["visit_index"], item["radio"]): oid for oid, item in observed.items()}
    recorded, census = [], Counter()
    for rows in pieces.values():
        track = []
        for donor in rows:
            oid = opposite[donor["row"]["visit_index"], 1-donor["radio"]]
            a, b = observed[oid], compare[oid]
            if donor["counter"] != a["counter"] or donor["short"] != a["short"]:
                raise ValueError("Donor and target aren't the same signed stereo visit")
            track.append(Sample(donor["counter"], a["short"], donor["factor"], a["factor"], b["factor"]))
        for part in segments(track):
            state, data = piece(part)
            census[state] += 1
            if data:
                recorded.append(dict(exposures=data, state=state, target_radio=1-rows[0]["radio"]))
    shared = [row["exposures"] for row in recorded if row["state"] == "both_apertures"]
    exposure = defaultdict(lambda: dict(start=Counter(), end=Counter()))
    for r in recorded:
        for mode, exp in r["exposures"].items():
            for label in ("all", "both_apertures") if r["state"] == "both_apertures" else ("all",):
                for edge in ("start", "end"):
                    exposure[f"{label}_{mode}"][edge].update(exp[edge])
    primary = fmean(s["short"]["contrast"]-s["full"]["contrast"] for s in shared) if shared else None
    components = {mode: fmean(s[mode]["contrast"] for s in shared) for mode in ("short", "full")} if shared else {}
    return dict(graph=info, piece_counts=census, exposure=dict(exposure), contrast=primary, component_contrasts=components,
                pieces=recorded)


def case_readout(pair):
    (stock_path, stock_row), (mixed_path, mixed_row) = (pair[role] for role in ("installed", "successor"))
    a, b = (document(p, row["attempt_result_sha256"]) for p, row in ((stock_path, stock_row), (mixed_path, mixed_row)))
    offer = b["raw_identity"]["region_sha256"]
    if a["authority_sha256"] != b["authority_sha256"] or a["raw_identity"] != b["raw_identity"]:
        raise ValueError("Native pair not from the same verified original request")
    stock = read_native(stock_path.parent / "publication", a["native_sha256"])
    pub = mixed_path.parent / "publication"
    raw = document(pub / "unified-short-bootstrap.json")
    mixed, _, _ = qualified_candidate(pub, raw, b["native_sha256"], offer)
    if stock["provenance"]["detector_sha256"] != "sha256:"+FULL:
        raise ValueError("Installed detector differs from the frozen original")
    for native in (stock, mixed):
        if any(len(positives(p)) > 1 for p in native["source"]["probes"]):
            raise ValueError("More than one retained native positive, outside the frozen Graph scope")
    left, right = opportunities(stock), opportunities(mixed)
    bind_pair(stock, mixed, left, right)
    observed_calls = Counter("short_primary" if r["short"] else "full" for r in right.values())
    if observed_calls != Counter(raw["receiver_audit"]["native"]["native_calls"]):
        raise ValueError("Actual native counts differ from the original aperture schedule")
    return dict(evaluate_graph(stock, left, right), packet_sha256=[a["native_sha256"], b["native_sha256"]])


def freeze_graph():
    from leo.analysis import glrt_frequency_input, graph_tracklets
    from leo.analysis.localization_v3 import tracks

    for module in (glrt_frequency_input, graph_tracklets, tracks):
        path = Path(module.__file__).resolve()
        rel = path.relative_to(RELEASE).as_posix()
        if sha256(path.read_bytes()).hexdigest() != PINS[rel]:
            raise ValueError("Actual source differs from the original Graph")


def evaluate(capture, ledger):
    freeze_graph()
    pairs, _ = enroll(capture, ledger)
    starts = {case: min(row["child_started_unix_ns"] for _, row in pair.values()) for case, pair in pairs.items()}
    held = sorted((case for case in pairs if starts[case] > starts[DEVELOPMENT]), key=starts.__getitem__)[:N_HELD]
    if len(held) != N_HELD:
        raise ValueError("Missing prespecified held recordings")
    cases = {case: case_readout(pairs[case]) for case in (DEVELOPMENT, *held)}
    estimates = [cases[c]["contrast"] for c in held if cases[c]["contrast"] is not None]
    interval = None
    if estimates:
        rng = Random(4581)
        draws = sorted(fmean(rng.choices(estimates, k=len(estimates))) for _ in range(4000))
        interval = [draws[100], draws[3899]]
    return dict(ledger_sha256=ROWS_SHA, graph_sources=PINS, development=DEVELOPMENT, held=held, cases=cases,
                held_contrast=fmean(estimates) if estimates else None, eligible_cases=len(estimates),
                case_bootstrap95=interval, passes=len(estimates) >= 5 and interval[0] > 0)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("capture", type=Path)
    cli.add_argument("ledger", type=Path)
    args = cli.parse_args()
    print(json.dumps(evaluate(args.capture, args.ledger), indent=2, sort_keys=True, allow_nan=False))
