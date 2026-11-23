"""Opt in to the reviewed guarded 20/12 ms detector and fixed-epoch CFO tail."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
import ctypes as ct
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import short_cfo_raw as exact


mixed = exact.mixed
ORIGINAL_PROBE = exact.refined_probe
NATIVE_PATH = mixed.NativePath
ORIGINAL_RECIPE = exact.recipe
LIBRARIES = {
    "full.so": "f13593d12d91c631cf66377431080c42ca2f0b9553de4b8bc767390e2243f32c",
    "short.so": "f20605e5a4e487d13548411b0430ea262b9b9c6fba89dae973313d3d0008bb6a",
    "tail.so": "304cb40f0577b972eedd582c3aac39ee3cc24af1cd488b0fb9bbd6b3336da7ae",
    "exact-gather.so": "a09cf653bcb90fb6b05d29650c41d259e2c867824bf0091e3a9a43a10f5dab13",
    "original-cfo.so": exact.LIBRARY_SHA256,
}
SOURCES = {
    "anchored_phase.inc": "8b0951fbb70d202924d734f954d8ebc774834abb59f4c1463301caf570cb794b",
    "anchored_phase.py": "ff5cd0f9bf48d21b6dc24157cdc401bce001c55b95154f1ec246576a41a45b5f",
    "short_cfo_exact_cost.inc": "34717f53d6baf2e9e839c4cb1597dfb88bcd1ce225d4194788c52acedd53f0b1",
    "short_cfo_exact_cost.py": "f149a1ab9c1e1afe0c71b556a78881f9be9beef2c3842c67ceeed091cf0775ea",
    "short_cfo_refine.inc": exact.EXTENSION_SHA256,
    "short_cfo_refine.py": exact.POLICY_SHA256,
    "short_cfo_raw.py": "58b0b80f62e95400722b07895aa833f156697c5fa6c133b76a1047a5578d820b",
    "measurements/anchored-phase.json.gz": "2cb94ea15f0382b85093db41976220fe63aab71c2c6ffd4f5c63b186bf9c7232",
    "../../../tools/pipeline_eval/variants/experimental/receiver_fractional_exact.inc":
        "7e6e4d0d0bd3074963a50340e645f66023c3a273ea2fc7cd6279496f2bef2a2b",
}
BAND_COLLAR_HZ = .001
GUARDS = dict(anchor_stride=32, rounding="FE_TONEAREST", gate_margin=.025, strong_margin=.1,
              spectrum="original conservative radius with recurrence allowance",
              order="original exact two-factor radius retry", tail_step=exact.STEP,
              tail_minimum_retry_coherence=.5, tail_margin_collar=1e-7, tail_coherence_collar=1e-7,
              tail_delta_collar_hz=.001, tail_agreement_collar_hz=.002, tail_band_collar_hz=BAND_COLLAR_HZ)


def specification():
    return dict(schema_version=1, kind="guarded-absolute-phase-32", sources=SOURCES, libraries=LIBRARIES, guards=GUARDS)


def verified_pack(root):
    root = root.resolve(strict=True)
    document = json.loads((root / "pack.json").read_bytes())
    if document != specification():
        raise ValueError("The guarded-phase library pack differs from the reviewed recipe")
    for source, pin in SOURCES.items():
        mixed.verified(HERE / source, pin)
    paths = {name: root / name for name in LIBRARIES}
    for name, path in paths.items():
        mixed.verified(path, LIBRARIES[name])
    return paths


def assemble(root, phase_build, exact_gather, exact_cfo):
    donors = dict(zip(LIBRARIES, (phase_build / "full-anchored/receiver.so", phase_build / "short-anchored/receiver.so",
                                  phase_build / "tail/tail.so", exact_gather, exact_cfo), strict=True))
    payloads = {name: mixed.verified(path, LIBRARIES[name]) for name, path in donors.items()}
    for source, pin in SOURCES.items():
        mixed.verified(HERE / source, pin)
    root.mkdir()
    for name, data in payloads.items():
        (root / name).write_bytes(data)
    (root / "pack.json").write_text(json.dumps(specification(), indent=2, sort_keys=True)+"\n")


class Event(ct.Structure):
    _fields_ = [("epoch", ct.c_uint), ("flags", ct.c_uint)] + [
        (name, ct.c_double) for name in ("frequency", "offset", "residual", "exact", "control")]


class GuardedPath(NATIVE_PATH):
    def __init__(self, path, asset, mode, counts):
        super().__init__(path, asset, mode)
        self.counts = counts
        self.take = self.native.lib.anchored_take_audit
        self.take.argtypes, self.take.restype = (ct.POINTER(Event), ct.POINTER(ct.c_uint64)), ct.c_int
        self.events, self.stats = (Event*8)(), (ct.c_uint64*2)()

    def run(self, samples, lane, center):
        result = super().run(samples, lane, center)
        n = self.take(self.events, self.stats)
        if not 0 <= n <= len(self.events):
            raise ValueError("Guarded-phase verifier audit overflow")
        attempted, accepted = self.stats
        self.counts.update(calls=1, verifier_evaluations=n, recurrence_attempted=attempted,
                           recurrence_accepted=accepted, fractional_exact_fallback=attempted-accepted)
        return result


def refiner(original, path, symbol):
    instance = type(original).__new__(type(original))
    instance.library = ct.CDLL(str(path))
    instance.call = getattr(instance.library, symbol)
    instance.call.argtypes = tuple(original.call.argtypes)
    instance.call.restype = original.call.restype
    return instance


def guarded_probe(probe, waveform, full, policy, center):
    factor, = probe["candidates"]
    original = (tuple(factor[k] for k in exact.FIELDS),)
    diagnostic = policy.refiner.diagnostics(full, waveform, probe["receiver_id"], original)
    if diagnostic is not None:
        cfo = original[0][3]+diagnostic[0]
        if abs(abs(cfo-center)-800_000) < BAND_COLLAR_HZ:
            policy.band_retries += 1
            diagnostic = policy.exact_gather.diagnostics(full, waveform, probe["receiver_id"], original)
    fixed = SimpleNamespace(diagnostics=lambda *args: diagnostic)
    return ORIGINAL_PROBE(probe, waveform, full, SimpleNamespace(amend=policy.amend, refiner=fixed), center)


class GuardedDetector(exact.RefinedShortDetector):
    def __init__(self, short_binary, short_sha256, *, full_coverage, policy, paths):
        super().__init__(short_binary, short_sha256, full_coverage=full_coverage, policy=policy)
        self.paths = paths
        self.phase = {}
        self.policy.exact_gather = refiner(policy.refiner, paths["exact-gather.so"], "short_cfo_gather")
        self.policy.refiner = refiner(policy.refiner, paths["tail.so"], "short_cfo_reanchored")
        self.policy.band_retries = 0
        self.take_tail = self.policy.refiner.library.anchored_take_tail_retries
        self.take_tail.argtypes, self.take_tail.restype = (), ct.c_uint64
        self.tail_retries = 0

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        def open_guarded(path, asset, mode):
            expected = binary if mode == "full" else self.short_binary
            if mode not in ("full", "short_primary") or Path(path).resolve() != Path(expected).resolve():
                raise ValueError("The guarded receiver tried to replace an unreviewed native path")
            counts = self.phase.setdefault((edge, mode), Counter())
            return GuardedPath(self.paths["full.so" if mode == "full" else "short.so"], asset, mode, counts)

        with ExitStack() as stack:
            # Only the two native opens are substituted. The existing lazy
            # tail workspace and asynchronous member source use their own ports.
            with patch.object(mixed, "NativePath", open_guarded):
                receive = stack.enter_context(super().detector(method, edge, binary=binary, pilot=pilot))
            yield receive

    def receipt(self):
        self.tail_retries += self.take_tail()
        return super().receipt() | {"anchored_phase": dict(
            lane_calls=[dict(edge=edge, mode=mode, **count) for (edge, mode), count in sorted(self.phase.items())],
            tail_exact_fallback=self.tail_retries, tail_signed_band_fallback=self.policy.band_retries)}


def recipe(original, parent):
    return ORIGINAL_RECIPE(original, parent) | {"guarded_phase": specification() | {
        "entry_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}}


def run_cli(pack, argv):
    paths = verified_pack(pack)
    with (patch.object(exact, "RefinedShortDetector", partial(GuardedDetector, paths=paths)),
          patch.object(exact, "refined_probe", guarded_probe), patch.object(exact, "recipe", recipe)):
        exact.run_cli(paths["original-cfo.so"], argv)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    action = cli.add_mutually_exclusive_group(required=True)
    action.add_argument("--anchored-cfo-pack", type=Path)
    action.add_argument("--assemble-pack", type=Path)
    cli.add_argument("--phase-build-root", type=Path, default=Path("/dev/shm/leo-anchored-phase-results02"))
    cli.add_argument("--exact-gather", type=Path, default=Path("/dev/shm/leo-short-cfo-exact-cost-results02/build/tail.so"))
    cli.add_argument("--exact-cfo", type=Path, default=Path("/dev/shm/leo-v3-short-cfo-held01/build/tail.so"))
    args, inherited = cli.parse_known_args()
    if args.assemble_pack:
        if inherited:
            cli.error("assembly accepts only library source options")
        assemble(args.assemble_pack, args.phase_build_root, args.exact_gather, args.exact_cfo)
    else:
        run_cli(args.anchored_cfo_pack, inherited)
