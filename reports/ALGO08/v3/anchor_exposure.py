"""Count signed receiver opportunities with chronology-preserving uncertainty."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from random import Random


SAMPLES = 2_000
SITE_WIDTHS = (128, 256)
STREAM_WIDTHS = (16, 32)
PINS = {
    "north": {
        "12ms": ("/dev/shm/leo-eight-ms-north/12ms", "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427"),
        "8ms": ("/dev/shm/leo-eight-ms-north/8ms", "a2eaf86c99145cc70b7040cf6e81c9fb0bc5e2e00b752223f5365de6818b8c49"),
        "stock": ("/tmp/leo-algo08v2-2x-bench/exact-curved-lookahead-north-inside/baseline",
                  "54ffd828f5cb9b09baa1d38e0f3fdff5b9e41954f74e60226e239fa5c6e4f1d8"),
    },
    "DS30-0016": {
        "12ms": ("/dev/shm/leo-eight-ms-DS30-0016-warm/12ms", "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
        "8ms": ("/dev/shm/leo-eight-ms-DS30-0016-warm/8ms", "f16ca1c684283a720596edfd727620a90f48712936f135c420d0c993ec669f6e"),
        "stock": ("/dev/shm/leo-v3-combined-frontier-weak-03/stock", "4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0"),
    },
    "DS30-0008": {
        "12ms": ("/dev/shm/leo-aperture-factor-position-02/prefix", "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"),
    },
}


def packet(folder, expected):
    path, = Path(folder).glob("fast-scan-automatic-work/*/detections.json")
    path = path.resolve(strict=True)
    if not path.is_relative_to("/dev/shm") and not path.is_relative_to("/tmp"):
        raise ValueError("The exposure census reads only pre-existing tmpfs packets")
    contents = path.read_bytes()
    if sha256(contents).hexdigest() != expected:
        raise ValueError(f"Unexpected saved detector bytes at {path}")
    return json.loads(contents)


def metadata(row):
    return {key: value for key, value in row.items() if key != "candidates"}


def positive(row):
    return any(factor["passed_fractional_margin_gate"] is True for factor in row["candidates"])


def bind(reference, candidate):
    identity = ("session_id", "input_manifest_sha256", "raw_recording_authority_digest")
    source, alternative = reference["source"], candidate["source"]
    if (any(source[key] != alternative[key] for key in identity)
            or any(reference[key] != candidate[key] for key in ("clock_anchor", "delivery_clocks"))
            or any(metadata(a) != metadata(b) for a, b in zip(source["probes"], alternative["probes"], strict=True))):
        raise ValueError("Receivers do not share identical signed opportunities")


def enroll(doc, reference=None):
    probes = doc["source"]["probes"]
    if reference is not None:
        bind(reference, doc)
    baseline = reference["source"]["probes"] if reference is not None else [None] * len(probes)
    counts = Counter()
    previous = -1
    for (a, b), (p, q) in zip(zip(probes[::2], probes[1::2], strict=True),
                            zip(baseline[::2], baseline[1::2], strict=True), strict=True):
        visit = a["visit_index"]
        if (visit <= previous or a["receiver_id"] != 0 or metadata(b) != dict(metadata(a), receiver_id=1)):
            raise ValueError("Expected complete chronological stereo visits")
        previous = visit
        stream = (a["edge"], a["channel"], a["actual_rf_hz"])
        index = counts[stream]
        counts[stream] += 1
        kind = "anchor" if index % 8 == 0 else "short"
        for row, other in ((a, p), (b, q)):
            passed = positive(row)
            stock = positive(other) if other is not None else False
            events = (1, int(passed), int(stock), int(passed and not stock), int(stock and not passed))
            yield (visit, index, row["receiver_id"], stream, kind, events)
    if (len(probes) != 2 * doc["provenance"]["processed_windows"]
            or doc["provenance"]["window_count"] != sum(counts.values()) + doc["provenance"]["invalid_capture"]):
        raise ValueError("Saved admitted-opportunity count differs")


def counts(rows, positions=None, width=None):
    blocks = defaultdict(lambda: [[0] * 5, [0] * 5])
    for visit, index, _radio, _stream, mode, events in rows:
        block = (visit if positions == "visit" else index) // width if width else 0
        counts_mode = blocks[block][int(mode == "short")]
        for i, flag in enumerate(events):
            counts_mode[i] += flag
    return [(tuple(a), tuple(s)) for _, (a, s) in sorted(blocks.items())]


def metrics(anchor, short, matched):
    a, s = anchor[1] / anchor[0], short[1] / short[0]
    stats = dict(anchor_rate=a, short_rate=s, short_minus_anchor=s-a)
    if matched:
        ea, es = a-anchor[2]/anchor[0], s-short[2]/short[0]
        stats.update(anchor_over_stock=ea, short_over_stock=es, relative_excess=es-ea)
    return stats


def interval(values):
    ordered = sorted(values)
    return (ordered[int(0.025 * (len(ordered)-1))], ordered[int(0.975 * (len(ordered)-1))])


def bootstrap(blocks, matched, seed):
    rng = Random(seed)
    columns = tuple(zip(*(a[:3]+s[:3] for a, s in blocks), strict=True))
    draws = defaultdict(list)
    for _ in range(SAMPLES):
        choice = rng.choices(range(len(blocks)), k=len(blocks))
        a, b, c, d, e, f = (sum(col[i] for i in choice) for col in columns)
        if a and d:
            for key, value in metrics((a, b, c), (d, e, f), matched).items():
                draws[key].append(value)
    return draws


def describe(rows, matched, positions, widths, site):
    (anchor, short), = counts(rows)
    names = ("opportunities", "pass", "stock_pass", "candidate_only", "stock_only")
    if not matched:
        names, anchor, short = names[:2], anchor[:2], short[:2]
    summary = dict(anchor=dict(zip(names, anchor, strict=True)), short=dict(zip(names, short, strict=True)),
                   point=metrics(anchor, short, matched), block={})
    draws_by_width = {}
    for width in widths:
        blocks = counts(rows, positions, width)
        draws = bootstrap(blocks, matched, f"anchor-exposure-1:{site}:{positions}:{width}")
        summary["block"][width] = dict(original_blocks=len(blocks), resamples=len(draws["short_minus_anchor"]),
                                       percentile95={key: interval(values) for key, values in draws.items() if values})
        draws_by_width[width] = draws
    return summary, draws_by_width


def census(rows, matched, site):
    radio, stream = defaultdict(list), defaultdict(list)
    for row in rows:
        radio[row[2]].append(row)
        stream[(row[2], *row[3])].append(row)
    totals, draws = describe(rows, matched, "visit", SITE_WIDTHS, site)
    by_radio = {str(key): describe(part, matched, "visit", SITE_WIDTHS, site)[0] for key, part in sorted(radio.items())}
    by_stream = [dict(receiver_id=key[0], edge=key[1], channel=key[2], actual_rf_hz=key[3],
                      **describe(part, matched, "stream", STREAM_WIDTHS, site)[0])
                 for key, part in sorted(stream.items())]
    return dict(all_streams=totals, by_radio=by_radio, by_stream=by_stream), draws


def contrasts(censuses, draws):
    result = {}
    for aperture in ("12ms", "8ms"):
        north = censuses["north"][aperture]
        comparisons = {}
        for site in ("DS30-0016", "DS30-0008") if aperture == "12ms" else ("DS30-0016",):
            other = censuses[site][aperture]
            key = "short_minus_anchor"
            comparisons[site] = dict(
                point=north["all_streams"]["point"][key]-other["all_streams"]["point"][key],
                by_radio={r: north["by_radio"][r]["point"][key]-other["by_radio"][r]["point"][key] for r in ("0", "1")},
                percentile95={w: interval(a-b for a, b in zip(draws["north"][aperture][w][key],
                                                                draws[site][aperture][w][key], strict=True))
                              for w in SITE_WIDTHS})
        north_widths = north["all_streams"]["block"].values()
        result[aperture] = dict(north_minus_compared=comparisons,
                               north_positive=all(b["percentile95"]["short_minus_anchor"][0] > 0 for b in north_widths),
                               north_excess_short_specific=all(b["percentile95"]["relative_excess"][0] > 0 for b in north_widths),
                               contrasts_positive=all(all(ci[0] > 0 for ci in row["percentile95"].values())
                                                      and min(row["by_radio"].values()) > 0 for row in comparisons.values()))
    return result


def run():
    output, draws = {}, {}
    for site, arms in PINS.items():
        sources = {name: packet(*entry) for name, entry in arms.items()}
        stock = sources.pop("stock", None)
        all_rows = {name: list(enroll(doc, stock)) for name, doc in sources.items()}
        if "8ms" in sources:
            bind(sources["12ms"], sources["8ms"])
            first, second = (sources[key]["source"]["probes"] for key in ("12ms", "8ms"))
            for opportunity, a, b in zip(all_rows["12ms"], first, second, strict=True):
                if opportunity[4] == "anchor" and a["candidates"] != b["candidates"]:
                    raise ValueError("The saved anchor factors changed across short apertures")
        output[site], draws[site] = {}, {}
        for aperture, rows in all_rows.items():
            output[site][aperture], draws[site][aperture] = census(rows, stock is not None, site)
    return dict(pins=PINS, cases=output, prespecified=contrasts(output, draws), bootstrap_samples=SAMPLES,
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    result = run()
    with args.receipt.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
