"""Seal the relocated original's ordered pair for the immutable campaign."""

import argparse
import json
import os
from pathlib import Path
from shutil import copytree
import sys
from time import monotonic, sleep

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import ds30_paired_evaluation as study
from ds30_paired_inputs import ARMS, checked, digest, encode, publish, read, write
from ds30_relocated_original import CASES, PLAN_PIN, measured_pair, plan_document, verify_encoded_successor


ROOT = study.OUTPUT
PRECEDING = ROOT / "cases" / "DS30-0124"


def overlay(proof_file, pin):
    proof_body = checked(proof_file, pin)
    proof = json.loads(proof_body)
    case = proof["case"]
    if case not in CASES:
        raise ValueError("This recording is outside the nine exact migrations")
    result = ROOT / "relocation" / case
    pair = study.summary(result)
    prior = read(result / "relocation.json")
    if (proof["plan_sha256"] != PLAN_PIN or prior["proof_sha256"] != pin
            or prior["initial_campaign_disposition"]["state"] != "invalid_original_input"
            or pair["generation"] != 2 or not pair["verified_pair"] or not pair["chronological"]
            or pair["actual_order"] != proof["assigned_order"]):
        raise ValueError("The sidecar is not the ordered, proven original pair")
    encoded = read(result / "native-encoded-auth.json")
    inputs = proof["inputs"]
    if (read(result / "authority.json") != inputs["authority"] or pair["authority_sha256"] != inputs["authority_sha256"]
            or encoded["both_raw_authority"] != proof["reopened"]["raw_authority_sha256"]
            or encoded["installed_contract"] != proof["stock_reader_sources"]):
        raise ValueError("The normal raw-reader authentication does not bind the reopening proof")
    attempts = {}
    for arm in ARMS:
        observed, path = study.outcome(result, arm)
        actual = digest(path.read_bytes())
        if (observed["raw_identity"] != inputs["authority"] or pair["attempt_result_sha256"][arm] != actual
                or observed["generation"] != 2 or observed["authority_sha256"] != inputs["authority_sha256"]):
            raise ValueError("An original timed arm changed its attested authority or attempt")
        attempts[arm] = dict(path=str(path.relative_to(ROOT)), sha256=actual)
    if verify_encoded_successor((ROOT / attempts["successor"]["path"]).parent / "publication", proof) != encoded["successor"]:
        raise ValueError("The successor raw encoded proof changed")
    prior_body = encode(prior["initial_campaign_disposition"]) + b"\n"
    value = dict(schema="ds30-paired-relocation-v1", plan_sha256=PLAN_PIN, case=case, generation=2,
                 accession=proof["accession"], historical=proof["historic"], canonical_reopened=proof["reopened"],
                 original_preflight_sha256=digest(prior_body), paired_attempts=attempts, paired_scope=pair,
                 proof_sha256=pin, proof_path=str((result / "proof.json").relative_to(ROOT)),
                 encoded_auth_sha256=digest((result / "native-encoded-auth.json").read_bytes()))
    publish(result / "proof.json", proof_body)
    write(result / "overlay.json", value)
    return value


def run_wait(proof, pin, max_wait):
    if not 0 < max_wait <= 1800:
        raise ValueError("Keep the detached 0452 admission window bounded")
    deadline = monotonic() + max_wait
    case = json.loads(checked(proof, pin))["case"]
    if case not in CASES or study.summary(ROOT / "cases" / case).get("state") != "invalid_original_input":
        raise ValueError("Reopen only a documented terminal relocation rejection")
    sidecar = ROOT / "relocation" / case
    if study.summary(sidecar):
        overlay(proof, pin)
        combine()
        return 0
    while monotonic() < deadline:
        retained_attempts(sidecar)
        if not (PRECEDING / "pair.json").is_file():
            sleep(10)
            continue
        if study.summary(PRECEDING)["state"] != "observed_pair":
            raise ValueError("The preceding immutable case has no measured pair disposition")
        quiet, _ = study.quiet_window()
        if quiet:
            try:
                status = measured_pair(proof, pin, sidecar)
            except BlockingIOError:
                status = 75
            if status == 0:
                overlay(proof, pin)
                combine()
                return 0
        sleep(10)
    return 75


def retained_attempts(sidecar):
    for arm in ARMS:
        for attempt in (sidecar / arm).glob("attempt-*"):
            result = attempt / "result.json"
            if not result.is_file():
                raise ValueError(f"Preserve and examine the interrupted arm before any restart: {attempt}")
            if read(result)["outcome"] not in study.VERIFIED:
                raise ValueError(f"Preserve the failed verification without a retry: {attempt}")


def link_immutable(source, target):
    if os.path.exists(target):
        if not os.path.samefile(source, target):
            raise ValueError("A resumed relocation cannot overwrite existing ledger bytes")
    else:
        os.link(source, target)
    return target


