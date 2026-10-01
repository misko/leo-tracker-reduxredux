"""Known-identity evaluation, independent of the tracker's fitted model."""
import argparse
import hashlib
import json
from pathlib import Path


def evaluate(truth, path):
    known = [{p["candidate_id"] for p in group} for group in truth["members"]]
    tracks = {}
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if fields[0] == "POINT":
            tracks.setdefault(int(fields[1]), set()).add(fields[2])
    rows = []
    eligible = []
    for i, expected in enumerate(known):
        options = []
        for index, members in tracks.items():
            shared = len(expected & members)
            options.append({"track_index":index, "correct_points":shared,
                            "reference_coverage":shared/len(expected),
                            "purity":shared/len(members), "output_points":len(members)})
        options.sort(key=lambda v:(v["reference_coverage"],v["purity"]),reverse=True)
        rows.append({"truth_index":i,"truth_points":len(expected),"best":options[0] if options else None})
        eligible.append({v["track_index"] for v in options
                         if v["reference_coverage"]>=.8 and v["purity"]>=.8})
    complete = 2 if any(a!=b for a in eligible[0] for b in eligible[1]) else int(any(eligible))
    return {"path":str(path), "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "tracks":len(tracks),"complete_true_curves":complete,
            "unmatched_hypotheses":len(tracks)-complete,"per_truth":rows,
            "criterion":"One-to-one, >=80% known member coverage and >=80% purity; extras remain visible."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--truth",type=Path,required=True)
    parser.add_argument("--tracks",type=Path,nargs="+",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    truth=json.loads(args.truth.read_text())
    result={"truth_sha256":hashlib.sha256(args.truth.read_bytes()).hexdigest(),
            "results":[evaluate(truth,p) for p in args.tracks]}
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
