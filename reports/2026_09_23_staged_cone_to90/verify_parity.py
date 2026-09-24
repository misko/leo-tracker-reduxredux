import hashlib, json
from pathlib import Path
HERE=Path(__file__).parent
OLD=HERE.parent/"2026_09_23_staged_cone_width_sweep/results.json"
NEW=HERE/"results.json"
old=json.loads(OLD.read_text()); new=json.loads(NEW.read_text()); checks=[]
fields=("orientation","training_capped_loss","held_capped_loss","supported_tracks","supported_occupied_second_support","changed_candidate_id_count")
for ci in range(5):
 for width in (10.0,25.0,30.0):
  for mapping in ([0,1],[1,0]):
   a=next(x for x in old["results"][ci]["scenarios"] if x["full_fov_deg"]==width and x["mapping"]==mapping)
   b=next(x for x in new["results"][ci]["scenarios"] if x["full_fov_deg"]==width and x["mapping"]==mapping)
   assert all(a[f]==b[f] for f in fields)
   assert [x["refit_candidate_id"] for x in a["assignments"]]==[x["refit_candidate_id"] for x in b["assignments"]]
   checks.append({"cell_id":new["results"][ci]["cell_id"],"full_fov_deg":width,"mapping":mapping,"parity":True})
def digest(path): return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
out={"schema":"staged-cone-to90-parity/v1","all_passed":True,"comparison_count":len(checks),"fields":list(fields)+["refit_candidate_ids"],"checks":checks,"bindings":{"prior_results":digest(OLD),"extended_results":digest(NEW),"verification_source":digest(Path(__file__))}}
(HERE/"parity_receipt.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