def attach(case):
    """Commit the overlay to the main ledger between controller invocations."""
    from ds30_paired_evaluation import export

    sidecar = ROOT / "relocation" / case
    retired = ROOT / "cases" / case
    with study.exclusive(ROOT / "driver.lock", "a+b"):
        side = read(sidecar / "overlay.json")
        if side != overlay(ROOT / side["proof_path"], side["proof_sha256"]):
            raise ValueError("The case overlay was not independently sealed")
        prior, retained = (retired / name for name in ("pair.json", "original-preflight.json"))
        if prior.read_bytes() == (sidecar / "pair.json").read_bytes():
            checked(retained, side["original_preflight_sha256"])
            export(ROOT, plan_document())
            return
        publish(retained, checked(prior, side["original_preflight_sha256"]))
        publish(retired / "relocation-overlay.json", (sidecar / "overlay.json").read_bytes())
        publish(retired / "authority.json", (sidecar / "authority.json").read_bytes())
        proof = read(sidecar / "proof.json")
        write(retired / "input.json", proof["inputs"] | {"relocation_proof_sha256": side["proof_sha256"]})
        for arm in ARMS:
            copytree(sidecar / arm, retired / arm, copy_function=link_immutable, dirs_exist_ok=True)
        publish(prior, (sidecar / "pair.json").read_bytes(), replace=True)
        export(ROOT, plan_document())


def update_row(row, side):
    arm = row["algorithm"]
    line = side["paired_attempts"][arm]
    attempt = json.loads(checked(ROOT / line["path"], line["sha256"]))
    evidence, process, validate = attempt["evidence"], attempt["process"], attempt["validation"]
    receipt = evidence["receipt"]
    pair = side["paired_scope"]
    if (row["raw_identity_sha256"] != side["accession"]["physical_content_sha256"]
            or row["manifest_raw_authority_sha256"] != side["accession"]["manifest_raw_authority_sha256"]
            or row["order"] != pair["actual_order"] or receipt["session_id"] != side["canonical_reopened"]["session_id"]
            or evidence["raw_authority"] != side["canonical_reopened"]["raw_authority_sha256"]):
        raise ValueError("The measured overlay is outside its original roster row")
    return row | dict(admission_state="observed_pair", acquisition_verified=True, outcome=attempt["outcome"],
        elapsed_s=attempt["elapsed_s"], cpu_s=attempt["cpu_s"], timing_scope=attempt["timing_scope"],
        child_elapsed_s=process["elapsed_s"], child_cpu_s=process["cpu_s"],
        child_started_unix_ns=process["started_unix_ns"], child_finished_unix_ns=process["finished_unix_ns"],
        validator_elapsed_s=validate["elapsed_s"], validator_cpu_s=validate["cpu_s"],
        input_blocks=process["input_blocks"], output_blocks=process["output_blocks"],
        verified_pair=True, same_lease=pair["same_lease"], generation=2, actual_order=pair["actual_order"],
        authority_sha256=attempt["authority_sha256"], arms=evidence["arms"],
        requested_raw_authority_sha256=side["canonical_reopened"]["raw_authority_sha256"],
        raw_authority_sha256=evidence["raw_authority"], historic_raw_authority_sha256=side["historical"]["raw_authority_sha256"],
        canonical_reopened_inventory_sha256=side["canonical_reopened"]["inventory_sha256"],
        relocation_proof_sha256=side["proof_sha256"], prior_preflight_sha256=side["original_preflight_sha256"],
        reached_solver=attempt.get("reached_solver", attempt["outcome"] == "complete"),
        attempt=line["path"], attempt_result_sha256=line["sha256"], receipt_sha256=digest(encode(receipt)),
        terminal_sha256=receipt.get("terminal_sha256"), reason=attempt.get("reason") or evidence.get("reason"))


def combine():
    """Use one atomic live export snapshot and all independently sealed overlays."""
    plan = plan_document()
    source = (ROOT / "rows.jsonl").read_bytes()
    original = [json.loads(row) for row in source.splitlines()]
    expected = {(row["case"], arm) for row in plan["cases"] for arm in ARMS}
    if len(original) != len(expected) or {(row["case"], row["algorithm"]) for row in original} != expected:
        raise ValueError("The live export differs from the entire frozen roster")
    replacement = {}
    for case in CASES:
        marker = ROOT / "relocation" / case / "overlay.json"
        if marker.is_file():
            old = read(marker)
            current = overlay(ROOT / old["proof_path"], old["proof_sha256"])
            if current != old or current["case"] != case:
                raise ValueError("A relocation overlay changed after its independent seal")
            replacement[case] = current
    combined = [update_row(row, replacement[row["case"]]) if row["case"] in replacement else row for row in original]
    body = b"".join(encode(row) + b"\n" for row in combined)
    publish(ROOT / "rows-with-relocations.jsonl", body, replace=True)
    publish(ROOT / "rows-with-relocations-seal.json", encode(dict(
        plan_sha256=PLAN_PIN, ledger_snapshot_sha256=digest(source), combined_sha256=digest(body),
        proofs={case: row["proof_sha256"] for case, row in replacement.items()},
        pending_relocation_cases=sorted(set(CASES) - replacement.keys()))) + b"\n", replace=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for mode in ("run", "seal"):
        command = actions.add_parser(mode)
        command.add_argument("proof", type=Path)
        command.add_argument("proof_sha256")
        if mode == "run":
            command.add_argument("--max-wait", type=int, default=900)
    attach_cmd = actions.add_parser("attach")
    attach_cmd.add_argument("case", choices=CASES)
    actions.add_parser("combine")
    args = parser.parse_args()
    if args.action == "run":
        return run_wait(args.proof, args.proof_sha256, args.max_wait)
    if args.action == "seal":
        overlay(args.proof, args.proof_sha256)
    elif args.action == "attach":
        attach(args.case)
    else:
        combine()
    return 0


if __name__ == "__main__":
    sys.exit(main())
