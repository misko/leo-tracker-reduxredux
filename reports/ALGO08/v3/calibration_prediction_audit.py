"""Apply the frozen RF-only rule to already issued standard products."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from .calibration_prediction_check import assess


TMPFS = Path("/dev/shm")
ARMS = ("c0", "fitted_c")
HELD = "physical-0004"
SCOPES = {
    HELD: ("leo-v3-history-risk-0004-pair01/routed/candidate", "joint-research-receipt.json"),
    "physical-0169": ("leo-v3-history-risk-0169-01/candidate", "joint-research-receipt.json"),
    "physical-0016-containing-20/8": ("leo-v3-history-risk-0016-cairo-result01/candidate", "exact-named-raw-witness.json"),
    "physical-0016-omitted-20/8": ("leo-v3-history-risk-0016-omitted-result02/candidate", "exact-named-raw-witness.json"),
    "physical-0016-containing-named": ("leo-v3-raw-0016-best-results-01/stock", None),
    "physical-0016-omitted-named": ("leo-v3-named-0016-translated-result01/translated", None),
    "north-containing-20/8": ("leo-v3-history-risk-raw-north02/candidate", "exact-named-raw-witness.json"),
    "north-far-20/8": ("leo-v3-history-risk-raw-north-omitted02/north-far-saved", "exact-named-raw-witness.json"),
    "north-containing-continued": ("leo-v3-continued-north-result01/containing", "joint-research-receipt.json"),
    "north-near-continued": ("leo-v3-continued-north-mirror-result02/north-mirror-outside", "joint-research-receipt.json"),
    "south-containing-20/8": ("leo-v3-eight-ms-south-result01/containing", "joint-research-receipt.json"),
    "south-near-20/8": ("leo-v3-eight-ms-south-result01/near-omitted", "joint-research-receipt.json"),
    "south-containing-named": ("leo-v3-named-south-transfer-01/containing", "joint-research-receipt.json"),
    "south-near-named": ("leo-v3-named-south-transfer-01/near-omitted", "joint-research-receipt.json"),
}
NAMED_OWNER_SOURCE = "leo-v3-named-0016-translated-result01/owners.json"


def digest(body):
    return "sha256:" + sha256(body).hexdigest()


def canonical(value):
    return digest(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                             separators=(",", ":")).encode())


def read(path, pins):
    if (not path.is_relative_to(TMPFS) or path.resolve(strict=True) != path
            or path.stat().st_dev != TMPFS.stat().st_dev or path.stat().st_size > 8_000_000):
        raise ValueError(f"Require a small existing tmpfs publication: {path}")
    body = path.read_bytes()
    pins[str(path)] = digest(body)
    return json.loads(body)


def evidence(case):
    relative, witness = SCOPES[case]
    root, pins = TMPFS / relative, {}
    (terminal_path,) = root.glob("fast-scan-automatic-work/*/terminal.json")
    terminal = read(terminal_path, pins)
    if terminal["decision"] == "withheld":
        if any(terminal["arms"][arm]["latlon"] is not None for arm in ARMS):
            raise ValueError("Withholding must have null arms")
        return dict(existing=terminal["decision"], status="unavailable", reason="prior_withhold", pins=pins)
    if terminal["decision"] != "ok":
        raise ValueError("A predictive screen requires a completed standard publication")
    manifest = read(root / "fast-scan-standard-v2" / terminal_path.parent.name / "final-error-v7" / "manifest.json", pins)
    if (manifest["terminal_sha256"], manifest["input_sha256"]) != (canonical(terminal), terminal["native_sha256"]):
        raise ValueError("The standard figure residual and terminal are not bound to one run")
    if witness:
        proof = read(root / witness, pins)
        role_rows = proof["selected_rows"] if "selected_rows" in proof else proof["evidence"]["owner_rows"]
        named_counts = None
    else:
        proof = read(TMPFS / NAMED_OWNER_SOURCE, pins)
        role_rows = proof["containing_rows"] if case == "physical-0016-containing-named" else None
        named_counts = None if role_rows else {arm: proof["arms"][arm]["translated_roles"] for arm in ARMS}
    if role_rows:
        for arm in ARMS:
            rows = role_rows[arm]
            owner = {oid: family for oid, family, _ in rows}
            if (len(rows) != len(owner) or canonical(owner) != manifest["arms"][arm]["owner_sha256"]):
                raise ValueError("The archived ordered rows do not bind to the reported all-owner residual")
        counts = {arm: Counter(row[2] for row in role_rows[arm]) for arm in ARMS}
        same = role_rows[ARMS[0]] == role_rows[ARMS[1]]
    else:
        counts, same = named_counts, False
    arms = {}
    for arm in ARMS:
        plotted, fit = manifest["arms"][arm], terminal["arms"][arm]
        nc, np = (counts[arm].get(role, 0) for role in ("conditional", "predictive"))
        if (sum(counts[arm].values()) != nc + np or plotted["associated_points"] != nc + np
                or plotted["endpoint_latlon"] != fit["latlon"]):
            raise ValueError("The saved role partition, owner count or calibration association changed")
        arms[arm] = dict(conditional_count=nc, predictive_count=np, conditional_rms_hz=fit["rf_rms_hz"],
                         all_owned_rms_hz=plotted["residual_rms_hz"])
    result = assess(arms, same)
    return dict(existing=terminal["decision"], arms=arms, matched_ordered_owners=same, pins=pins, **result)


def seal(path, content):
    with path.open("x") as stream:
        json.dump(content, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("which", choices=("held", "controls"))
    cli.add_argument("destination", type=Path)
    opts = cli.parse_args()
    scoped = (HELD,) if opts.which == "held" else tuple(case for case in SCOPES if case != HELD)
    results = {case: evidence(case) for case in scoped}
    seal(opts.destination, results)
