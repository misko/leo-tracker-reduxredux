"""Apply the sealed 0218 carrier diagnostic to two closed saved half-blends."""

import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import held_cfo_fixed_residual as prior
import masked_cfo_0218_installed_agreement as method


HERE = Path(__file__).resolve().parent
FIELD = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases")
CASES = {
    "DS30-0019": ("5a5307be75290e5bed14cb42380e47cd9679030a327fdcce2fa1fd2f3c910719", 366),
    "DS30-0274": ("7e2e78392701820e6a2667adc6ba6f2dfbfec1f7eb1ee5017d50a775b773c28c", 499),
}
PINS = {**method.PINS,
        "held_cfo_fixed_residual.py": "9ff602aa6d466c155d954a26ecca844b744cb83b6d095538c0573333b6bcabbb",
        "masked_cfo_0218_installed_agreement.py": "86b720ec97a74a21c4dc2d92621aa9531657bdbaa779fab2bb88c86c8f626c24"}


def capsules(case):
    if case == "DS30-0019":
        closed = prior.read(prior.ORIGINAL / "prediction-seal.json", prior.SEALS["original19"])
        recap = prior.read(prior.ORIGINAL / "ordinary-recovered.json", closed["products"]["ordinary"]["receipt_sha256"])
        original = prior.read(prior.ORIGINAL / "native.json", prior.ORIGINAL_0019)
        witness, _ = prior.load_publication(prior.ORIGINAL / "ordinary", recap["terminal"],
                                            recap["witness_sha256"], "sha256:"+prior.ORIGINAL_0019)
        edited, _, plan, run = prior.capsule(prior.BLEND, prior.SEALS["blend19"], case)
        old = recap["witness_sha256"]
    elif case == "DS30-0274":
        original, (witness, _), _, ordinary = prior.capsule(
            prior.TRANSFER / "ordinary-capsule/output", prior.SEALS["original274"], case)
        edited, _, plan, run = prior.capsule(prior.TRANSFER / "half-blend-capsule/output", prior.SEALS["blend274"], case)
        old = ordinary["witness"]
    else:
        raise ValueError("Only the two declared saved workers are enrolled")
    ledger = plan["change"]["edits"]
    native, revised, changes = (prior.digest(doc) for doc in (original, edited, ledger))
    if (native != plan["original_native_sha256"] or revised != run["input"]
            or revised != plan["change"]["derived_native_sha256"]
            or changes != plan["change"]["recipe"]["edit_sha256"] or len(ledger) != CASES[case][1]):
        raise ValueError("The ordinary, edited or sealed edit digest failed to reproduce")
    delta, winners, _ = prior.signed_edits(original, edited, ledger)
    owners = {arm: prior.owner_rows(witness, arm, winners) for arm in prior.ARMS}
    bindings = dict(ordinary_native_sha256=native, edited_native_sha256=revised, edits_sha256=changes,
                    publication_witnesses=[old, run["witness"]], verified_edits=len(delta))
    return original, {edit["observation_id"]: edit for edit in ledger}, owners, bindings


