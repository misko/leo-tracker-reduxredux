"""Separate research registration for the reviewed guarded 20 ms anchors."""

from collections import Counter
from contextlib import ExitStack, contextmanager
import ctypes as ct
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import mixed_aperture_receiver as mixed


HERE = Path(__file__).resolve().parent
FIELD = "guarded_full_anchor"
LIBRARY_SHA256 = "f13593d12d91c631cf66377431080c42ca2f0b9553de4b8bc767390e2243f32c"
SOURCE_PINS = {
    "anchored_phase.inc": "8b0951fbb70d202924d734f954d8ebc774834abb59f4c1463301caf570cb794b",
    "anchored_phase.py": "ff5cd0f9bf48d21b6dc24157cdc401bce001c55b95154f1ec246576a41a45b5f",
    "../../../tools/pipeline_eval/variants/experimental/receiver_fractional_exact.inc":
        "7e6e4d0d0bd3074963a50340e645f66023c3a273ea2fc7cd6279496f2bef2a2b",
    "measurements/anchored-phase.json.gz": "2cb94ea15f0382b85093db41976220fe63aab71c2c6ffd4f5c63b186bf9c7232",
}


class AuditEvent(ct.Structure):
    _fields_ = [("epoch", ct.c_uint), ("flags", ct.c_uint),
                *((k, ct.c_double) for k in ("frequency", "offset", "residual", "exact", "control"))]


class NativeAudit:
    def __init__(self, library):
        self.take = library.anchored_take_audit
        self.take.argtypes, self.take.restype = (ct.POINTER(AuditEvent), ct.POINTER(ct.c_uint64)), ct.c_int
        self.events, self.counts = (AuditEvent*8)(), (ct.c_uint64*2)()

    def drain(self, *, rows=False):
        count = self.take(self.events, self.counts)
        attempted, accepted = self.counts
        if not 0 <= count <= len(self.events) or not 0 <= accepted <= attempted:
            raise ValueError("The original rotation audit is inconsistent")
        events = [tuple(getattr(event, k) for k, _ in AuditEvent._fields_) for event in self.events[:count]] if rows else None
        return dict(calls=1, verifier_evaluations=count, recurrence_attempted=attempted,
                    recurrence_accepted=accepted, exact_fallbacks=attempted-accepted), events


def definition():
    return dict(kind="guarded-absolute-phase-32-full-anchor-only", full_sha256=LIBRARY_SHA256,
                original_full_sha256=mixed.INSTALLED_SHA, source_sha256=SOURCE_PINS,
                adapter_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                exact_fallback="original absolute-phase verifier", anchor_stride=32,
                margin_gate=.025, strong_margin=.1, full_scans=2, independent_cfo_refinement=False)


def checked_library(path):
    for source, pin in SOURCE_PINS.items():
        mixed.verified(HERE / source, pin)
    mixed.verified(path, LIBRARY_SHA256)
    return Path(path).resolve(strict=True)


def unguarded(recipe):
    option = recipe.get(FIELD)
    if FIELD not in recipe:
        return recipe
    if option != definition():
        raise ValueError("Unknown guarded full anchor registration")
    return {k: v for k, v in recipe.items() if k != FIELD}


class GuardedFullPath(mixed.NativePath):
    def __init__(self, path, asset, audit):
        super().__init__(path, asset, "full")
        self.audit = NativeAudit(self.native.lib)
        self.counters = audit

    def run(self, samples, lane, center):
        measured = super().run(samples, lane, center)
        counts, _ = self.audit.drain()
        self.counters.update(counts)
        return measured


class GuardedFullDetector(mixed.MixedApertureDetector):
    def __init__(self, short, pin, full):
        super().__init__(short, pin, full_coverage=True)
        self.full = full
        self.rotation = {}

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        original = mixed.NativePath

        def open_path(path, asset, mode):
            if mode == "short_primary":
                return original(path, asset, mode)
            if mode != "full" or Path(path) != Path(binary):
                raise ValueError("Unknown native receiver path")
            return GuardedFullPath(self.full, asset, self.rotation.setdefault(edge, Counter()))

        with ExitStack() as stack:
            with patch.object(mixed, "NativePath", open_path):
                receive = stack.enter_context(super().detector(method, edge, binary=binary, pilot=pilot))
            yield receive

    def receipt(self):
        return super().receipt() | {FIELD: dict(full_sha256=LIBRARY_SHA256,
                                              by_edge=[dict(edge=edge, **counts) for edge, counts in sorted(self.rotation.items())])}


def configure(short, short_pin, parent, library):
    """Build the normal receiver and recipe at the same opt-in dispatch point."""
    from full_short_run import SPARSE_EIGHT_MS_RECIPE_SHA, SPARSE_EIGHT_MS_SHA, verify_recipe

    if short_pin != SPARSE_EIGHT_MS_SHA:
        raise ValueError("Guarded full anchors keep the registered sparse 8 ms primary")
    verify_recipe(parent, SPARSE_EIGHT_MS_RECIPE_SHA)
    return GuardedFullDetector(short, short_pin, checked_library(library)), dict(parent, **{FIELD: definition()})
