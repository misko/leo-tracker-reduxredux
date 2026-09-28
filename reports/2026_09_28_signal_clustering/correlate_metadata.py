"""Exploratory metadata/signature distance associations with session-level screening."""
# ruff: noqa: E501 -- Standalone HTML markup.

import base64
import csv
import html
import json
from collections import Counter

import numpy as np
from cluster_signals import OUT, csv_write, distance_hierarchy
from clustering_review import profile_matrix
from scipy.cluster.hierarchy import leaves_list
from scipy.stats import rankdata

FEATURES = {
    "channel": "category",
    "edge": "category",
    "rate_hz": "numeric",
    "dataset": "category",
    "actual_rf_hz": "numeric",
    "capture_start_unix_s": "numeric",
    "rx0_acquisition_cfo_hz": "numeric",
    "rx1_acquisition_cfo_hz": "numeric",
    "rx1_minus_rx0_cfo_hz": "numeric",
    "rx0_sample_clock_ppm": "numeric",
    "rx1_sample_clock_ppm": "numeric",
    "rx0_pilot_coherence_median": "numeric",
    "rx1_pilot_coherence_median": "numeric",
    "rx0_acquisition_margin": "numeric",
    "rx1_acquisition_margin": "numeric",
    "accepted": "numeric",
    "recovery_fraction": "numeric",
    "strict_accepted": "numeric",
    "known_conditional_norad": "category",
    "predicted_doppler_canonical_hz": "numeric",
    "known_label_elevation_mid_deg": "numeric",
    "known_label_azimuth_mid_deg": "circular",
    "known_label_offset_canonical_hz": "numeric",
    "predicted_range_km": "numeric",
}


def attribute_distance(values, kind):
    v = np.asarray(values)
    if kind == "category":
        return (v[:, None] != v[None, :]).astype(float)
    difference = abs(v.astype(float)[:, None] - v.astype(float)[None, :])
    return (
        np.minimum(difference % 360, 360 - difference % 360) if kind == "circular" else difference
    )


def association(signature, attribute, repetitions=0, seed=20260928):
    """Mantel-style rank association; permutations relabel visits, never individual pairs."""
    n = len(signature)
    ij = np.triu_indices(n, 1)
    a, b = rankdata(signature[ij]), rankdata(attribute[ij])
    a, b = a - a.mean(), b - b.mean()
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        return None, None
    rho = float(a @ b / denominator)
    if not repetitions:
        return rho, None
    ranks = np.zeros((n, n))
    ranks[ij] = b
    ranks[(ij[1], ij[0])] = b
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(repetitions):
        order = rng.permutation(n)
        value = float(a @ ranks[order[ij[0]], order[ij[1]]] / denominator)
        exceed += abs(value) >= abs(rho) - 1e-12
    return rho, (1 + exceed) / (1 + repetitions)


def bh_adjust(pvalues):
    p = np.asarray(pvalues)
    order = np.argsort(p)
    adjusted = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    result = np.empty(len(p))
    result[order] = np.minimum(adjusted, 1)
    return result.tolist()


def representatives(rows):
    """Select by support count before looking at metadata associations; stable tie break."""
    best = {}
    for r in sorted(rows, key=lambda r: r["signal"]):
        if r["session"] not in best or r["accepted"] > best[r["session"]]["accepted"]:
            best[r["session"]] = r
    return sorted(best.values(), key=lambda r: r["signal"])


