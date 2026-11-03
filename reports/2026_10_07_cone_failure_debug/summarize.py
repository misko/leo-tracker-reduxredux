"""Consolidate completed receipts without choosing methods by reference error."""
import csv
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    rows=[];sources={};counts={};elapsed={}
    def read(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())
    def append(experiment,case,values):
        for r in values:
            clock=r.get("pair_clock",{})
            rows.append(dict(experiment=experiment,case=case,option=r.get("option",r.get("model",r.get("correction",""))),arm=r["arm"],
                basin=r.get("basin",""),selection_score=r.get("selection_score",r.get("objective")),
                position_error_km=r.get("horizontal_error_m",r.get("error_m",0))/1000,
                data_nll=r.get("data_nll"),uniform_frequency_data_nll=r.get("uniform_frequency_data_nll"),
                timing_penalty=r.get("timing_penalty"),posterior_rms_hz=r.get("posterior_rms_hz",r.get("rms_hz")),
                signal_fraction=r.get("signal_fraction"),converged=r["converged"],boundary=r["boundary"],
                stationarity=r["stationarity"],paired_median_abs_hz=clock.get("median_absolute_residual_hz"),
                paired_residual_slope_hz_s=clock.get("robust_residual_slope_hz_s"),
                mean_common_unidentified_pair_probability=r.get("mean_common_unidentified_pair_probability",r.get("mean_common_background_probability"))))
    for case in ("1939","2139"):
        p=HERE/"geometry_fix"/case/"polished.json";d=read(p);append("geometry",case,d["selections"])
        primary=read(p.parent/"results.json")
        counts[f"geometry-{case}"]=len(primary["runs"])+len(d["polish_runs"])
        for folder in ("timing_search","annealing","paired_identity","paired_background"):
            d=read(HERE/folder/f"{case}.json");assert d["status"]=="complete"
            append(folder,case,d["selections"])
            counts[f"{folder}-{case}"]=len(d["runs"])
            for r in d["selections"]:
                eligible=[v for v in d["candidates"] if v["option"]==r["option"] and v["arm"]==r["arm"] and v.get("feasible",True)]
                if folder=="timing_search":
                    retained=read(HERE.parent/"2026_10_07_sigma1_cones"/case/"polished.json")
                    eligible += [v for v in retained["candidates"] if v["option"]=="control" and v["arm"]==r["arm"] and v["feasible"]]
                assert abs(r["selection_score"]-min(v["selection_score"] for v in eligible))<1e-6
                if r["arm"]=="zero-c":assert r["vector"][6]==0
            if "fit_elapsed_s" in d:elapsed[f"{folder}-{case}"]=d["fit_elapsed_s"]
        quadratic=read(HERE/"timing_search/quadratic"/f"{case}.json")
        assert quadratic["status"]=="complete"
        append("quadratic",case,quadratic["selections"])
        counts[f"quadratic-{case}"]=len(quadratic["runs"])
    anchors=read(HERE/"paired_background/anchor_results.json")
    assert anchors["status"]=="complete"
    for case in anchors["cases"]:
        append("receiver_anchor",case["case"],case["selections"])
        counts[f"receiver_anchor-{case['case']}"]=len(case["runs"])
        for row in case["selections"]:
            eligible=[v for v in case["candidates"] if v["model"]==row["model"] and v["arm"]==row["arm"] and v["feasible"]]
            assert abs(row["selection_score"]-min(v["selection_score"] for v in eligible))<1e-6
            if row["arm"]=="zero-c":assert row["vector"][6]==0
    with (HERE/"selected.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    output=dict(rows=rows,fit_counts=counts,known_fit_elapsed_s=elapsed,source_sha256=sources,
                caveats=["Options use different likelihoods; cross-model score values are not pure frequency-fit comparisons.",
                         "Timing and annealing controls precede paired identity; background controls also test an orbit-blind clock initializer.",
                         "Reference errors are evaluation only, never method-selection criteria.",
                         "Background is conditional on previously score-selected basins; it is not a full regional search."])
    (HERE/"summary.json").write_text(json.dumps(output,indent=2)+"\n")
    print("Consolidated",len(rows),"selected rows;",sum(counts.values()),"fits.")


if __name__=="__main__":main()
