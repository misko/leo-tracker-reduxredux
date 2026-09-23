"""Independent fixed-winner numerical replay against persisted production scores."""
import json
import sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/research"))
from sixteen_joint_compare import prediction_for_track
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2


def main():
    out = Path(__file__).resolve().parent
    cache = out / "joint/cache"
    scans = json.loads((out.parent / "2026_09_23_sixteen_scan_position_resolution/scans.json").read_text())
    store = AdaptiveTlePositionStoreV2(Path("/srv/bulk/leo"))
    results = []
    for scan in scans:
        sid = scan["session_id"]
        evidence = json.loads((cache / "evidence" / f"{sid}.json").read_text())
        with np.load(cache / "scans" / f"{sid}.npz", allow_pickle=False) as z:
            arrays = {key: z[key] for key in z.files}
        doc = store.status(sid).manifest.document
        for prior in ("sacramento", "reno"):
            selected = scan["priors"][prior]["selected"]
            scores = {row["track_id"]: row for row in doc.diagnostics["selected_track_scores"][prior]}
            for track in evidence["tracks"]:
                saved = scores[track["track_id"]]
                if saved["candidate_id"] is None:
                    continue
                prediction = prediction_for_track(evidence, arrays, track,
                    selected["latitude_deg"], selected["longitude_deg"],
                    taus_s=np.asarray([saved["tau_s"]]))
                k = list(map(str, prediction.candidate_ids)).index(str(saved["candidate_id"]))
                train = prediction.training_mask
                residual = prediction.measured_hz - prediction.predictions_hz[k, 0]
                residual -= residual[train].mean()
                rms = float(np.sqrt(np.mean(residual[~train]**2)))
                results.append(dict(session_id=sid, prior=prior, track_id=track["track_id"],
                    saved_rms_hz=saved["heldout_rms_hz"], replay_rms_hz=rms,
                    difference_hz=rms-saved["heldout_rms_hz"]))
    diff = np.abs([row["difference_hz"] for row in results])
    result = dict(scope="Same saved candidate, tau, position and randomized mask; quarter-second orbit interpolation versus production one-second interpolation",
                  count=len(results), abs_delta_hz_quantiles=np.quantile(diff, [0,.5,.95,1]).tolist(), rows=results)
    (out / "replay_audit.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
