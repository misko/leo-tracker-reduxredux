"""Render the dated DS7/DS8 paper from private, digest-bound evidence.

Only report illustrations, HTML and PDF are written; measurements stay private.
Dependencies: numpy, matplotlib, markdown, weasyprint.
"""

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NAME = "2026-09-28-ds7-ds8"
ASSETS = ROOT / "reports/figures" / NAME
REPORT = ROOT / "reports/2026-09-28-ds7-ds8-signal-structure.md"
BLUE, ORANGE = "#176b9b", "#bc501f"


def read(path):
    return json.loads(path.read_text())


def save(fig, name):
    fig.savefig(ASSETS / (name + ".png"), dpi=220, facecolor="white")
    plt.close(fig)


def workflow():
    fig, ax = plt.subplots(figsize=(8, 3.5), layout="constrained")
    ax.set(xlim=(0, 10), ylim=(0, 5))
    ax.axis("off")
    boxes = [
        (0.1, 1.9, 2.1, 1.2, "Saved DS7 + DS8\ndual-receiver IQ", "#e9eef2"),
        (
            3.0,
            3.3,
            3.1,
            1.2,
            "Known pilots + template\n60-bit estimates\nRX-held-out checks",
            "#e6f2f8",
        ),
        (
            3.0,
            0.5,
            3.1,
            1.2,
            "CFO tracks + site + TLEs\nCandidate Doppler fits\nConditional labels",
            "#fbefe8",
        ),
        (
            7.0,
            1.9,
            2.8,
            1.2,
            "Exact source bindings\nRepeat-pass comparison\nIdentity collisions",
            "#eaf2e9",
        ),
    ]
    for x, y, w, h, text, color in boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y), w, h, boxstyle="round,pad=0.06", facecolor=color, edgecolor="#607080"
            )
        )
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9)
    for start, end in [
        ((2.25, 2.7), (2.95, 3.9)),
        ((2.25, 2.3), (2.95, 1.1)),
        ((6.15, 3.9), (6.95, 2.7)),
        ((6.15, 1.1), (6.95, 2.3)),
    ]:
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="->", color="#607080"))
    ax.text(4.55, 2.45, "No decoded bits used\nto choose an orbit", ha="center", fontsize=9)
    save(fig, "workflow")


def timeline(repeats):
    fig, ax = plt.subplots(figsize=(8, 3.4), layout="constrained")
    for i, row in enumerate(repeats):
        a, b = (datetime.fromisoformat(row[k]) for k in ("ds7_start", "ds8_start"))
        ax.plot([a, b], [i, i], color="#aab2b9", linewidth=1.5)
        ax.scatter(a, i, color=BLUE, s=45, label="DS7" if i == 0 else None, zorder=3)
        ax.scatter(b, i, color=ORANGE, s=45, marker="s", label="DS8" if i == 0 else None, zorder=3)
        ax.annotate(
            f"{(b - a).total_seconds() / 3600:.2f} h",
            (a + (b - a) / 2, i),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    ax.set_yticks(range(len(repeats)), [f"{r['name']}\nNORAD {r['norad_id']}" for r in repeats])
    ax.invert_yaxis()
    ax.set_ylim(len(repeats) - 0.5, -0.7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_xlabel("27 September 2026, UTC — earliest qualifying track start")
    ax.legend(loc="upper right", bbox_to_anchor=(1, 1.15), ncol=2, frameon=False, fontsize=8)
    ax.grid(axis="x", alpha=0.2)
    save(fig, "repeat-timeline")


def controls(raw, reference):
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2), layout="constrained")
    ax = axes[0]
    for i, edge in enumerate(("upper", "lower")):
        rows = [r for r in raw["rows"] if r["edge"] == edge]
        dx = np.linspace(-0.07, 0.07, len(rows))
        ax.scatter(
            i - 0.12 + dx,
            [r["pilot_holdout_coherence"] for r in rows],
            color=BLUE,
            s=20,
            label="Known pilots" if i == 0 else None,
        )
        ax.scatter(
            i + 0.12 + dx,
            [r["heldout_wrong_sequence_max"] for r in rows],
            color=ORANGE,
            marker="x",
            s=24,
            label="Control maximum" if i == 0 else None,
        )
    ax.set_xticks([0, 1], ["Upper edge", "Lower edge"])
    ax.set(title="Raw IQ: seven frames", ylim=(0, 1.05), ylabel="Normalized correlation")
    ax.legend(fontsize=7, loc="center", frameon=False)
    ax = axes[1]
    x = [r["frame"] for r in reference]
    ax.plot(
        x,
        [r["lower_simple_prediction"] for r in reference],
        "o-",
        color=BLUE,
        markersize=3,
        label="Periodic model (accepted)",
    )
    ax.plot(
        x,
        [r["lower_finite_prediction"] for r in reference],
        "x--",
        color=ORANGE,
        markersize=4,
        label="Finite wrap (rejected)",
    )
    ax.set(
        title="Published symbols: thirteen frames",
        xlabel="UT frame index (zero-based)",
        ylim=(0, 1.05),
    )
    ax.legend(fontsize=7, loc="lower center", frameon=False)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
    save(fig, "ut-controls")


