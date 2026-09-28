"""All-pairs bit-pattern and signal-distribution comparisons; descriptive clustering."""
# ruff: noqa: E501

import base64
import csv
import hashlib
import html
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import jensenshannon, squareform

BASE = Path(__file__).parent
OUT = BASE / "local"
JOINT = BASE.parent / "2026_09_28_ds7_ds8_correspondence"


def canonical(word):
    if len(word) != 60 or set(word) - {"0", "1"}:
        raise ValueError("Only complete 60-bit words can enter clustering")
    inverted = word.translate(str.maketrans("01", "10"))
    return min(w[i:] + w[:i] for w in [word, inverted] for i in range(60))


def hamming(a, b):
    return sum(x != y for x, y in zip(a, b, strict=True))


def family_distance(a, b):
    distances = [hamming(a, b[k:] + b[:k]) for k in range(60)]
    return min(min(distances), 60 - max(distances))


def distribution_distance(a, b):
    """Base-2 Jensen-Shannon distance; empty input is missing evidence, not zero."""
    if not a or not b:
        return None
    keys = sorted(set(a) | set(b))
    return float(jensenshannon([a.get(k, 0) for k in keys], [b.get(k, 0) for k in keys], base=2))


def csv_write(path, rows, fields=None):
    with path.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def qualifies_word(row):
    """Historical T-code gates; stricter pilot gate is retained separately."""
    return bool(
        row.get("shared") == 60
        and row.get("word") == row.get("peer_word")
        and len(row["word"]) == 60
        and not set(row["word"]) - {"0", "1"}
        and row["selection"] > 0.25
        and row["held"] > 0.25
        and row["held"] > row["wrong_max"]
    )


def matrix_csv(path, names, matrix):
    with path.open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", *names])
        for name, row in zip(names, matrix, strict=True):
            writer.writerow([name, *["" if not np.isfinite(x) else float(x) for x in row]])


def distance_hierarchy(matrix, labels, method="average"):
    """Validate distances explicitly; never fill missing evidence with zero."""
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (len(labels), len(labels)) or len(set(labels)) != len(labels):
        raise ValueError("A square distance matrix and unique matching labels are required")
    if not np.isfinite(matrix).all() or (matrix < 0).any():
        raise ValueError("Distances must be finite and nonnegative")
    if not np.allclose(matrix, matrix.T, atol=1e-12, rtol=0):
        raise ValueError("Distances must be symmetric")
    if not np.allclose(np.diag(matrix), 0, atol=1e-12, rtol=0):
        raise ValueError("Self distances must be zero")
    if method not in {"average", "complete", "single", "weighted"}:
        raise ValueError("This distance API does not establish Euclidean geometry for Ward")
    if len(labels) < 2:
        return np.empty((0, 4))
    matrix = (matrix + matrix.T) / 2
    np.fill_diagonal(matrix, 0)
    return linkage(squareform(matrix), method=method, optimal_ordering=True)


def clustered_plot(matrix, labels, path, title, maximum=1, method="average"):
    import matplotlib.pyplot as plt

    matrix = np.asarray(matrix, dtype=float)
    hierarchy = distance_hierarchy(matrix, labels, method)
    if len(labels) < 2:
        fig, ax = plt.subplots(figsize=(9, 3))
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            "Insufficient visits for clustering\n" + ", ".join(labels),
            ha="center",
            va="center",
        )
        fig.suptitle(title)
        fig.savefig(path, dpi=160)
        plt.close(fig)
        return []
    fig = plt.figure(figsize=(14, max(7, len(labels) * 0.28)), layout="constrained")
    grid = fig.add_gridspec(1, 2, width_ratios=[1, 2])
    ax = fig.add_subplot(grid[0])
    tree = dendrogram(
        hierarchy,
        labels=labels,
        orientation="left",
        ax=ax,
        color_threshold=0,
        above_threshold_color="#315a80",
        leaf_font_size=8,
    )
    # SciPy's left-oriented leaves run bottom to top; imshow rows run top to bottom.
    order = tree["leaves"][::-1]
    ax.set_xlabel(f"{method.capitalize()}-linkage distance")
    ax2 = fig.add_subplot(grid[1])
    im = ax2.imshow(
        matrix[np.ix_(order, order)], vmin=0, vmax=maximum, cmap="viridis_r", aspect="auto"
    )
    ax2.set_xticks(range(len(order)), [labels[i] for i in order], rotation=90, fontsize=7)
    ax2.set_yticks(range(len(order)), [labels[i] for i in order], fontsize=7)
    fig.colorbar(im, ax=ax2, shrink=0.65)
    fig.suptitle(title, fontsize=12)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return hierarchy.tolist()


