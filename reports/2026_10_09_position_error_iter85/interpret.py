"""Summarize completed controlled effects; no per-recording winner selection."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EFFECTS = {
    "Search only": "B1-B0",
    "Joint clock only": "B2-B0",
    "Joint clock after expanded search": "B3-B1",
    "Pruning versus unpruned refit": "B4-C3",
    "Clock-prior relaxation versus narrow refit": "B4W-C4",
    "RF time versus RF-off refit": "B5-C5",
    "Satellite slope0.25 versus RF refit": "B6-C6",
    "Satellite slope0.5 versus RF refit": "B7-C6",
    "Slope0.5 versus0.25": "B7-B6",
}


def main():
    summary = json.loads((HERE / "summary.json").read_text())
    if not summary["complete"]:
        raise SystemExit("Interpretation requires complete148; preserve pending membership")
    pooled = summary["groups"]["Pooled"]
    lines = [
        "# Controlled effects from deployed hard60",
        "",
        "All148 recordings are included: DS16 63, DS17 51, DS18 34. "
        "These are consumed development results. No new deployment is implied.",
        "",
        "Negative changes below mean lower position error. Each contrast is specified "
        "before execution. Refit controls isolate model changes from another local "
        "optimization, but the complete expanded-search pipeline has extra computation.",
        "",
        "| Change | Fitted-c mean delta km | Improved/regressed/tied | "
        "c=0 mean delta km | Improved/regressed/tied |",
        "|---|---:|---|---:|---|",
    ]
    for label, comparison in EFFECTS.items():
        values = [pooled["comparisons"][arm][comparison] for arm in ("fitted-c", "zero-c")]
        cells = [label]
        for v in values:
            cells += [f"{v['mean_delta_km']:+.6f}", f"{v['improved']}/{v['regressed']}/{v['tied']}"]
        lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Search and joint-fit interaction",
        "",
        "Interaction = mean(B3) − mean(B2) − mean(B1) + mean(B0). "
        "Negative means the combined improvement exceeds the sum of the isolated "
        "improvements on this corpus. It is descriptive, not independent validation.",
        "",
        "| Dataset | Fitted-c interaction km | c=0 interaction km |",
        "|---|---:|---:|",
    ]
    for dataset in ("DS16", "DS17", "DS18", "Pooled"):
        values = []
        for arm in ("fitted-c", "zero-c"):
            metrics = summary["groups"][dataset]["arms"][arm]
            means = {s: metrics[s]["position"]["mean"] for s in ("B0", "B1", "B2", "B3")}
            values.append(means["B3"] - means["B2"] - means["B1"] + means["B0"])
        lines.append(f"| {dataset} | {values[0]:+.6f} | {values[1]:+.6f} |")
    lines += [
        "",
        "## Accuracy and deployment limits",
        "",
        "Frequency RMS, qualification, fallback and timing data are separate in "
        "[RESULTS.md](RESULTS.md) and summary.json. c0 locks RF-time coefficients; "
        "C5 fitted-c versus C5 c0 isolates static c, and B5 versus C5 fitted-c isolates "
        "RF time with static c enabled. All use shared fitted-derived candidate inputs.",
        "",
        "No per-scan best-error combination is operationally selected. A subsequent "
        "frozen removal study must test which components remain necessary in the "
        "chosen combination. The reserve remains outcome-unexamined. Cold integrated "
        "replay, ordinary new-scan shadow results, fallback/runtime checks and WebUI "
        "PNGs are required before promoting a new default.",
        "",
        "![Mean error by configuration](means.png)",
        "",
        "![All-member error distributions](distributions.png)",
        "",
        "![Individual scan errors](per-scan.png)",
    ]
    (HERE / "CONTROLLED_EFFECTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
