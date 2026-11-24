"""Recheck eligible short observations while their original CI16 is live."""

from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import mixed_aperture_receiver as mixed
from selective_full_recheck import HISTORY_LENGTH, OLD_BOUND, Shortlist, clocks, full_candidates, rechecked, spent


FIELD = "selective_full_20ms_recheck"
SOURCES = ("live_full_recheck.py", "selective_full_recheck.py", "selective-full-recheck-protocol.md")


def definition():
    from empty_bootstrap import CONTINUATION, EXTRA_SOURCES
    from selective_full_recheck import digest_file

    return dict(past_opportunities=HISTORY_LENGTH, past_counter_samples=OLD_BOUND,
                antenna_lane_key=["edge", "receiver_id", "channel", "actual_rf_hz"],
                continuation_sha256=EXTRA_SOURCES[CONTINUATION], full_native_sha256=mixed.INSTALLED_SHA,
                user_waveform_passes=1,
                sources={name: digest_file(Path(__file__).with_name(name)) for name in SOURCES})


def require_compatible(args):
    if not (getattr(args, "eight_ms_native_history", False) and getattr(args, "sparse8_primary", False)
            and getattr(args, "held_anchor_route", False)) or any(
                getattr(args, name, None) is not None
                for name in ("full_anchor_primary_library", "short_lane_mask", "packed_ci16_map",
                             "packed_ci16_map_sha256", "packed_ci16_codec")) or any(
                getattr(args, name, False)
                for name in ("whole_stereo_blocks", "select_before_cfo", "strict_packed_eight")):
        raise ValueError("Selective full recheck requires the original signed sparse 20/8 ms schedule and held selection")


class LiveFullRecheck:
    def __init__(self, mixer, continuation, constructor):
        self.mixer = mixer
        self.continuation = continuation
        self.constructor = constructor
        self.opportunities = Counter()
        self.calls = []
        self.callback = Counter()

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        from contextlib import ExitStack

        installed_path = mixed.NativePath
        engines = {}

        def capture(library, asset, mode):
            if mode in engines:
                raise ValueError("The installed receiver initialized a duplicate aperture")
            path = installed_path(library, asset, mode)
            engines[mode] = path
            return path

        with ExitStack() as stack:
            with patch.object(mixed, "NativePath", capture):
                original = stack.enter_context(self.mixer.detector(method, edge, binary=binary, pilot=pilot))
            if set(engines) != {"full", "short_primary"} or engines["full"].maximum != 2:
                raise ValueError("The installed full 20 ms alternatives are unavailable")
            history, replacement = Shortlist(self.continuation()), self.continuation()
            full = engines["full"]

            def receive(window):
                short = self.mixer.visits["short_primary"]
                original_rows = original(window)
                begin = clocks()
                mode = "short" if self.mixer.visits["short_primary"] != short else "anchor"
                self.opportunities[mode] += len(original_rows)
                output = []
                for row in original_rows:
                    decision = history.consider(row, mode)
                    contenders, native = None, None
                    if decision["selected"]:
                        target, acquisition = window.target, window.acquisition
                        center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
                        factors, native = full.run(window.samples, row["receiver_id"], center)
                        contenders = full_candidates(factors, self.constructor)
                    chosen, proof = rechecked(row, contenders, replacement)
                    if proof is not None:
                        self.calls.append(dict(decision=decision, base=row, replacement=proof,
                                               native_cpu_ns=native[0], native_wall_ns=native[1]))
                    output.append(chosen)
                self.callback.update(spent(begin))
                return output

            yield receive

    def receipt(self):
        return dict(opportunities=dict(self.opportunities), calls=self.calls, callback=dict(self.callback),
                    native_cpu_ns=sum(row["native_cpu_ns"] for row in self.calls),
                    native_wall_ns=sum(row["native_wall_ns"] for row in self.calls),
                    extra_ci16_retained_bytes=0, extra_native_contexts=0, additional_recording_traversals=0)


def prepare(original, recipe, session, inventory, receipt_file):
    """Retain the held selector byte identity and bind its actual measurement provenance."""
    from continued_cfo_trial import rebinding
    from eight_ms_native_receiver import SAVED_SELECTOR
    from empty_bootstrap import bind_native, checked
    from full_short_run import SPARSE_EIGHT_MS_RECIPE_SHA
    from leo.contracts.digests import canonical_digest
    from preloaded_saved_worker import write

    base = {key: value for key, value in recipe.items() if key != FIELD}
    if canonical_digest(base) != "sha256:"+SPARSE_EIGHT_MS_RECIPE_SHA or recipe.get(FIELD) != definition():
        raise ValueError("Selective recheck does not bind to the checked sparse 20/8 ms recipe")
    checked(Path(__file__).with_name("eight_ms_held_fit.py"), SAVED_SELECTOR)
    from eight_ms_held_fit import select

    packet, witness = select(original, recipe)
    if witness["refinement_calls"]:
        raise ValueError("The held route cannot request a second waveform pass")
    held = witness["receiver_recipe"]
    policy = dict(held["held_native_8ms"], measurement="signed live sparse 8 ms and full 20 ms alternatives; "
                  "causal recheck precedes the unchanged held selector")
    held = dict(held, held_native_8ms=policy)
    packet = rebinding(packet, packet["source"]["probes"], held)
    digest, detector = canonical_digest(packet), canonical_digest(held)
    bind_native(packet, session, inventory, detector[7:], expected=digest)
    witness.update(native_sha256=digest, detector_recipe_sha256=detector, receiver_recipe=held)
    write(receipt_file, witness)
    return packet, held, detector[7:], witness