def repeat_families(bits):
    rows = [r for r in bits if r["norad_id"] == "59199"]
    families = sorted({r["family"] for r in rows})
    a, b = (
        np.array(
            [sum(r["dataset"] == dataset and r["family"] == f for r in rows) for f in families]
        )
        for dataset in ("DS7", "DS8")
    )
    assert (int(a.sum()), int(b.sum()), len(families)) == (9, 13, 12)
    shared = (a > 0) & (b > 0)
    assert int(shared.sum()) == 3
    fig, ax = plt.subplots(figsize=(8, 3.1), layout="constrained")
    x = np.arange(len(families))
    for i in np.flatnonzero(shared):
        ax.axvspan(i - 0.48, i + 0.48, color="#e1ecde", zorder=0)
    ax.bar(x - 0.18, a, width=0.36, color=BLUE, label="DS7: nine words")
    ax.bar(x + 0.18, b, width=0.36, color=ORANGE, label="DS8: thirteen words")
    ax.set_xticks(x, [f"F{i + 1}" for i in x])
    ax.set(
        xlabel="Normalized code family — shaded families occur in both passes",
        ylabel="Accepted frame observations",
        ylim=(0, max(a.max(), b.max()) + 0.8),
    )
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.legend(frameon=False, ncol=2, loc="upper right", fontsize=8)
    save(fig, "repeat-families")


def render_document():
    import markdown
    from weasyprint import HTML

    body = markdown.markdown(REPORT.read_text(), extensions=["tables", "fenced_code"])
    body = re.sub(
        r"<p>(<img [^>]+>)</p>\s*<p><em>(.*?)</em></p>",
        r"<figure>\1<figcaption>\2</figcaption></figure>",
        body,
        flags=re.S,
    )
    css = """
    @page { size: A4; margin: 18mm 18mm 19mm;
      @bottom-left { content: 'DS7–DS8 Signal Structure · 28 September 2026';
                     font-size: 8pt; color: #555; }
      @bottom-right { content: counter(page); font-size: 8pt; } }
    body { font: 10pt/1.42 'DejaVu Sans', sans-serif; color: #17232d;
           max-width: 900px; margin: auto; }
    h1 { font-size: 22pt; line-height: 1.15; color: #154b70; }
    h2 { font-size: 14pt; margin: 1.25em 0 .4em; color: #154b70; break-after: avoid; }
    h3 { font-size: 11pt; break-after: avoid; }
    p { orphans: 3; widows: 3; }
    a { color: #176b9b; text-decoration: none; }
    table { border-collapse: collapse; width: 100%; font-size: 8pt; margin: 1em 0; }
    th { background: #e8f0f6; text-align: left; }
    td, th { padding: 5px 6px; border-bottom: 1px solid #cbd4dc; }
    tr { break-inside: avoid; }
    figure { margin: 1em 0; break-inside: avoid; }
    img { width: 100%; height: auto; }
    figcaption { font-size: 8pt; line-height: 1.35; color: #344451; }
    pre { font-size: 7.2pt; background: #f0f3f5; padding: 8px;
          white-space: pre-wrap; overflow-wrap: anywhere; }
    code { font-family: 'DejaVu Sans Mono', monospace; font-size: .88em; }
    @media screen { body { padding: 2em; } }
    """
    html = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>DS7–DS8 Signal Structure</title>"
    )
    html += f"<style>{css}</style><body>{body}</body></html>"
    REPORT.with_suffix(".html").write_text(html)

    def portable_link(match):
        target = match.group(1)
        if target.startswith(("https://", "http://", "#")):
            return match.group(0)
        relative = (REPORT.parent / target).resolve().relative_to(ROOT)
        return f'href="https://github.com/misko/leo-tracker-reduxredux/blob/main/{relative}"'

    pdf_html = re.sub(r'href="([^"]+)"', portable_link, html)
    HTML(string=pdf_html, base_url=str(REPORT.parent)).write_pdf(REPORT.with_suffix(".pdf"))


def identity_collisions(bits, result):
    words = sorted(r["raw_bits"] for r in result["exact_cross_identity_words"])
    ids = ["57526", "59199", "59250"]
    counts = np.array(
        [
            [sum(r["raw_bits"] == word and r["norad_id"] == norad for r in bits) for word in words]
            for norad in ids
        ]
    )
    assert np.all(np.sum(counts > 0, axis=0) >= 2)
    fig, ax = plt.subplots(figsize=(8, 2.6), layout="constrained")
    ax.imshow(counts > 0, cmap="Blues", vmin=0, vmax=1, aspect="auto", alpha=0.75)
    for i, j in zip(*np.nonzero(counts), strict=True):
        ax.text(j, i, str(counts[i, j]), ha="center", va="center", color="white", fontsize=11)
    ax.set_yticks(range(3), ["Likely NORAD " + n for n in ids])
    ax.set_xticks(range(len(words)), [f"W{i + 1}" for i in range(len(words))])
    ax.set_xlabel("Exact 60-bit word — no rotation or polarity normalization")
    save(fig, "identity-collisions")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    for line in (ASSETS / "input-hashes.sha256").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        path = args.workspace / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Input changed: {relative}")
    local = args.workspace / "reports/2026_09_28_ds7_ds8_correspondence/local"
    result = read(local / "joint-results.json")
    assert result["total_qualified_codewords"] == 85 and result["unique_families"] == 27
    assert len(result["exact_cross_identity_words"]) == 8
    assert len(result["cross_identity_family_collisions"]) == 11
    with (local / "decoded-bits.csv").open() as stream:
        bits = list(csv.DictReader(stream))
    target = [r for r in bits if r["norad_id"] == "59199"]
    shared = {r["raw_bits"] for r in target if r["dataset"] == "DS7"} & {
        r["raw_bits"] for r in target if r["dataset"] == "DS8"
    }
    assert len(shared) == 3
    assert set(re.findall(r"(?m)^[01]{60}$", REPORT.read_text())) == shared
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    workflow()
    timeline(result["cross_dataset_repeat_candidates"])
    controls(
        read(local / "raw-ut-demodulation-check.json"),
        read(local / "ut-lower-reference-check.json"),
    )
    repeat_families(bits)
    identity_collisions(bits, result)
    render_document()
    print("Verified bound inputs; rendered five figures, HTML and PDF.")


if __name__ == "__main__":
    main()
