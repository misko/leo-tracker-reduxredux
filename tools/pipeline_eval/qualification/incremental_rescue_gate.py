"""Bind native ordinary parity, lazy receiver gating and actual rescue to the release."""

import argparse
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import incremental_rescue as rescue
from ..variants import incremental_rescue_graft as graft
from ..variants.differential_runtime_fft import FftScout
from . import differential_pilot_eval, scout_stride_build
from . import incremental_rescue_build as build
from . import wide_kernel_eval as wide
from .full_v5_check import MARGIN_GATE, _from_native, _sha
from .pilot_kernel_eval import _digest
from .wide_regional_eval import RATE, templates

REPORT = ROOT / "reports/2026_11_19_receiver_screening/support-preserving/incremental-rescue"


def release(work):
    info = whole_iq.read(work / "release.json")
    for role, path in info["paths"].items():
        whole_iq.checked(Path(path), info["sha256"][role])
    if info["detector_entry"] != graft.ENTRY or info["stock_public_abi"] != 1:
        raise ValueError("wrong incremental ABI")
    return info["paths"], info


def attach(stack, paths, edge, roles=("stock", "detector")):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    pair = templates(RATE, edge)
    return {
        role: stack.enter_context(
            NativeShortWindow(paths[role], *pair, sample_rate_hz=RATE, fractional_epoch=True)
        )
        for role in roles
    }


def positive(row):
    return any(
        factor["passed_fractional_margin_gate"]
        for rank, value in enumerate(row["candidates"])
        if (factor := _from_native(rank, value)) is not None
    )


def check(stock, result, trace, called):
    expected = [rx for rx, row in enumerate(stock["rows"]) if not positive(row)]
    if expected != called:
        raise ValueError("scout activation differs from the ordinary fractional gate")
    for rx, (baseline, actual, detail) in enumerate(
        zip(stock["rows"], result["rows"], trace, strict=True)
    ):
        if detail["stock_positive"] != positive(baseline):
            raise ValueError("native stock gate differs from canonical GLRT projection")
        if not detail["donor_positive"] and encoded(baseline) != encoded(actual):
            raise ValueError("incremental fallback or positive stock row changed")
        if positive(actual) != (detail["stock_positive"] or detail["donor_positive"]):
            raise ValueError("accepted donor differs from the canonical GLRT projection")
        epochs = detail["evaluated_epochs"]
        stock_epochs = {
            a for c in detail["ordinary"] for a in range(max(0, c - 1), min(13_333, c + 2))
        }
        if detail["rx"] != rx or len(epochs) > 3 or stock_epochs.intersection(epochs):
            raise ValueError("donor tried more than one new disjoint native region")


def qualify(work):
    if MARGIN_GATE != 0.025:
        raise ValueError("canonical fractional gate changed")
    paths, info = release(work)
    rows = {}
    for ident, edge in zip(wide.PANEL, ("lower", "upper"), strict=True):
        raw = scout_stride_build.ROOT / f"{ident}-held/visit.ci16"
        actual = np.fromfile(raw, dtype="<i2").reshape(200000, 2, 2)
        frozen = next(
            r for r in wide.held_roster(ident) if r["iq_sha256"] == _digest(actual.tobytes())
        )
        with ExitStack() as stack:
            native = attach(stack, paths, edge)
            fftw = stack.enter_context(FftScout(paths["scout"], edge))
            single = stack.enter_context(rescue.SingleLaneScout(paths["scout"], edge))
            called = []

            def record(sample, band, rx, called=called, single=single):
                called.append(rx)
                return single(sample, band, rx)

            call = rescue.IncrementalRescueCall(native["detector"], edge, scout=record)
            samples = {
                "saved": actual,
                "zero": np.zeros_like(actual),
                "one-frame": differential_pilot_eval.synthetic(edge, "one-frame")[0],
            }
            for name, sample in samples.items():
                stock = native["stock"].analyze(sample)
                if encoded(stock) != encoded(native["detector"].analyze(sample)):
                    raise ValueError("ordinary ABI changed on the new release")
                if name == "saved" and _digest(encoded(stock)) != frozen["product_sha256"]:
                    raise ValueError("saved waveform disagrees with frozen wide payload")
                surfaces = fftw.surface(sample)
                if any(
                    single.one_surface(sample, i).tobytes() != expected.tobytes()
                    for i, expected in enumerate(surfaces)
                ):
                    raise ValueError("one-lane scout did not reproduce the two-lane surface")
                called.clear()
                output, proposals, trace, elapsed = call(sample)
                check(stock, output, trace, called)
                if name == "zero" and encoded(output) != encoded(stock):
                    raise ValueError("zero input changed native candidate fields")
                rows[f"{ident}:{name}"] = dict(
                    edge=edge,
                    visit=frozen["visit"] if name == "saved" else None,
                    iq_sha256=_digest(sample.tobytes()),
                    stock=_digest(encoded(stock)),
                    result=_digest(encoded(output)),
                    stock_positive=[positive(row) for row in stock["rows"]],
                    trace=trace,
                    elapsed_ns=elapsed,
                    proposals=proposals,
                )
    if not any(lane["donor_positive"] for row in rows.values() for lane in row["trace"]):
        raise ValueError("ABI witness set never exercised an accepted donor")
    save_json(REPORT / "abi-witness.json", rows)
    write(REPORT / "release.json", (work / "release.json").read_bytes())
    receipt = Path(paths["detector"]).with_name("build-receipt.json")
    write(REPORT / receipt.name, receipt.read_bytes())
    sources = (
        Path(__file__),
        Path(rescue.__file__),
        Path(graft.__file__),
        graft.HEADER,
        Path(build.__file__),
        wide.REPORT / "evidence-lock.json",
    )
    save_json(
        REPORT / "feature-gate.json",
        dict(
            passed=True,
            entry=graft.ENTRY,
            detector=dict(path=paths["detector"], sha256=info["sha256"]["detector"]),
            sidecar=dict(path=paths["scout"], sha256=info["sha256"]["scout"]),
            files={
                name: _sha(REPORT / name)
                for name in (
                    "PROTOCOL.md",
                    "abi-witness.json",
                    "release.json",
                    "build-receipt.json",
                )
            },
            sources={str(path.relative_to(ROOT)): _sha(path) for path in sources},
            stock_rows_preserved=True,
            null_stock_exact=True,
            one_lane_scout_surface_exact=True,
            positive_gate_verified=True,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, default=build.WORK)
    qualify(parser.parse_args().work)
