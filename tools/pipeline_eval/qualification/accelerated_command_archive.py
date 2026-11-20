"""Independently replay the compact receiver on authenticated original factors."""

import argparse
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from tools.pipeline_eval import iq_service, original_receiver, whole_iq
from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification.full_v5_check import _sha

CASE = "DS26-0020"


def archived_fit(smoke, out, cpu=19):
    source = smoke / "source-lock.json"
    lock = whole_iq.read(source)
    case = lock["case"]
    if lock["id"] != CASE or not lock["smoke"] or lock.get("interior_guard"):
        raise ValueError("expected the sealed unguarded accelerated smoke for the selected case")
    if lock.get("position_limit_s") != 180 or whole_iq.MEMORY != 512 * 2**20:
        raise ValueError("archived compact fit must use the matched time and memory limits")
    native = whole_iq.checked(
        original_receiver.BULK / case["native"]["path"],
        case["native"]["sha256"],
    )
    out.mkdir(parents=True)
    copy = out / "source-lock.json"
    copy.write_bytes(source.read_bytes())
    attempt = out / "position"
    request = attempt / "recording/request.json"
    request.parent.mkdir(parents=True)
    sha = original_receiver.bind_fresh(case, native, request)
    save_json(attempt / "raw.json", dict(native_sha256=sha, request_sha256=_sha(request)))
    start = perf_counter()
    with patch.object(iq_service, "MODULE", original_receiver.MODULE):
        receipt = original_receiver.service(
            attempt,
            cpu,
            180,
            "position",
            dict(receiver=lock["receiver"]),
        )
    result = dict(
        id=CASE,
        native_path=str(native),
        native_sha256=sha,
        case_request_sha256=case["request"]["sha256"],
        request_sha256=_sha(request),
        source_lock_sha256=_sha(copy),
        cpu=cpu,
        elapsed_s=perf_counter() - start,
        service=receipt,
        position_sha256=_sha(attempt / "position.json") if iq_service.succeeded(receipt) else None,
    )
    save_json(out / "archive-receipt.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("smoke", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--cpu", type=int, default=19)
    args = parser.parse_args()
    receipt = archived_fit(args.smoke, args.out, args.cpu)
    print(receipt["id"], receipt["cpu"], receipt["elapsed_s"], receipt["position_sha256"])
