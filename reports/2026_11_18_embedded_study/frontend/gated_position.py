"""Paired geographic test of every-eighth blind and guided acquisition on saved DS26 peaks."""
import hashlib
import json
from pathlib import Path
import sys

from replay import extract, replay, INPUTS

HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parent/"stream"))
from winner_to_fix import at_deadline, cold, winners


def main():
    base=cold.read(HERE.parent/"stream/winner-positions-32.json")
    assert base["cold_source_sha256"]==hashlib.sha256(Path(cold.__file__).read_bytes()).hexdigest()
    assert base["cases"]==cold.panel()
    native_baseline={r["case"]:r for r in base["rows"] if r.get("deadline")=="full"}
    gate_checks={r["case"]:r for r in cold.read(HERE/"pilot-prediction-stride1.json")["rows"]}
    results=[]
    for case in base["cases"]:
        path=INPUTS/case/"native.json"
        if not path.is_file():
            results.append(dict(case=case,status="missing native input"))
            continue
        raw=path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==gate_checks[case]["input_sha256"]
        doc=json.loads(raw)
        whole,meta,half=winners(doc)
        assert len(whole)==native_baseline[case]["winners"]
        source=doc["source"]
        indices={(p["channel"],p["receiver_id"],p["actual_rf_hz"],p["visit_index"]):i for i,p in enumerate(source["probes"])}
        assert len(indices)==len(source["probes"])
        accepted=[]
        def keep(lane,visit,t,cfo):
            ch,rx,rf=lane
            i=indices[(*lane,visit)]
            accepted.append((i,rx+1,ch,rf,t+half,cfo))
        stats=replay(extract(doc),8,True,emit=keep)
        assert stats==gate_checks[case]["modes"]["every8-joint"]
        assert len(accepted)==stats["reference_winners_reproduced"]+stats["guided_substitute"]
        accepted.sort(key=lambda r:(r[4],r[1],r[2]))
        result=at_deadline(case,accepted,meta,half,"full")
        assert result["winners"]==len(accepted)
        results.append(result)
    (HERE/"gated-positions-32.json").write_text(json.dumps(dict(rows=results,cases=base["cases"],cold_source_sha256=base["cold_source_sha256"]),allow_nan=False,indent=2))


if __name__=="__main__":
    main()
