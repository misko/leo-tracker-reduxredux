"""Check and bind native stock support before handing the opt-in union to whole IQ."""

import argparse
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import center_union, hinted_glrt
from ..variants.differential_runtime_fft import FftScout
from . import center_union_build, scout_stride_build, whole_fftw_trial
from . import wide_kernel_eval as wide
from .full_v5_check import _sha
from .pilot_kernel_eval import _digest
from .wide_regional_eval import RATE, templates

REPORT = ROOT / "reports/2026_11_19_receiver_screening/support-preserving/center-union"


def preserved(null, merged):
    for before, after in zip(null, merged, strict=True):
        if (
            before["ordinary"] != after["ordinary"]
            or before["stock_peak_keys"] != after["stock_peak_keys"]
            or before["stock_peaks"] != len(before["stock_peak_keys"])
            or before["active_epochs"] + after["added_epochs"] != after["active_epochs"]
            or not 0 <= after["added_epochs"] <= 3
        ):
            raise ValueError("fifth region lost an original native peak or stock epoch")


def release(work):
    build = whole_iq.read(work / "release.json")
    for role, name in build["paths"].items():
        whole_iq.checked(Path(name), build["library_sha256"][role])
    if build["optional_entry"] != center_union.ENTRY or build["stock_public_abi"] != 1:
        raise ValueError("center union build did not retain the stock ABI")
    assets = whole_fftw_trial.qualified()
    return {**build["paths"], **{key: val["path"] for key, val in assets.items()}}, build


def bind(stack, paths, edge):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    pair = templates(RATE, edge)
    return {
        name: stack.enter_context(
            NativeShortWindow(
                paths[name],
                *pair,
                sample_rate_hz=RATE,
                fractional_epoch=True,
            )
        )
        for name in ("stock", "hinted", "union")
    }


def qualify(work):
    paths, build = release(work)
    rows = {}
    for ident, edge in zip(wide.PANEL, ("lower", "upper"), strict=True):
        raw = scout_stride_build.ROOT / f"{ident}-held/visit.ci16"
        sample = np.fromfile(raw, dtype="<i2").reshape(200000, 2, 2)
        frozen = next(
            r for r in wide.held_roster(ident) if r["iq_sha256"] == _digest(sample.tobytes())
        )
        with ExitStack() as stack:
            native = bind(stack, paths, edge)
            fft = stack.enter_context(FftScout(paths["fftw"], edge))
            union = center_union.UnionCall(native["union"])
            replace = hinted_glrt.HintedCall(native["hinted"])
            expected = native["stock"].analyze(sample)
            stock, before = union(sample)
            hints = tuple(centers[0] if centers else None for centers, _ in fft(sample, edge))
            old, old_trace = replace(sample, hints)
            new, after = union(sample, hints)
            if _digest(encoded(expected)) != frozen["product_sha256"] or encoded(stock) != encoded(
                expected
            ):
                raise ValueError("null hint differs from authenticated stock payload")
            preserved(before, after)
            rows[ident] = dict(
                visit=frozen["visit"],
                iq_sha256=frozen["iq_sha256"],
                edge=edge,
                hints=hints,
                stock_payload_sha256=_digest(encoded(expected)),
                replace_payload_sha256=_digest(encoded(old)),
                union_payload_sha256=_digest(encoded(new)),
                stock=before,
                replacement=old_trace,
                union=after,
            )
    if not any(lane["added_epochs"] for item in rows.values() for lane in item["union"]):
        raise ValueError("both early real witnesses bypassed the fifth region")
    save_json(REPORT / "abi-witness.json", rows)
    write(REPORT / "release.json", (work / "release.json").read_bytes())
    receipt = Path(paths["union"]).with_name("build-receipt.json")
    write(REPORT / receipt.name, receipt.read_bytes())
    bound = ("PROTOCOL.md", "abi-witness.json", "release.json", "build-receipt.json")
    sources = (
        Path(__file__),
        Path(center_union.__file__),
        center_union.HEADER,
        Path(center_union_build.__file__),
        wide.REPORT / "evidence-lock.json",
        whole_fftw_trial.QUALIFIED / "prediction-lock.json",
    )
    save_json(
        REPORT / "feature-gate.json",
        dict(
            passed=True,
            entry=center_union.ENTRY,
            detector=dict(path=paths["union"], sha256=build["library_sha256"]["union"]),
            sidecar=dict(path=paths["fftw"], sha256=whole_fftw_trial.whole_fftw_raw.SCOUT_SHA256),
            files={name: _sha(REPORT / name) for name in bound},
            sources={str(p.relative_to(ROOT)): _sha(p) for p in sources},
            witnesses=list(rows),
            stock_peaks_preserved=True,
            null_stock_exact=True,
        ),
    )
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, default=center_union_build.WORK)
    qualify(parser.parse_args().work)
