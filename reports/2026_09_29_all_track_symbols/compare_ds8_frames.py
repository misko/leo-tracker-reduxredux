"""Compare old/new recovery on identical excerpts and common evaluation frames."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
OUT = BASE / "local/ds8-fourteen-frames"


def main():
    plan_path = OUT / "plan.json"
    plan = json.loads(plan_path.read_text())
    rows, inputs = [], {str(plan_path): hashlib.sha256(plan_path.read_bytes()).hexdigest()}
    for capture in plan["captures"]:
        unit = capture["unit"]
        old_path = BASE / f"local/decoded/{unit}/results.json"
        new_path = OUT / f"decoded/{unit}/results.json"
        old = {r["track_id"]: r for r in json.loads(old_path.read_text())["rows"]}
        new = {r["track_id"]: r for r in json.loads(new_path.read_text())["rows"]}
        inputs.update(
            {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [old_path, new_path]}
        )
        for item in (m for m in plan["mapping"] if m["unit"] == unit):
            a, b = old[item["track_id"]], new[item["track_id"]]
            if "artifact" not in b:
                rows.append(dict(**item, error=b.get("error", b["status"])))
                continue
            assert a["excerpt_sha256"] == b["excerpt_sha256"]
            assert a["candidate_id"] == b["candidate_id"]
            assert a["track_id"] == b["track_id"]
            path = Path(b["artifact"])
            assert hashlib.sha256(path.read_bytes()).hexdigest() == b["artifact_sha256"]
            am, bm = a["receiver_metadata"], b["receiver_metadata"]
            common = sorted(set(am["evaluation_frames"]) & set(bm["evaluation_frames"]))
            old_q = [am["diagnostics"][f]["held_pilot_coherence"] for f in common]
            new_q = [bm["diagnostics"][f]["held_pilot_coherence"] for f in common]
            words = [w for w in b["words"] if w["accepted"]]
            rows.append(
                dict(
                    **item,
                    new_status=b["status"],
                    shape=b["shape"],
                    calibration_frames=bm["calibration_frames"],
                    evaluation_frames=bm["evaluation_frames"],
                    qualified_frames=b["qualified_frames"],
                    common_evaluation_frames=common,
                    common_old_quality=old_q,
                    common_new_quality=new_q,
                    accepted_words=len(words),
                    known_words=sum(w["known_phase"] is not None for w in words),
                )
            )
    good = [r for r in rows if "error" not in r]
    old_q = np.array([q for r in good for q in r["common_old_quality"]])
    new_q = np.array([q for r in good for q in r["common_new_quality"]])
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256=inputs,
        tracks=len(rows),
        errors=[r for r in rows if "error" in r],
        transitions=dict(Counter(f"{r['old_status']} -> {r['new_status']}" for r in good)),
        common_frame_observations=len(old_q),
        common_old_pass=int(sum(old_q > 0.5)),
        common_new_pass=int(sum(new_q > 0.5)),
        common_quality_change_quantiles=np.quantile(new_q - old_q, [0.05, 0.5, 0.95]).tolist(),
        accepted_words=sum(r["accepted_words"] for r in good),
        known_words=sum(r["known_words"] for r in good),
        rows=rows,
    )
    (OUT / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({k: v for k, v in result.items() if k not in {"rows", "input_sha256"}}, indent=2)
    )


if __name__ == "__main__":
    main()
