"""Bind the previously qualified native rank-zero helper on 20 ms anchor calls."""

import ctypes
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import mixed_aperture_receiver as mixed


ARTIFACT = Path("/var/tmp/leo-algo08v3-primary-schedule-trial-native/primary.so")
LIBRARY_SHA256 = "5e9667bbe38c1aeb897189c5ebff0a05cd400fd21f41703a279a384c202f3f50"
SOURCE_SHA256 = "d825bca622578e3c502305541ab5e8e7655ce6085d0e61e88e09caeb40dbfb4e"
STOCK_LIBRARY = Path("/opt/leo-algo08/algo08v3/payload/receiver.so")
RECIPE_FIELD = "full_anchor_primary_only"


def definition():
    return dict(symbol="primary_factors", sha256=LIBRARY_SHA256, helper_source_sha256=SOURCE_SHA256,
                aperture_samples=200_000, selection="verified native rank zero only")


def single_anchor_options(recipe):
    """Validate the sole permitted variant before checking the original base recipe."""
    base = dict(recipe)
    measured = base.pop(RECIPE_FIELD, None)
    if measured is not None and measured != definition():
        raise ValueError("Unrecognized primary-only full anchor recipe")
    return base


def bound_library(path):
    mixed.verified(path, LIBRARY_SHA256)
    mixed.verified(STOCK_LIBRARY, mixed.INSTALLED_SHA)
    return ctypes.CDLL(str(path.resolve())).primary_factors


def first_only(path, callback):
    callback.argtypes = path.call.argtypes
    callback.restype = path.call.restype
    path.call = callback
    path.maximum = 1
    return path


def anchor_witness(native):
    from anchor_exposure import enroll, metadata
    from leo.contracts.digests import canonical_digest

    anchors, short = [], []
    for row, event in zip(native["source"]["probes"], enroll(native), strict=True):
        (anchors if event[4] == "anchor" else short).append(row)
    return dict(anchors=anchors, short_probes_sha256=canonical_digest(short),
                ordered_metadata_sha256=canonical_digest(list(map(metadata,native["source"]["probes"]))))


class AnchorPrimaryMixer(mixed.MixedApertureDetector):
    def __init__(self, short_binary, short_sha, helper):
        super().__init__(short_binary, short_sha, full_coverage=True)
        self.helper = helper

    @contextmanager
    def detector(self, *args, **kwargs):
        ordinary = mixed.NativePath

        def factory(binary, asset, mode):
            path = ordinary(binary, asset, mode)
            return first_only(path, self.helper) if mode == "full" else path

        with ExitStack() as scope:
            with patch.object(mixed, "NativePath", factory):
                receive = scope.enter_context(super().detector(*args, **kwargs))
            yield receive
