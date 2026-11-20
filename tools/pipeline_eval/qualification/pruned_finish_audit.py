"""Count final-stage eligibility from original no-repair v5 archives."""

import argparse
import io
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from zipfile import ZipFile

from ..__main__ import save_json
from ..corpus import _selection
from ..variants.v5_lean import ARMS, SOURCE_SHA256
from .v5_postfit import ARCHIVE, _map, sha256
from .v5_prefix_audit import DS29

POLICY = "72h_30s"
FOLDS = {"full", "20261031", "94721", "4081"}


def _field(raw, name, prefix=b""):
    marker = f'["{name}",'.encode() + prefix
    start = raw.find(marker)
    if start < 0 or raw.find(marker, start + len(marker)) >= 0:
        raise ValueError(f"expected one archived {name} field")
    decoder = json.JSONDecoder()
    size = 4096
    while True:
        try:
            (_, value), _ = decoder.raw_decode(raw[start : start + size].decode("utf-8", "ignore"))
            return value
        except json.JSONDecodeError:
            if start + size >= len(raw):
                raise
            size *= 2


def _rows(node):
    kind, rows = node
    if kind != "list":
        raise ValueError("expected an archived list")
    return [_map(row) for row in rows]


def _checkpoint(raw, name, status):
    prefix = f'["map",[["status","{status}"]'.encode()
    return _map(_field(raw, name, prefix))


def counts(raw):
    trigger = _checkpoint(raw, "reassociation_trigger", "reassociation_targets_ranked")
    ranking = _rows(trigger["ranking"])
    retained = [row for row in ranking if row["points"] >= 30 and row["tracks"] >= 2]
    passing = [row["norad"] for row in retained if float.fromhex(row["rank_score"][1]) >= 0.5]
    if len(ranking) != len({row["norad"] for row in ranking}) or trigger["targets"] != [
        "list",
        passing[:2],
    ]:
        raise ValueError("family ranking or original top-two gate differs")
    screened = _checkpoint(raw, "reassociation_screen", "reassociation_candidates_screened")
    admission = _map(screened["admission"])
    if admission["targets"] != trigger["targets"]:
        raise ValueError("admission targets differ from the ranked targets")

    prepared = _checkpoint(raw, "additional_recovery", "additional_recovery_prepared")
    incumbent_families = len(prepared["families"][1])
    if incumbent_families not in (0, 1, 2):
        raise ValueError("unexpected incumbent residual family count")
    eligible_targets = _map(prepared["inventory"])["eligible_targets"]
    residual = _checkpoint(raw, "residual_screen", "additional_candidates_screened")
    targets = _rows(_map(residual["screen"])["targets"])
    if len(targets) != min(3, eligible_targets):
        raise ValueError("residual target count differs from the original top-three gate")
    folds, scored_folds, screen_pass = Counter(), Counter(), 0
    for target in targets:
        names = {row["name"] for row in _rows(target["folds"])}
        if "full" not in names or not names <= FOLDS:
            raise ValueError("unexpected residual fold schedule")
        folds[len(names) - 1] += 1
        (summary,) = [item for item in _rows(target["summaries"]) if item["policy"] == POLICY]
        arms = _map(summary["arms"])
        if set(arms) != set(ARMS):
            raise ValueError("both residual screening arms required")
        for arm in ARMS:
            by_name = _map(_map(arms[arm])["folds"])
            if not by_name.keys() <= names:
                raise ValueError("scored fold absent from the original schedule")
            scored_folds[arm] += by_name.keys() == FOLDS
        screen_pass += summary["screen_pass"]

    replay = _map(_field(raw, "replay", b'["map",[["pre_recovery",'))
    decision = _map(replay["recovery"])
    excluded = Counter(row["reason"] for row in _rows(decision["excluded"]))
    return dict(
        observed_families=len(ranking),
        support_eligible_families=len(retained),
        original_arm_omissions=sum(len(_map(row["arms"])) for row in ranking),
        support_eligible_arm_omissions=sum(len(_map(row["arms"])) for row in retained),
        rank_eligible_before_cap=len(passing),
        rank_eligible_after_cap=len(passing[:2]),
        reassociation_admission_status=admission["status"],
        admitted_reassociation_proposals=len(_rows(admission.get("admitted", ["list", []]))),
        incumbent_residual_families=incumbent_families,
        residual_targets_before_cap=eligible_targets,
        residual_targets=len(targets),
        residual_held_fold_counts=dict(sorted(folds.items())),
        residual_scored_all_folds={arm: scored_folds[arm] for arm in ARMS},
        residual_fold_eligible_targets=folds[3],
        residual_pruned_fit_eligible_targets=folds[3] if incumbent_families < 2 else 0,
        residual_screen_pass=screen_pass,
        residual_eligible_proposals=decision["eligible_proposals"],
        residual_decision=decision["status"],
        residual_proposal_exclusions=excluded,
    )


def read_case(ident):
    root = DS29 if ident.startswith("DS29-") else ARCHIVE
    directory = root / f"{ident}-r0"
    receipt_raw = (directory / "baseline-execution.json").read_bytes()
    receipt = json.loads(receipt_raw)
    worker = receipt["worker"]
    raw = (directory / "baseline/experimental-evidence.zip").read_bytes()
    digest = worker["artifact"]["sha256"]
    if (
        receipt["role"] != "baseline"
        or receipt["status"] != "complete"
        or worker["source_sha256"] != SOURCE_SHA256
        or sha256(raw) != digest
    ):
        raise ValueError(f"{ident} lacks an intact frozen no-repair archive")
    with ZipFile(io.BytesIO(raw)) as archive:
        values = archive.read("values.json")
    if _field(values, "request_sha256") != receipt["request_sha256"]:
        raise ValueError(f"{ident} checkpoint request differs from the archive receipt")
    return dict(
        id=ident,
        archive_sha256=digest,
        archive_receipt_sha256=sha256(receipt_raw),
        request_sha256=receipt["request_sha256"],
        **counts(values),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    ds26, files = _selection("ds26-common127")
    roof, _ = _selection("roof16")
    ids = ds26 + [ident for ident in roof if ident.startswith("DS29-")]
    if len(ids) != 135 or len(set(ids)) != len(ids):
        raise ValueError("expected the 135 frozen matched cases")
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(read_case, ids))
    receipt = dict(roster_sha256=files["panels.json"], source_sha256=SOURCE_SHA256, rows=rows)
    save_json(args.out, receipt)


if __name__ == "__main__":
    main()
