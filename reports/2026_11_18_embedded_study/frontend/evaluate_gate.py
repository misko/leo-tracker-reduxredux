"""Measure an optional score threshold with each complete DS9 session held out in turn."""

from collections import Counter
import json
from pathlib import Path

import numpy as np

from folded_scout import ROOT, frequency_match, phase_match


def main():
    base = Path(__file__).parent
    rows = json.loads((base/"folded-scout-five-aliases.json").read_text())["rows"]
    oracle = json.loads((ROOT/"deployed-fractional-oracle.json").read_text())["rows"]
    references = {(r["session_id"],r["visit_index"],r["probe"]["receiver_id"]):r["probe"]["candidates"]
                  for r in oracle}
    counts = Counter()
    per_session = []
    for session in sorted({r["session"] for r in rows}):
        negative_training = [r["estimates"][0][0] for r in rows
                             if r["session"] != session and not r["reference_positive"]]
        threshold = float(np.quantile(negative_training,.95,method="higher"))
        fold = Counter()
        for row in (r for r in rows if r["session"]==session):
            score,e,f = row["estimates"][0]
            eligible = [c for c in references[session,row["visit"],row["rx"]] if c["passed_fractional_margin_gate"]]
            assert bool(eligible) == row["reference_positive"]
            accept = score>threshold
            if eligible:
                ref = max(eligible,key=lambda c:(c["fractional_margin"],-c["candidate_rank"]))
                match = phase_match(e,ref["integer_epoch_sample"]+ref["fractional_epoch_offset_samples"]) and frequency_match(f,ref["fractional_tracking_cfo_hz"])
                fold["positive"]+=1
                fold["correct_positive"]+=accept and match
                fold["wrong_peak"]+=accept and not match
                fold["abstain_positive"]+=not accept
            else:
                fold["reference_negative"]+=1
                fold["accept_negative"]+=accept
        counts.update(fold)
        per_session.append(dict(session=session,threshold=threshold,stats=fold))
    doc=dict(gate="Per held-out session, score must exceed other sessions' 95th percentile reference-empty best-candidate score; higher order statistic.",
             summary=counts,folds=per_session)
    (base/"folded-gate.json").write_text(json.dumps(doc,indent=2)+"\n")
    print(dict(counts))


if __name__=="__main__":
    main()
