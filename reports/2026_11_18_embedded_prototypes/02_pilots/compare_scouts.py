"""Check the earlier cold-or-eighth scout policy on exactly the new scheduler's probes."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bench import CASES
from support.frontend import replay as original


def main():
    primary = json.loads((HERE / "result.json").read_bytes())
    by_case = {r["case"]: r["detector"] for r in primary["cases"]}
    totals = Counter()
    rows = []
    for case in CASES:
        raw = (original.INPUTS / case / "native.json").read_bytes()
        lanes = original.extract(json.loads(raw))
        prior = original.replay(lanes, period=8, phase_gate=True)
        new = by_case[case]
        if (prior["probes"], prior["reference_winners"]) != (new["probes"], new["blind_reference_winners"]):
            raise ValueError(f"Unmatched archived detector probes or blind winners for {case}")
        counts = dict(probes=prior["probes"], blind_winners=prior["reference_winners"],
                      prior_exact=prior["reference_winners_reproduced"], new_exact=new["exact"],
                      prior_area=prior["search_area_upper"], new_area=new["search_area_units_upper"])
        totals.update(counts)
        rows.append(dict(case=case, native_sha256=hashlib.sha256(raw).hexdigest(), **counts))
    summary = {f"{policy}_winner_recall": totals[f"{policy}_exact"] / totals["blind_winners"]
               for policy in ("prior", "new")}
    summary.update({f"{policy}_area_fraction": totals[f"{policy}_area"] / totals["probes"]
                    for policy in ("prior", "new")})
    result = dict(prior="Blind search whenever the lane is cold or every eighth visit. "
                        "Three states, six-second expiry, +/-8 kHz and +/-25 us gates.",
                  new="Prespecified guided/rescue prototype in run.py. Both policies see the same saved candidate export.",
                  cases=rows, counts=dict(totals), summary=summary)
    (HERE / "scout-policy-control.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
