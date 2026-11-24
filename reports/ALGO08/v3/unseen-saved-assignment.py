"""Assign one independent saved-input case using the released DS30 IDs."""

import hashlib
import json
from pathlib import Path


PREFIX = "ALGO08v3-successor-unseen-20261124/"
EXCLUDED = frozenset("DS30-" + label for label in (
    "0016", "0107", "0008", "0004", "0169", "0138", "0160", "0316", "0374",
    "0402", "0022", "0129", "0227", "0306", "0057", "0049", "0191",
))
ROSTER = Path(__file__).parent / "measurements/release-stage-budget.json"
ROSTER_PIN = "bf5e6488d1b59ba49ca091b6707b6d3fed099664f528bc7540bcbbed7afbc4be"
DECISION_PIN = "26ac73f584b58150b1205ccfb848b0317af322d5389c0b4e8eaf18c0a178f1f1"


def assignment():
    body = ROSTER.read_bytes()
    if hashlib.sha256(body).hexdigest() != ROSTER_PIN:
        raise ValueError("The frozen release roster changed")
    source = json.loads(body)
    pairs = {row["case"]: row["pair_sha256"] for row in source["rows"]}
    if source["decision_sha256"] != DECISION_PIN or len(pairs) != len(source["rows"]) or len(pairs) != 100:
        raise ValueError("The release must supply its exact original 100 IDs")
    ranking = {case: hashlib.sha256((PREFIX + case).encode("utf-8")).hexdigest() for case in pairs.keys() - EXCLUDED}
    selected = min(ranking, key=lambda case: (ranking[case], case))
    order = ("routed", "installed") if int(selected[-4:]) % 2 else ("installed", "routed")
    return dict(selected=selected, ranking_hash=ranking[selected], archived_pair_sha256=pairs[selected],
                order=order, source_sha256=ROSTER_PIN, decision_sha256=DECISION_PIN, released_ids=len(pairs),
                eligible_ids=len(ranking), excluded=sorted(EXCLUDED))


if __name__ == "__main__":
    print(json.dumps(assignment(), sort_keys=True))
