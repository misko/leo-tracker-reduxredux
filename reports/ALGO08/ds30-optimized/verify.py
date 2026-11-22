"""Verify published DS30 tables against every receipt in the selected panel."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import zipfile

from PIL import Image
from score import ARMS, BASE, HERE, MODES, read, records, score
from panels import select_panel


def verify(out):
    panel=read(out/"panel.json")
    ref=read(BASE/"prediction-lock.json")
    selected=select_panel(ref["predictions"],panel["panel"])
    assert panel["cases"]==[r["case"] for r in selected]
    members={r["id"]:r for r in read(BASE/"cohort.json")["members"]}
    roster=[members[cid] for cid in panel["cases"]]
    expected={r["id"]+"/"+m+".json" for r in roster for m in MODES}
    manifest=read(out/"prediction-lock.json")
    assert set(manifest)==expected
    with zipfile.ZipFile(out/"predictions.zip") as archive:
        assert set(archive.namelist())==expected and len(archive.namelist())==len(expected)
        entries={}
        for name,wanted in manifest.items():
            data=archive.read(name)
            assert hashlib.sha256(data).hexdigest()==wanted
            entries[name]=json.loads(data)
    signed={r["case"]:r for r in ref["predictions"] if r["method"]=="compact_two_scan"}
    counts=Counter()
    for r in roster:
        cid=r["id"]
        pair=[entries[cid+"/"+mode+".json"] for mode in MODES]
        for mode,a in zip(MODES,pair):
            assert a["case"]==cid and a["mode"]==mode and a["windows"]==r["windows"]
            assert a["raw_authority"]==signed[cid]["raw_authority"]
            assert a["input_binding_sha256"]==signed[cid]["input_binding_sha256"]
            assert a["detector"]==dict(deployed="98d094c9541d22a94396df9ce00778c20030fcf88ac52257bd975b304b916cb5",
                                      optimized="f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809")[mode]
            counts[mode,a["status"]]+=1
            assert set(a["arms"])==set(ARMS)
            for unit in ("cpu","wall"):
                assert abs(a["total_"+unit+"_s"]-a["solve_"+unit+"_s"]-a["acquisition_"+unit+"_s"])<1e-6
            for v in a["arms"].values():
                assert (v["latlon"] is not None)==(a["status"]=="ok")
        assert pair[0]["cpu"]==pair[1]["cpu"] and pair[0]["order"]+pair[1]["order"]==1
        assert pair[0]["release"]==pair[1]["release"]=="081ab0265a9d37dbc2d3fb5b62a64d02970b67ed"
        assert pair[0]["region"]==pair[1]["region"]
    timing,positions=score(roster,entries)
    for path,actual in (("runtime.csv",timing),("positions.csv",positions)):
        published=records(out/path)
        assert len(actual)==len(published)
        for a,b in zip(actual,published):
            assert {k:("" if v is None else str(v)) for k,v in a.items()}==b
    assert len(positions)==2*len(roster) and len(timing)==len(roster)
    if panel["panel"]=="full":
        assert sum(r["eligible_visits"] for r in timing)==2581792
    for name in ("runtime.png","position-error.png"):
        with Image.open(out/name) as im:
            assert im.format=="PNG" and im.width>=1500 and im.height>=700
            im.load()
    for name in ("README.md","PROTOCOL.md"):
        for link in re.findall(r"\]\(([^ )]+)\)",(out/name).read_text()):
            assert (out/link).exists(),link
    with zipfile.ZipFile(out/"receiver-source.zip") as z:
        build=json.loads(z.read("build.json"))
        assert all(build["rebuild_sha256"]==r["detector"] for r in entries.values() if r["mode"]=="optimized")
        for name,h in build["source_digests"].items():
            assert hashlib.sha256(z.read(name)).hexdigest()==h
    print("Verified",len(timing),"pairs and",len(positions),"scored recording/calibration comparisons.",dict(counts))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report",type=Path,nargs="?",default=HERE)
    verify(parser.parse_args().report)
