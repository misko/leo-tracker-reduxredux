"""Measure candidate slates and true plant/CFO behavior for the fixed strided scout."""

import argparse
import gzip
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, write
from ..variants import scout_stride
from . import scout_budget_eval, scout_radius_eval, scout_stride_build, wide_regional_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import PRODUCERS, _sha
from .pilot_kernel_eval import _digest

REPORT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/cfo-stride"
SCHEDULE = tuple((s, (8, 15, 22, 27)) for s in (3, 6, 10))
MODES = ("control", "stride")
RATE = 10_000_000


def release(work):
    data = json.loads((work / "release.json").read_bytes())
    if any(_sha(Path(data["paths"][m])) != data["library_sha256"][m] for m in MODES):
        raise ValueError("Release artifacts differ from their measured digests")
    if data["library_sha256"]["control"] != scout_stride_build.PIN:
        raise ValueError("Off artifact is not the bit-exact full CFO bank")
    return data


def sources():
    paths = (
        Path(__file__),
        Path(scout_stride.__file__),
        scout_stride.HEADER,
        Path(scout_stride_build.__file__),
        Path(scout_budget_eval.__file__),
        Path(scout_radius_eval.__file__),
        REPORT / "PROTOCOL.md",
        scout_budget_eval.REPORT / "prediction-lock.json",
    )
    return {p.name: _sha(p) for p in paths}


def held(ident, work, bank, dev):
    archive_audit = scout_budget_eval.archive_audit
    original_centers = scout_budget_eval.centers_for
    probe = scout_radius_eval.probe()

    def four_centers(*args):
        return [row[:4] for row in original_centers(*args)]

    def audit(case, observed, windows):
        paired = []
        for r in observed:
            if r["status"] != "processed":
                paired.append(r)
                continue
            votes = dict(control=r["payloads"]["control"], scout16=r["payloads"]["stride"])
            paired.append(dict(r, payloads=votes))
        src = archive_audit(case, paired, windows)
        for r in src["receivers"]:
            for key in ("scout_coverage", "native_fit"):
                r[key]["stride"] = r[key].pop("scout16")
        return src

    with patch.multiple(
        scout_budget_eval,
        MODES=MODES,
        SCHEDULE=SCHEDULE,
        make_probe=lambda _work: probe,
        centers_for=four_centers,
        archive_audit=audit,
    ):
        return scout_budget_eval.held(ident, work, bank, dev)


def controls(bank):
    results = {}
    with patch.object(scout_budget_eval, "MODES", MODES):
        for edge, sign in (("lower", 1), ("upper", -1)):
            original = wide_regional_eval.synthetic(RATE, edge)
            one = {
                name: ((735, sign * f, a),)
                for name, f, a in (
                    ("odd", 720_000, 640),
                    ("even", 640_000, 640),
                    ("edge", 799_875, 640),
                    ("faint-odd", 400_000, 128),
                    ("faint-between", 479_875, 128),
                )
            }
            two = {
                "same-epoch-160khz": ((735, sign * 719_750, 480), (735, sign * 559_750, 184)),
                "symbol-alias": (
                    (735, sign * 689_250, 480),
                    (2267, sign * (689_250 - 1 / 4.4e-6), 184),
                ),
            }
            with ExitStack() as stack:
                call, _ = scout_budget_eval.native_call(stack, bank, edge)
                for i, (name, plants) in enumerate(
                    {**one, **two, "noise": (), "empty": ()}.items()
                ):
                    iq = (
                        np.zeros_like(original.samples)
                        if name == "empty"
                        else _test_signal(original, plants, 59491 + i).samples
                    )
                    vote = scout_budget_eval.timed(iq, call, i, 1)
                    results[f"{edge}-{name}"] = dict(
                        vote, planted=plants, iq_sha256=_digest(iq.tobytes())
                    )
    return dict(release=bank, results=results)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=scout_stride_build.ROOT)
    p.add_argument("--case", choices=PRODUCERS)
    p.add_argument("--dev", action="store_true")
    a = p.parse_args()
    frozen = sources()
    if json.loads((REPORT / "source-lock.json").read_bytes()) != frozen:
        raise ValueError("CFO stride qualification differs from its pre-scoring lock")
    bank = release(a.work)
    if a.case:
        data = held(a.case, a.work, bank, a.dev)
        name = f"{a.case}-{'dev' if a.dev else 'held'}.json.gz"
    else:
        data = controls(bank)
        name = "smoke.json.gz"
    if sources() != frozen:
        raise ValueError("Source changed during physical CFO stride measurement")
    write(REPORT / name, gzip.compress(encoded(data), mtime=0))
