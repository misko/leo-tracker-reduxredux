"""Build the fresh two-recording figure from sealed late-preflight worker files."""

from ..__main__ import read_predictions, save_json
from ..scoring import validate_result
from . import full_receiver_comparison as authority
from . import late_preflight_live as fresh
from . import late_preflight_trial as trial
from . import pruned_finish_eval as aligned
from .phase_support_results import pack

CHART = "late-preflight-live"
FOLDER = trial.REPORT / "live"
POSITIONS = "positions.jsonl.gz"
MATCH = (*trial.MATCH, "input_sha256", "scientific_request_sha256")


def plot_pair(row, control, request):
    binding = row["native_binding"]
    authority.require_fields(binding, dict(id=row["id"]))
    authority.require_fields(
        control,
        dict(
            {k: binding[k] for k in ("id", "input_sha256", "native_sha256", "catalog_sha256")},
            method=aligned.STOCK,
            request_sha256=binding["frozen_request_sha256"],
            result=row["control"],
        ),
    )
    expected = dict(scientific_request_sha256=binding["scientific_request_sha256"])
    authority.require_fields(row["request"], expected)
    authority.require_fields(request, expected)
    results = {fresh.candidate.METHOD: row["result"], aligned.STOCK: control["result"]}
    for result in results.values():
        validate_result(result)
    common = {k: binding[k] for k in ("id", *MATCH)}
    return [dict(common, method=name, result=result) for name, result in results.items()]


def build():
    cases = list(fresh.ROSTER)
    evidence_name = "evidence-lock.json"
    comparison_name = "comparison.json"
    required = [comparison_name]
    for ident in cases:
        required.extend([f"{ident}-worker-result.json", f"{ident}-run-lock.json"])
    lock = authority.seal(FOLDER, evidence_name, required)
    authority.seal(aligned.HISTORICAL, "prediction-lock.json", (POSITIONS, "matched-requests.json"))
    controls = read_predictions(aligned.HISTORICAL / POSITIONS)
    matched = authority.read(aligned.HISTORICAL / "matched-requests.json")
    comparison = authority.read(FOLDER / comparison_name)
    authority.roster_matches([r["id"] for r in comparison], cases, CHART)
    positions = []
    for row in comparison:
        ident = row["id"]
        raw_name = f"{ident}-worker-result.json"
        run = authority.read(FOLDER / f"{ident}-run-lock.json")
        authority.require_fields(
            run,
            dict(
                inputs=row["native_binding"],
                aligned_lock_sha256=authority.sha(aligned.armijo_aligned_trial.SEAL),
                aligned_predictions_sha256=authority.sha(aligned.HISTORICAL / POSITIONS),
            ),
        )
        authority.require_fields(
            row,
            dict(
                lock=run,
                raw_result_sha256=lock["files"][raw_name],
                result=authority.read(FOLDER / raw_name),
            ),
        )
        positions.extend(plot_pair(row, controls[ident], matched[ident]))
    pack(FOLDER / POSITIONS, positions)
    names = (POSITIONS, comparison_name, evidence_name)
    save_json(
        FOLDER / "roof-figure-lock.json",
        dict(cases=cases, files={name: authority.sha(FOLDER / name) for name in names}),
    )
    chart = dict(
        id=CHART,
        method=fresh.candidate.METHOD,
        scope="roof",
        cases="sealed",
        title="Fresh late-preflight receiver checks",
        caption=(
            "Fresh stored-GLRT workers and sealed same-request aligned controls. "
            "DS26-0066 ran reassociation. DS29-0082 bypassed it. Paired positions coincide."
        ),
        seal="roof-figure-lock.json",
        provenance=[comparison_name, evidence_name],
        series=[
            dict(
                key="one", label="Fresh RF preflight", file=POSITIONS, value=fresh.candidate.METHOD
            ),
            dict(
                key="stock",
                label="Sealed aligned finish",
                file=POSITIONS,
                value=aligned.STOCK,
                match=list(MATCH),
            ),
        ],
    )
    save_json(FOLDER / "figures.json", dict(version=1, charts=[chart]))


if __name__ == "__main__":
    build()