def main():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    details = json.loads((OUT / "metadata_details.json").read_text())
    rows = [r["summary"] for r in details]
    with (OUT / "observations.csv").open() as stream:
        observations = [r for r in csv.DictReader(stream) if r["accepted"] == "True"]
    eligible = [r for r in rows if r["accepted"] >= 10]
    primary = representatives(eligible)
    profiles = {
        r["signal"]: [o["family"] for o in observations if o["signal"] == r["signal"]] for r in rows
    }
    exact = {
        r["signal"]: [o["word"] for o in observations if o["signal"] == r["signal"]] for r in rows
    }
    balanced_file = OUT / "balanced_mean_js.csv"
    with balanced_file.open() as stream:
        reader = csv.reader(stream)
        balanced_names = next(reader)[1:]
        balanced = np.array([[float(x) for x in r[1:]] for r in reader])
    tests = []
    for feature, kind in FEATURES.items():
        selected = [r for r in primary if r[feature] is not None]
        all_selected = [r for r in eligible if r[feature] is not None]
        rec = dict(
            feature=feature,
            kind=kind,
            primary_sessions=len(selected),
            all_visits=len(all_selected),
            rho=None,
            permutation_p=None,
            bh_q=None,
            all_visit_rho=None,
            exact_word_rho=None,
            balanced_rho=None,
            status="insufficient sessions or varying attributes",
        )
        if len(all_selected) >= 3:
            rec["all_visit_rho"] = association(
                profile_matrix([profiles[r["signal"]] for r in all_selected]),
                attribute_distance([r[feature] for r in all_selected], kind),
            )[0]
        values = [r[feature] for r in selected]
        enough = len(selected) >= 6 and len(set(values)) >= 2
        if kind == "category":
            enough &= sum(v >= 2 for v in Counter(values).values()) >= 2
        if enough:
            md = attribute_distance(values, kind)
            rec["rho"], rec["permutation_p"] = association(
                profile_matrix([profiles[r["signal"]] for r in selected]), md, repetitions=4999
            )
            rec["exact_word_rho"] = association(
                profile_matrix([exact[r["signal"]] for r in selected]), md
            )[0]
            indices = [balanced_names.index(r["signal"]) for r in selected]
            rec["balanced_rho"] = association(balanced[np.ix_(indices, indices)], md)[0]
            if rec["rho"] is not None:
                rec["status"] = "exploratory session-label permutation"
        tests.append(rec)
    valid = [r for r in tests if r["permutation_p"] is not None]
    for r, q in zip(valid, bh_adjust([r["permutation_p"] for r in valid]), strict=True):
        r["bh_q"] = q
    csv_write(OUT / "metadata_correlations.csv", tests)

    fig, ax = plt.subplots(figsize=(11, 8), layout="constrained")
    tested = sorted(valid, key=lambda r: r["rho"])
    y = np.arange(len(tested))
    ax.barh(y, [r["rho"] for r in tested], color="#417b9d", label="Full family profiles")
    ax.scatter(
        [r["balanced_rho"] for r in tested], y, color="#df8129", label="Equal-count sensitivity"
    )
    ax.set_yticks(y, [r["feature"] for r in tested], fontsize=9)
    ax.axvline(0, color="black", linewidth=0.5)
    ax.set_xlabel("Rank correlation of signature distance with metadata difference")
    ax.set_title(
        "One visit per recording session (12 maximum)\nExploratory associations; not causal or decoded fields"
    )
    ax.legend()
    fig.savefig(OUT / "metadata_correlations.png", dpi=160)
    plt.close(fig)

    family_ids = sorted({o["family_id"] for o in observations if o["signal"].startswith("S")})
    tree = distance_hierarchy(
        profile_matrix([profiles[r["signal"]] for r in eligible]), [r["signal"] for r in eligible]
    )
    ordered = [eligible[i] for i in leaves_list(tree)]
    ordered += [r for r in rows if r not in eligible]
    matrix = np.full((len(ordered), len(family_ids)), np.nan)
    for i, row in enumerate(ordered):
        counts = Counter(o["family_id"] for o in observations if o["signal"] == row["signal"])
        if counts:
            matrix[i] = [counts[f] / sum(counts.values()) for f in family_ids]
    fig, ax = plt.subplots(figsize=(15, 12), layout="constrained")
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#dddddd")
    im = ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=0, vmax=0.35)
    labels = [
        f"{r['signal']} | Ch{r['channel']} {r['edge']} | {r['rate_hz'] / 1e6:g}M | "
        f"n={r['accepted']} | {r['known_conditional_name'] or 'ID unresolved'}"
        for r in ordered
    ]
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    ax.set_xticks(range(len(family_ids)), family_ids, rotation=90, fontsize=8)
    ax.set_title(
        "Observed signature vocabulary with acquisition metadata\n"
        "Grey = no qualified profile; low-count visits appended below main cohort"
    )
    fig.colorbar(im, ax=ax, label="Observed family fraction (colour clipped at 0.35)", shrink=0.6)
    fig.savefig(OUT / "metadata_signature_atlas.png", dpi=160)
    plt.close(fig)

    summary = dict(
        primary_signals=[r["signal"] for r in primary],
        eligible_visits=len(eligible),
        tested_features=len(valid),
        q_below_005=[r["feature"] for r in valid if r["bh_q"] < 0.05],
        permutation_repetitions=4999,
        seed=20260928,
        signature="base-2 JS distance of observed 60-bit rotation/inversion families",
        warning="Exploratory univariate distance associations. Sessions are not proven "
        "independent satellite passes; permutations assume exchangeability. "
        "No pairwise-independence assumption or identity training. "
        "BH correction covers only the primary tested features in this screen.",
    )
    (OUT / "metadata_correlation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    def table(records):
        keys = list(records[0])
        return (
            "<div class='scroll'><table><thead><tr>"
            + "".join(f"<th>{html.escape(k)}</th>" for k in keys)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                + "".join(
                    f"<td>{html.escape('—' if r[k] is None else str(r[k]))}</td>" for k in keys
                )
                + "</tr>"
                for r in records
            )
            + "</tbody></table></div>"
        )

    document = """<!doctype html><meta charset="utf-8"><title>Signal metadata and signatures</title>
<style>body{font:15px system-ui;margin:24px}table{border-collapse:collapse;font-size:12px}
td,th{padding:7px;border:1px solid #ddd;white-space:nowrap}th{position:sticky;top:0;background:#eee}
.scroll{overflow:auto;max-height:700px}img{max-width:100%}pre{white-space:pre-wrap}input{padding:10px}</style>
<h1>DS7/DS8 signal metadata and signature associations</h1>
<p>32 local visits; measured acquisition CFO is not pure Doppler. Model Doppler is conditional
on the candidate orbit and normalized to 11.2 GHz unless explicitly marked tuned-RF.
Satellite IDs are geometric associations, not decoded bits. Additional track candidates are
linked by visit, receiver and RF only and are excluded from identity correlations.
Track-observation UTC and track-midpoint angles are distinct from excerpt-start UTC and angles.</p>
<p>The statistical screen selects the most-supported eligible visit per session, before testing
metadata. It uses 4,999 whole-session-label permutations and BH correction across primary tests.
Other views are descriptive sensitivity checks. Shared channel, edge, receiver quality, time and
satellite pass can confound each other; this is not proof of a transmitted metadata field.</p>
<p>All times are UTC. Unknown values are —, not zero. Site is operator supplied; altitude and
antenna elevation are unknown. RX0 west / RX1 east is provisional cable mapping.
UT reference entries have no comparable local acquisition metadata and are excluded from this screen.</p>
<p><a href="metadata_signals.csv">Visit CSV</a> · <a href="metadata_receivers.csv">Receiver CSV</a> ·
<a href="metadata_tracks.csv">Track/orbit CSV</a> · <a href="metadata_details.json">Full evidence JSON</a> ·
<a href="metadata_correlations.csv">Correlation CSV</a> · <a href="all_vs_all.html">Bit lookup</a></p>"""
    document += "<pre>" + html.escape(json.dumps(summary, indent=2)) + "</pre>"
    compact = [
        dict(
            signal=r["signal"],
            dataset=r["dataset"],
            channel=r["channel"],
            edge=r["edge"],
            tuned_rf_GHz=r["actual_rf_hz"] / 1e9,
            MSps=r["rate_hz"] / 1e6,
            rx0_CFO_kHz=round(r["rx0_acquisition_cfo_hz"] / 1000, 2)
            if r["rx0_acquisition_cfo_hz"] is not None
            else None,
            rx1_CFO_kHz=round(r["rx1_acquisition_cfo_hz"] / 1000, 2)
            if r["rx1_acquisition_cfo_hz"] is not None
            else None,
            conditional_satellite=r["known_conditional_name"],
            candidate_tracks_only=r["additional_track_candidates"],
            accepted=r["accepted"],
            strict=r["strict_accepted"],
        )
        for r in rows
    ]
    for title, records in [
        ("Signal overview", compact),
        ("Full visit information", rows),
        ("Metadata associations", tests),
    ]:
        document += f"<h2>{title}</h2>"
        document += """<input placeholder="Filter table: S06, upper, STARLINK..."
oninput="let q=this.value.toLowerCase();this.nextElementSibling.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))">"""
        document += table(records)
    document += """<h2>UT reference availability</h2><p>UT-ref: 347 qualified observations
from 1,009 published hard-symbol frames; two carrier slices. UT-IQ: seven previously checked
raw frames at 250 MS/s, no qualified long T-code block. Local receiver channels, CFO estimates,
site geometry and conditional IDs are not transferred to either reference. See the original
lookup for both entries; missing metadata is not treated as a zero-valued measurement.</p>"""
    for name in ["metadata_signature_atlas", "metadata_correlations"]:
        encoded = base64.b64encode((OUT / f"{name}.png").read_bytes()).decode()
        document += f'<img src="data:image/png;base64,{encoded}">'
    document += "<h2>Per-visit evidence</h2>"
    for d in details:
        document += f"<details><summary>{d['summary']['signal']}: receivers, labels and source evidence</summary>"
        document += "<pre>" + html.escape(json.dumps(d, indent=2)) + "</pre></details>"
    (OUT / "metadata_report.html").write_text(document)
    print(json.dumps(summary, indent=2))
    print(json.dumps(sorted(valid, key=lambda r: r["permutation_p"])[:8], indent=2))


if __name__ == "__main__":
    main()
