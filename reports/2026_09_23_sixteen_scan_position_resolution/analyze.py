import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from matplotlib.figure import Figure

from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2

root = Path(__file__).resolve().parent
selection = json.loads((root / "selection.json").read_text())
store = AdaptiveTlePositionStoreV2(Path("/srv/bulk/leo"))


def read(sid):
    with urlopen(
        "http://127.0.0.1:8090/api/v3/scanner/adaptive-sessions/" + sid, timeout=60
    ) as response:
        capture = json.load(response)["capture"]
    doc = store.status(sid).manifest.document
    diagnostics = doc.diagnostics
    out = {
        "session_id": sid,
        "captured_at": capture["captured_at"],
        "rate_hz": capture["sample_rate_hz"],
        "duty_ppm": capture["valid_duty_ppm"],
        "edge": capture.get("selected_edge"),
        "priors": {},
    }
    scores = diagnostics["selected_track_scores"]
    a = {t["track_id"]: t for t in scores["sacramento"]}
    b = {t["track_id"]: t for t in scores["reno"]}
    out["association_comparison"] = {
        "tracks": len(a),
        "different_norad": sum(a[k]["candidate_id"] != b[k]["candidate_id"] for k in a),
    }
    for prior in doc.priors:
        ts = scores[prior.name]
        out["priors"][prior.name] = {
            "selected": prior.selected.model_dump(mode="json"),
            "finest": prior.finest.model_dump(mode="json"),
            "accounting": prior.accounting.model_dump(mode="json"),
            "tau_boundary_count": sum(t["tau_s"] is not None and abs(t["tau_s"]) == 5 for t in ts),
            "tau_histogram": {str(i): sum(t["tau_s"] == i for t in ts) for i in range(-5, 6)},
            "unique_norads": len({t["candidate_id"] for t in ts if t["candidate_id"] is not None}),
        }
    return out


with ThreadPoolExecutor(max_workers=2) as pool:
    scans = list(pool.map(read, selection["session_ids"]))
scans.sort(key=lambda s: s["captured_at"])
times = [datetime.fromisoformat(s["captured_at"]) for s in scans]
gaps = [(b - a).total_seconds() for a, b in zip(times[:-1], times[1:], strict=True)]
summary = {
    "selection_rule": selection["rule"],
    "scan_count": len(scans),
    "start": scans[0]["captured_at"],
    "last_start": scans[-1]["captured_at"],
    "first_to_last_start_seconds": (times[-1] - times[0]).total_seconds(),
    "start_gaps_seconds": gaps,
    "tracks": sum(s["priors"]["sacramento"]["accounting"]["eligible_track_count"] for s in scans),
    "observations": sum(
        s["priors"]["sacramento"]["accounting"]["eligible_observation_count"] for s in scans
    ),
    "different_norad_between_priors": sum(
        s["association_comparison"]["different_norad"] for s in scans
    ),
    "rate_hz": sorted({s["rate_hz"] for s in scans}),
    "edges": {e: sum(s["edge"] == e for s in scans) for e in ("lower", "upper")},
    "priors": {},
}
fig = Figure(figsize=(12, 7), layout="constrained")
axes = fig.subplots(2, 1)
for name in ("sacramento", "reno"):
    selected = [s["priors"][name]["selected"] for s in scans]
    errors = np.array([p["horizontal_error_m"] / 1000 for p in selected])
    finest = np.array([s["priors"][name]["finest"]["horizontal_error_m"] / 1000 for s in scans])
    summary["priors"][name] = {
        "selected_error_km_min_median_max": np.quantile(errors, [0, 0.5, 1]).tolist(),
        "finest_error_km_min_median_max": np.quantile(finest, [0, 0.5, 1]).tolist(),
        "unique_selected_positions": len(
            {(p["latitude_deg"], p["longitude_deg"]) for p in selected}
        ),
        "selected_spacing_km_counts": {
            str(g): sum(p["spacing_km"] == g for p in selected) for g in (100, 50, 25, 12.5)
        },
        "tau_boundary_count": sum(s["priors"][name]["tau_boundary_count"] for s in scans),
        "median_score_hz": float(np.median([p["capped_weighted_rmse_hz"] for p in selected])),
    }
    axes[0].plot(range(1, 17), errors, "o-", label=name.title())
    axes[1].plot(
        range(1, 17), [p["capped_weighted_rmse_hz"] for p in selected], "o-", label=name.title()
    )
axes[0].set(
    ylabel="Selected position error (km)",
    yscale="log",
    title="Independent current estimates; reference used only for evaluation",
)
axes[1].set(ylabel="Selection RMS (Hz)", xlabel="Consecutive scan, chronological order")
for ax in axes:
    ax.grid(alpha=0.2)
    ax.legend()
    ax.set_xticks(range(1, 17))
fig.suptitle("16 consecutive analyzed 300-second scans · existing baseline, no new fitting")
fig.savefig(root / "baseline.png", dpi=150)
(root / "scans.json").write_text(json.dumps(scans, indent=2) + "\n")
(root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
