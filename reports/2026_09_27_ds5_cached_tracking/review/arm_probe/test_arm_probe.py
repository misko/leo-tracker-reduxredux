import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def test_plan_is_small_metadata_only_and_excludes_holdout():
    plan=json.loads((HERE/"plan.json").read_text())
    assert plan["holdout_excluded"] is True
    assert len(plan["cases"])==16
    assert {c["split"] for c in plan["cases"]}=={"dev","control"}
    assert sum(c["split"]=="dev" for c in plan["cases"])==4
    assert {c["rate_hz"] for c in plan["cases"]}=={2_500_000,5_000_000}


def test_build_receipt_pins_all_three_arm_binaries():
    receipt=json.loads((HERE/"build.receipt.json").read_text())
    assert receipt["scope"].startswith("stateless saved-IQ")
    assert {x["method"] for x in receipt["builds"]}==set(json.loads((HERE/"plan.json").read_text())["methods"])
    for build in receipt["builds"]:
        assert digest(HERE/build["method"])==build["binary_sha256"]
        assert build["sources_sha256"]


def test_qemu_is_explicitly_not_timing_evidence():
    receipt=json.loads((HERE/"qemu.functional.json").read_text())
    assert receipt["timing_valid"] is False
    assert len(receipt["cases"])==2
    for case in receipt["cases"]:
        assert all(x["passed"] for group in (case["fp64_fftw_vs_builtin"],case["aligned_fp32_vs_builtin"]) for x in group)
