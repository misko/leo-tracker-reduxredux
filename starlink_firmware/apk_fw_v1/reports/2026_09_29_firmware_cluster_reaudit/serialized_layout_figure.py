"""Illustrate verified SYSINFO serialization without implying an RF mapping."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def layout(ephemeris, timing):
    fields = [("Envelope", 11), ("SATAddr", 32), ("Channels", 16), ("Presence", 1)]
    if ephemeris:
        fields.append(("Ephemeris", 352))
    fields.append(("Presence", 1))
    if timing:
        fields.append(("Timing + empty options", 81))
    fields.append(("Padding", (-sum(width for _, width in fields)) % 8))
    start, result = 0, []
    for name, width in fields:
        result.append(dict(name=name, start=start, width=width))
        start += width
    return result


def main():
    sources = []
    receipts = {}
    for name in ("sysinfo-address-decode", "sysinfo-timing-layout", "sysinfo-ephemeris-layout"):
        path = BASE / f"local/{name}.json"
        receipts[name] = json.loads(path.read_text())
        sources.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    assert all(len(bytes.fromhex(c["bytes_hex"])) == 8
               for c in receipts["sysinfo-address-decode"]["cases"])
    assert receipts["sysinfo-timing-layout"]["layout"]["bytes"] == 18
    eph = receipts["sysinfo-ephemeris-layout"]
    assert {c["message_bytes"] for c in eph["cases"] if not c["timing"]} == {52}
    assert {c["message_bytes"] for c in eph["cases"] if c["timing"]} == {62}
    variants = [dict(ephemeris=e, timing=t, fields=layout(e, t))
                for e, t in ((0, 0), (0, 1), (1, 0), (1, 1))]
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    colors = dict(zip(("Envelope", "SATAddr", "Channels", "Presence", "Ephemeris",
                       "Timing + empty options", "Padding"),
                      ("#818b99", "#c77532", "#c9a13a", "#282d33", "#397daa",
                       "#4c9874", "#d8dce0"), strict=True))
    fig, ax = plt.subplots(figsize=(11, 4.5), layout="constrained")
    labels = []
    for row, variant in enumerate(variants):
        fields = variant["fields"]
        total = sum(f["width"] for f in fields)
        labels.append(f"Ephemeris {variant['ephemeris']}, timing {variant['timing']}\n"
                      f"{total // 8} bytes")
        for f in fields:
            ax.barh(row, f["width"], left=f["start"], height=.55, color=colors[f["name"]])
            if f["width"] >= 81:
                ax.text(f["start"] + f["width"] / 2, row, f"{f['width']} bits",
                        color="white", ha="center", va="center")
    ax.set(yticks=range(4), yticklabels=labels, xlim=(0, 512),
           xlabel="Serialized control-message bit offset, before PHY coding",
           title="Verified SYSINFO layouts — no established RF carrier mapping\n"
                 "Version zero; later optional scalar absent and list empty")
    ax.invert_yaxis()
    ax.legend(handles=[Patch(color=color, label=name) for name, color in colors.items()],
              loc="upper right", fontsize=8, ncol=2)
    fig.savefig(BASE / "local/serialized-layout.png", dpi=170)
    plt.close(fig)
    output = dict(variants=variants, sources=sources,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Diagram groups serialized fields for readability. It does not "
                  "map them to observed RF signs or infer one bit per carrier. Width equality "
                  "with a captured region is not evidence of field correspondence.")
    (BASE / "local/serialized-layout.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