def installed(case, original, signed):
    base = FIELD / case
    pin, _ = CASES[case]
    pair = prior.read(base / "pair.json", pin)
    if (pair["state"] != "observed_pair" or not pair["verified_pair"] or not pair["chronological"]
            or set(pair["actual_order"]) != {"installed", "successor"}):
        raise ValueError("Expected the authenticated original field pair")
    runs, folders = {}, {}
    for role in ("installed", "successor"):
        root = base / role / f"attempt-{pair['generation']:06d}"
        run = prior.read(root / "result.json", pair["attempt_result_sha256"][role])
        if (run["algorithm"] != role or run["generation"] != pair["generation"]
                or run["process"]["exit_code"] or run["outcome"] != "complete"):
            raise ValueError("The original field acquisition is incomplete")
        runs[role], folders[role] = run, root / "publication"
    source = prior.read(base / "authority.json", pair["authority_sha256"])
    if any(run["raw_identity"] != source for run in runs.values()):
        raise ValueError("Independent receiver acquisition has a different raw authority")
    packets = {}
    for role, path in folders.items():
        matches = list((path / "fast-scan-automatic-work").glob("*/detections.json"))
        if not matches:
            raise FileNotFoundError(errno.ENOENT, "No sealed native packet", path)
        if len(matches) != 1:
            raise ValueError("Expected one signed native packet for each role")
        packets[role] = signed.read_native(path, runs[role]["native_sha256"], path=matches[0])
    full, mixed = (packets[role] for role in ("installed", "successor"))
    if (full["provenance"]["detector_sha256"] != method.FULL or mixed != original
            or full["source"]["raw_recording_authority_digest"] != source["raw_authority_sha256"]
            or any(full["source"][key] != mixed["source"][key] for key in ("capture_end_utc_ns", "probe_ms"))):
        raise ValueError("Native full receiver or original mixed packet changed")
    return full, dict(pair_sha256=pin, installed_native_sha256=runs["installed"]["native_sha256"],
                      original_attempts=pair["attempt_result_sha256"])


def receiver_view(rows, opportunities, evaluate, windows, alias):
    partitions = {0: [], 1: []}
    for oid, value in rows.items():
        radio = opportunities[oid]["radio"]
        if radio not in partitions:
            raise ValueError("Edited opportunity does not identify one of the two native receivers")
        partitions[radio].append(value)
    return {str(rx): method.summarize(values, evaluate, windows, alias) for rx, values in partitions.items()}


def score_case(case, signed, held):
    mixed, edits, owners, bindings = capsules(case)
    stock, field = installed(case, mixed, signed)
    observed, full = (signed.opportunities(native) for native in (mixed, stock))
    signed.bind_pair(stock, mixed, full, observed)
    for native, lanes in ((mixed, observed), (stock, full)):
        saved = {key: row["factor"][prior.HERTZ] for key, row in lanes.items() if row["factor"] is not None}
        winners = {row["observation_id"]: row["measured_cfo_hz"] for row in method.residual.original_winners(native)}
        if saved != winners:
            raise ValueError("The signed comparison winner differs from the fixed-residual extractor")
    rows = method.matched_rows(edits, observed, full, held.aligned_errors)
    metrics = (held.evaluate, held.odd.WINDOWS, signed.ALIAS)
    return dict(status="verified", binding=bindings | field, signed_pairs_sha256=prior.digest(rows),
                by_receiver=receiver_view(rows, observed, *metrics), **method.view(rows, owners, *metrics))


def main():
    if os.sched_getaffinity(0) != {3}:
        raise ValueError("Require CPU 3 for the retrospective saved readback")

    def no_raw(event, args):
        if event == "open" and isinstance(args[0], (bytes, str)):
            path = Path(os.fsdecode(args[0])).resolve()
            if (path.suffix == ".tle" or "fast-scan-recordings" in path.parts
                    or path.name in ("evaluation-reference.json", "reference-audit.json")
                    or FIELD in path.parents and not any(path.is_relative_to(FIELD / case) for case in CASES)):
                raise RuntimeError("The audit reads only sealed data for the two declared cases")

    sys.addaudithook(no_raw)
    for name, pin in PINS.items():
        method.residual.checked(HERE / name, pin)

    import signed_cfo_time_readout as signed
    from reports.ALGO08.v3 import held_short_cfo_shrink as held

    if held.odd.WINDOWS != ((250, 2), (2250, 6)) or held.odd.PERIOD != 40_000/3:
        raise ValueError("The frozen 0218 agreement windows changed")
    results = {}
    for case in CASES:
        try:
            results[case] = score_case(case, signed, held)
        except FileNotFoundError as error:
            results[case] = dict(status="missing_saved_artifact", path=str(error.filename))
    return dict(cases=results, source_pins=PINS, waveform_reads=0, solver_runs=0,
                protocol_sha256=sha256((HERE/"held-installed-carrier-transfer-protocol.md").read_bytes()).hexdigest())


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True, separators=(",", ":"), allow_nan=False))
