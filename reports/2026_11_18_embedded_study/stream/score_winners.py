"""Score already emitted positions against the external DS26 antenna reference."""
import argparse
import json
from pathlib import Path

import numpy as np

from event_fit import CENTER, OUTPUT, REFERENCE, WORKERS, surface_error


def latlon(xy):
    east,north=xy
    return [CENTER[0]+north/111., CENTER[1]+east/(111.32*np.cos(np.deg2rad(CENTER[0])))]


def stat(values):
    if not values:
        return dict(n=0)
    return dict(n=len(values), mean=float(np.mean(values)),median=float(np.median(values)),
                p95=float(np.percentile(values,95)),maximum=float(np.max(values)))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--count",type=int,default=12)
    parser.add_argument("--all-full",action="store_true")
    args=parser.parse_args()
    tag="all" if args.all_full else str(args.count)
    packet=json.loads((OUTPUT/f"winner-positions-{tag}.json").read_bytes())
    old=json.loads((OUTPUT.parent/"cold-panel.json").read_bytes())
    graph={row["case"]:row.get("results",{}).get("joint",{}) for row in old["rows"]}
    ref=json.loads(REFERENCE.read_bytes())
    truth=[ref["latitude_deg"],ref["longitude_deg"]]
    saved={}
    for case in packet["cases"]:
        path=WORKERS/(case+"-r0")/"baseline/worker-result.json"
        outcome=json.loads((path.parent.parent/"baseline-execution.json").read_bytes())["status"]
        saved[case]=(json.loads(path.read_bytes())["arms"] if outcome=="complete" else {})
    report={}
    for deadline in (("full",) if args.all_full else (60,120,"full")):
        rows=[r for r in packet["rows"] if r.get("deadline")==deadline]
        for arm in ("c0","fitted_c"):
            fits=[r for r in rows if r["arms"][arm]["status"]=="estimate"]
            candidate={r["case"]:surface_error(latlon(r["arms"][arm]["xy"]),truth) for r in fits}
            rms={r["case"]:r["arms"][arm]["rms_hz"] for r in fits}
            cf=[case for case in candidate if arm in saved[case]]
            cg=[case for case in candidate if graph.get(case,{}).get(arm,{}).get("status")=="estimate"]
            report[f"{deadline}-{arm}"]=dict(
                presented=len(packet["cases"]),native=len(rows),fits=len(fits),missing=[case for case in packet["cases"] if case not in candidate],
                position_km=stat(list(candidate.values())),edge=sum(r["arms"][arm]["on_boundary"] for r in fits),
                rms_hz=stat([r["arms"][arm]["rms_hz"] for r in fits]),
                selected_satellites=stat([r["arms"][arm]["satellites"] for r in fits]),
                vs_v5=dict(cases=cf,stream_km=stat([candidate[c] for c in cf]),v5_km=stat([surface_error(saved[c][arm]["endpoint_latlon"],truth) for c in cf]),
                           stream_rms_hz=stat([rms[c] for c in cf]),v5_rms_hz=stat([saved[c][arm]["residual_rms_hz"] for c in cf])),
                only_stream_km=stat([candidate[c] for c in candidate if c not in cf]),
                per_case_error_km=candidate,
                vs_full_graph=dict(cases=cg,stream_km=stat([candidate[c] for c in cg]),graph_km=stat([surface_error(latlon(graph[c][arm]["xy"]),truth) for c in cg])),
                cpu_s_by_stage={stage:stat([r["time"][stage] for r in rows]) for stage in ("link_cpu_s","bank_cpu_s","rest_cpu_s")},
                host_post_winner_wall_s=stat([r["time"]["post_winner_wall_s"] for r in rows]))
    (OUTPUT/f"winner-scores-{tag}.json").write_text(json.dumps(report,allow_nan=False,indent=2))
    for label,r in report.items():
        print(label, r["fits"],r["position_km"],"RMS",r["rms_hz"].get("median"),
              "edge",r["edge"],"wall",r["host_post_winner_wall_s"].get("median"),
              "vs_v5",r["vs_v5"]["stream_km"],r["vs_v5"]["v5_km"])


if __name__=="__main__":
    main()
