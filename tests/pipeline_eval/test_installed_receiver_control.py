import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import installed_receiver_control as stock
import integrated_original_batch as batch


def test_reference_pin_is_optional_and_does_not_enable_receiver():
    pin = "sha256:" + "a" * 64
    assert not stock.required(SimpleNamespace())
    assert stock.required(SimpleNamespace(installed_stock_receiver=True))
    assert stock.required(SimpleNamespace(installed_stock_receiver=True, assert_stock_native_sha256=pin))
    with pytest.raises(ValueError, match="requires a tagged native SHA-256"):
        stock.required(SimpleNamespace(assert_stock_native_sha256=pin))
    with pytest.raises(ValueError, match="requires a tagged native SHA-256"):
        stock.required(SimpleNamespace(installed_stock_receiver=True, assert_stock_native_sha256="not a digest"))


def test_installed_mode_preserves_only_the_original_complete_source():
    base = dict(history_risk_route=True, verify_original_once=True)
    stock.verify_mode(SimpleNamespace(**base), {"schedule": "all"})
    for field in ("packed_ci16_map", "whole_stereo_blocks", "select_before_cfo", "selective_full_20ms_recheck",
                  "full_anchor_primary_library", "guarded_full_anchor_library"):
        with pytest.raises(ValueError, match="released all-visit continuation"):
            stock.verify_mode(SimpleNamespace(**base, **{field: True}), {"schedule": "all"})
    for spec in ({"schedule": "bursts"}, {"schedule": "all", "fractional_score_selection": True}):
        with pytest.raises(ValueError, match="released all-visit continuation"):
            stock.verify_mode(SimpleNamespace(**base), spec)


def test_batch_passes_separate_selector_control_and_optional_assertion():
    pin = "sha256:" + "a" * 64
    kwargs = {k: Path("/" + k) for k in ("recording", "archive", "region", "bulk_root")}
    artifact = {"path": "/checked.so", "sha256": pin}
    book = {"native": {flag: artifact for flag in (*batch.PATH_OPTIONS, *batch.SIGNED_OPTIONS)}, "portable_producer": artifact}
    authority = {"archive_sha256": pin}
    mixed = batch.original_argv(SimpleNamespace(**kwargs), book, authority)
    installed = batch.original_argv(SimpleNamespace(**kwargs, installed_stock_receiver=True), book, authority)
    verified = batch.original_argv(SimpleNamespace(**kwargs, installed_stock_receiver=True, assert_stock_native_sha256=pin),
                                   book, authority)
    assert installed == [*mixed, "--installed-stock-receiver"]
    assert verified == [*installed, "--assert-stock-native-sha256", pin]