def main():
    import matplotlib

    matplotlib.use("Agg")
    inventory = json.loads((OUT / "inventory.json").read_text())
    signals, observations, inputs, header = [], [], [OUT / "inventory.json"], {}
    for visit in inventory:
        path = OUT / (visit["signal"] + ".json")
        result = json.loads(path.read_text())
        inputs.append(path)
        rates = {s["row"]["sample_rate_hz"] for s in visit["streams"]}
        assert len(rates) == 1
        accepted = [r for r in result["results"] if qualifies_word(r)]
        signals.append(
            dict(
                signal=visit["signal"],
                session=visit["session"],
                visit=visit["visit"],
                edge=visit["edge"],
                rate_hz=rates.pop(),
                norad_id=visit["norad_id"],
                receivers=len(visit["streams"]),
                attempted=len(result["results"]),
                accepted=len(accepted),
                status=result.get("error")
                or (
                    "verified words"
                    if accepted
                    else "single RX; provisional"
                    if len(visit["streams"]) == 1
                    else "no qualified full words"
                ),
            )
        )
        for r in result["results"]:
            observations.append(
                dict(
                    signal=visit["signal"],
                    frame=r["frame"],
                    status="paired T-code gates" if qualifies_word(r) else r["status"],
                    accepted=qualifies_word(r),
                    strict_pilot_accepted=r["accepted"],
                    word=r["word"],
                    family=canonical(r["word"]) if qualifies_word(r) else "",
                    selection=r["selection"],
                    held=r.get("held", ""),
                )
            )
        header[visit["signal"]] = {r["key"]: r["bit"] for r in result.get("header_features", [])}
    utpath = JOINT / "local/ut-codebook/comparison.json"
    inputs.append(utpath)
    ut = json.loads(utpath.read_text())["accepted"]
    signals.append(
        dict(
            signal="UT-ref",
            session="published hard symbols",
            visit="",
            edge="two central slices",
            rate_hz="",
            norad_id=None,
            receivers="reference",
            attempted=1009,
            accepted=len(ut),
            status="published symbols; frequency-held-out check",
        )
    )
    signals.append(
        dict(
            signal="UT-IQ",
            session="raw UT frames 250–256",
            visit="",
            edge="full band",
            rate_hz=250000000,
            norad_id=None,
            receivers=1,
            attempted=7,
            accepted=0,
            status="prior demodulation verified; no qualified long T-code block; header not semantically decoded",
        )
    )
    for r in ut:
        observations.append(
            dict(
                signal="UT-ref",
                frame=r["frame"],
                status="reference",
                accepted=True,
                strict_pilot_accepted=False,
                word=r["word"],
                family=canonical(r["word"]),
                selection=r["selection"],
                held=r["held"],
            )
        )
    accepted = [r for r in observations if r["accepted"]]
    words = sorted({r["word"] for r in accepted})
    families = sorted({canonical(w) for w in words})
    word_ids = {w: f"W{i + 1:03}" for i, w in enumerate(words)}
    family_ids = {w: f"F{i + 1:03}" for i, w in enumerate(families)}
    for r in observations:
        r["word_id"] = word_ids.get(r["word"], "") if r["accepted"] else ""
        r["family_id"] = family_ids.get(r["family"], "")
    lookup = []
    utwords = {r["word"] for r in ut}
    utfamilies = {canonical(w) for w in utwords}
    for w in words:
        matched = [r for r in accepted if r["word"] == w]
        lookup.append(
            dict(
                word_id=word_ids[w],
                raw_bits=w,
                hex=f"{int(w, 2):015X}",
                family_id=family_ids[canonical(w)],
                ones=w.count("1"),
                observations=len(matched),
                signals=";".join(sorted({r["signal"] for r in matched})),
                exact_ut_match=w in utwords,
                family_ut_match=canonical(w) in utfamilies,
            )
        )
    csv_write(OUT / "signals.csv", signals)
    csv_write(OUT / "observations.csv", observations)
    csv_write(OUT / "word_lookup.csv", lookup)
    exact_matrix = np.array([[hamming(a, b) for b in words] for a in words], float)
    family_matrix = np.array([[family_distance(a, b) for b in families] for a in families], float)
    matrix_csv(OUT / "word_hamming_bits.csv", list(word_ids.values()), exact_matrix)
    matrix_csv(OUT / "family_hamming_bits.csv", list(family_ids.values()), family_matrix)
    word_linkage = clustered_plot(
        exact_matrix,
        list(word_ids.values()),
        OUT / "word_clusters.png",
        "Unique recovered words: raw Hamming distance (bits)",
        60,
    )
    family_linkage = clustered_plot(
        family_matrix,
        list(family_ids.values()),
        OUT / "family_clusters.png",
        "Pattern families: minimum Hamming distance over rotation and inversion",
        30,
    )
    profiles = {
        s["signal"]: Counter(r["family"] for r in accepted if r["signal"] == s["signal"])
        for s in signals
    }
    exact_profiles = {
        s["signal"]: Counter(r["word"] for r in accepted if r["signal"] == s["signal"])
        for s in signals
    }
    pairs = []
    signal_matrix = np.full((len(signals), len(signals)), np.nan)
    for i, a in enumerate(signals):
        for j, b in enumerate(signals):
            pa, pb = profiles[a["signal"]], profiles[b["signal"]]
            distance = distribution_distance(pa, pb)
            if distance is not None:
                signal_matrix[i, j] = distance
            ha, hb = header.get(a["signal"], {}), header.get(b["signal"], {})
            common = sorted(set(ha) & set(hb))
            pairs.append(
                dict(
                    a=a["signal"],
                    b=b["signal"],
                    family_js_distance=distance,
                    exact_js_distance=distribution_distance(
                        exact_profiles[a["signal"]], exact_profiles[b["signal"]]
                    ),
                    shared_families=len(set(pa) & set(pb)) if pa and pb else None,
                    shared_exact_words=len(
                        set(exact_profiles[a["signal"]]) & set(exact_profiles[b["signal"]])
                    )
                    if pa and pb
                    else None,
                    header_shared_positions=len(common),
                    header_disagreement=sum(ha[k] != hb[k] for k in common) / len(common)
                    if len(common) >= 16
                    else None,
                    same_likely_identity=a["norad_id"] == b["norad_id"]
                    if a["norad_id"] and b["norad_id"]
                    else None,
                )
            )
    csv_write(OUT / "signal_pairs.csv", pairs)
    matrix_csv(OUT / "signal_family_js_distance.csv", [s["signal"] for s in signals], signal_matrix)
    valid = [i for i, s in enumerate(signals) if profiles[s["signal"]]]
    visit_labels = [
        f"{signals[i]['signal']} (n={signals[i]['accepted']}) | "
        f"{signals[i]['rate_hz'] / 1e6:g}M {signals[i]['edge']} | {signals[i]['norad_id'] or '?'}"
        if signals[i]["rate_hz"]
        else "UT-ref | published catalogue"
        for i in valid
    ]
    signal_linkage = clustered_plot(
        signal_matrix[np.ix_(valid, valid)],
        visit_labels,
        OUT / "signal_clusters.png",
        "Signal profiles: Jensen–Shannon distance of observed pattern-family frequencies\nAverage linkage; inferred identities are annotations, not training labels",
    )
    strict_profiles = {
        s["signal"]: Counter(
            r["family"]
            for r in accepted
            if r["signal"] == s["signal"] and r["strict_pilot_accepted"]
        )
        for s in signals
    }
    strict_names = [name for name, profile in strict_profiles.items() if profile]
    strict_matrix = np.array(
        [
            [distribution_distance(strict_profiles[a], strict_profiles[b]) for b in strict_names]
            for a in strict_names
        ]
    )
    matrix_csv(OUT / "strict_signal_family_js_distance.csv", strict_names, strict_matrix)
    clustered_plot(
        strict_matrix,
        strict_names,
        OUT / "strict_signal_clusters.png",
        "Sensitivity: dual-RX words additionally requiring pilot coherence > 0.5",
    )
    summary = dict(
        signals=len(signals),
        ds_visits=len(inventory),
        ds_accepted=sum(r["accepted"] for r in observations if r["signal"] != "UT-ref"),
        strict_accepted=sum(r["strict_pilot_accepted"] for r in observations),
        strict_clusterable_signals=len(strict_names),
        ut_accepted=len(ut),
        unique_words=len(words),
        families=len(families),
        clusterable_signals=len(valid),
        unclusterable=[s["signal"] for s in signals if not profiles[s["signal"]]],
        ds_unmatched_ut_families=sorted(
            {
                r["family_id"]
                for r in observations
                if r["accepted"] and r["signal"] != "UT-ref" and r["family"] not in utfamilies
            }
        ),
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        word_linkage=word_linkage,
        family_linkage=family_linkage,
        signal_linkage=signal_linkage,
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    # Standalone searchable lookup, with all ordered signal pairs and word mapping.
    def table(rows):
        keys = list(rows[0])
        return (
            "<table><thead><tr>"
            + "".join(f"<th>{html.escape(k)}</th>" for k in keys)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                + "".join(
                    "<td>"
                    + html.escape(
                        "—"
                        if row[k] is None
                        else str(round(row[k], 4))
                        if isinstance(row[k], float)
                        else str(row[k])
                    )
                    + "</td>"
                    for k in keys
                )
                + "</tr>"
                for row in rows
            )
            + "</tbody></table>"
        )

    figures = "".join(
        f'<h2>{title}</h2><img src="data:image/png;base64,{base64.b64encode((OUT / name).read_bytes()).decode()}">'
        for name, title in [
            ("signal_clusters.png", "Signal profiles"),
            ("strict_signal_clusters.png", "Stricter pilot-quality subset"),
            ("word_clusters.png", "Exact words"),
            ("family_clusters.png", "Rotation/inversion families"),
        ]
    )
    document = """<!doctype html><meta charset="utf-8"><title>DS7/DS8 all-signal lookup</title>
<style>body{font:15px system-ui;margin:24px;max-width:1600px}img{max-width:100%}table{border-collapse:collapse;font-size:12px}td,th{padding:6px;border:1px solid #ccc;white-space:nowrap}th{position:sticky;top:0;background:#eee}.scroll{overflow:auto;max-height:650px}input{padding:10px;width:70%;margin:12px 0}</style>
<h1>DS7/DS8 signal and bit-pattern lookup</h1><p>Descriptive clustering, not decoded identities or message fields. Missing comparisons mean insufficient qualified data. Signal frequency profiles depend on excerpt length, SNR, band edge and acceptance filters. UT-ref is a larger published reference pool, not an equal-duration visit. Header comparisons use only stable overlapping positions and require at least 16; they are not header message decoding.</p>
<p><a href="alternatives.html">Clustering review: sample-count sensitivity and alternative methods</a>. The broad inventory plots below retain low-count visits and UT-ref for context; use the reviewed local-only cohort for comparisons. Tree and heatmap now share the same top-to-bottom order.</p>
<p>Main results require exact agreement of all 60 bits between receivers, selection and held-out correlation above 0.25, and held-out correlation above 1,000 shuffled controls. The strict sensitivity plot additionally requires pilot coherence above 0.5 in both receivers. These exploratory gates do not constitute a calibrated false-discovery probability. Historical shorter-run observations are not pooled into this uniform reanalysis.</p>"""
    for title, rows in [
        ("Signals", signals),
        ("All versus all signals", pairs),
        ("Word lookup", lookup),
    ]:
        document += f"<h2>{title}</h2><input placeholder='Filter this table (e.g. S06 or W001)' oninput='let q=this.value.toLowerCase();this.nextElementSibling.querySelectorAll(\"tbody tr\").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))'><div class='scroll'>{table(rows)}</div>"
    (OUT / "all_vs_all.html").write_text(document + figures)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if not k.endswith("linkage") and k != "input_sha256"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
