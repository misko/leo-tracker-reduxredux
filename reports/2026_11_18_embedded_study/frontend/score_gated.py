"""Compare full-scan positions after freezing both gated and dense estimates."""
import json
from pathlib import Path
import sys

from gated_position import HERE

sys.path.insert(0,str(HERE.parent/"stream"))
from score_winners import REFERENCE, latlon, stat, surface_error


def main():
    candidate=json.loads((HERE/"gated-positions-32.json").read_text())
    baseline=json.loads((HERE.parent/"stream/winner-positions-32.json").read_text())
    assert candidate["cases"]==baseline["cases"]
    b={r["case"]:r for r in baseline["rows"] if r.get("deadline")=="full"}
    c={r["case"]:r for r in candidate["rows"] if r.get("deadline")=="full"}
    ref=json.loads(REFERENCE.read_text())
    truth=[ref["latitude_deg"],ref["longitude_deg"]]
    summary={}
    for arm in ("c0","fitted_c"):
        good={name:[case for case,r in obj.items() if r["arms"][arm]["status"]=="estimate"]
              for name,obj in (("baseline",b),("guided",c))}
        paired=sorted(set(good["baseline"]).intersection(good["guided"]))
        err={name:{case:surface_error(latlon(obj[case]["arms"][arm]["xy"]),truth) for case in paired}
             for name,obj in (("baseline",b),("guided",c))}
        stats={}
        for name,obj in (("baseline",b),("guided",c)):
            stats[name]=dict(fixes=len(good[name]),position_km=stat(list(err[name].values())),
                    rms_hz=stat([obj[case]["arms"][arm]["rms_hz"] for case in paired]),
                    winners=sum(obj[k]["winners"] for k in paired),
                    on_boundary=sum(obj[k]["arms"][arm]["on_boundary"] for k in paired),
                    satellites=stat([obj[case]["arms"][arm]["satellites"] for case in paired]))
        deltas=[err["guided"][k]-err["baseline"][k] for k in paired]
        summary[arm]=dict(scans=len(candidate["cases"]),common=len(paired),outcomes=stats,
                          errors={case:dict(baseline_km=err["baseline"][case],guided_km=err["guided"][case]) for case in paired},
                          paired_delta_km=stat(deltas),improved=sum(delta<0 for delta in deltas),
                          missing_or_failed={name:[k for k in candidate["cases"] if k not in success] for name,success in good.items()})
    doc=dict(comparison="RF residuals are in-sample on the points retained by each pipeline; common scans, different point sets between pipelines. Both calibration arms use the same association and selection budget within each pipeline.",summary=summary)
    (HERE/"gated-position-comparison.json").write_text(json.dumps(doc,allow_nan=False,indent=2))
    for arm,result in summary.items():
        print(arm, {k:v for k,v in result.items() if k != "errors"})


if __name__=="__main__":
    main()
