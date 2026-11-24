"""Bind the frozen 12 ms adaptive timing DSO to the original guarded receiver."""

from contextlib import contextmanager
import ctypes as ct
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


DSO_SHA = "abb9b25965840e491f47775a2c4b415f34948d18deec0a4bee7a6ec4703fcbe9"
SOURCE_SHA = "acc72c13fcfff2efb0e0e9c08ee947731fb543f86aaf003693942a41f2e522f9"
RULE = (1666, 1.1)


@contextmanager
def activate(path):
    import anchored_cfo_raw as guarded

    path = path.resolve(strict=True)
    source = Path(__file__).with_name("cross_lag_timing.inc")
    if sha256(path.read_bytes()).hexdigest() != DSO_SHA or sha256(source.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("The frozen guarded 12 ms timing DSO or its source differs")
    native = ct.CDLL(str(path))
    setting = native.set_cross_lag_rule
    setting.argtypes = (ct.c_int, ct.c_int, ct.c_double)
    setting.restype = None
    verify, original_recipe = guarded.verified_pack, guarded.recipe

    def library(pack):
        return verify(pack) | {"short.so": path}

    def recipe(*args):
        return dict(original_recipe(*args), guarded_cross_lag_timing=dict(
            short_sha256=DSO_SHA, source_sha256=SOURCE_SHA, samples=120_000, timing_lags=[28, 44],
            narrow_rows=4, expanded_rows=12, max_distance=RULE[0], minimum_contrast=RULE[1]))

    setting(3, *RULE)
    try:
        with patch.object(guarded, "verified_pack", library), patch.object(guarded, "recipe", recipe):
            yield
    finally:
        setting(0, *RULE)
