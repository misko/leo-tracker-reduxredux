"""Pair radius-two capture testing with the authenticated four-center stage fixture."""

import argparse
import gzip
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, write
from ..variants import scout_radius
from . import scout_budget_build, scout_budget_eval, scout_budget_results, scout_radius_build
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import PRODUCERS, _from_native, _probe, _sha, compare_probes
from .pilot_kernel_eval import _digest
from .wide_regional_eval import synthetic

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support/scout-radius"
PARENT = scout_budget_eval.REPORT
MODES = ("control", "radius2")
RATE = scout_budget_eval.RATE
FRAME = scout_budget_eval.FRAME


def fixture(name):
    files = json.loads((PARENT / "prediction-lock.json").read_bytes())["files"]
    path = PARENT / name
    if _sha(path) != files[name]:
        raise ValueError("Scout fixture differs from its published seal")
    return scout_budget_results.unpack(path)


def sources():
    dependencies = (
        Path(__file__),
        Path(scout_radius.__file__),
        Path(scout_radius_build.__file__),
        Path(scout_budget_eval.__file__),
        REPORT / "PROTOCOL.md",
        PARENT / "prediction-lock.json",
    )
    return {p.name: _sha(p) for p in dependencies}


def release(work):
    receipt = json.loads((work / "release.json").read_bytes())
    if any(_sha(Path(receipt["paths"][m])) != receipt["library_sha256"][m] for m in MODES):
        raise ValueError("Released candidate or control changed")
    if receipt["library_sha256"]["control"] != scout_radius_build.PIN:
        raise ValueError("Off artifact does not match the pinned ±1 released native library")
    return receipt


def compare(case, rows, windows, prior):
    if prior["archive"]["native_archive_sha256"] != case["native"]["sha256"]:
        raise ValueError("Old source factors and new raw corpus have different authority")
    prior_rows = {r["visit"]: r for r in prior["rows"]}
    archive = {(r["visit"], r["receiver"]): r for r in prior["archive"]["receivers"]}
    results = []
    for row in rows:
        base = prior_rows[row["visit"]]
        if any(base[k] != row[k] for k in ("status", "reason", "iq_sha256", "iq_bytes")):
            raise ValueError("Fresh radius pair saw different held input")
        if row["status"] != "processed":
            continue
        if row["payload_sha256"]["control"] != base["payload_sha256"]["control"]:
            raise ValueError("Updated radius pair changed its canonical wide control")
        for j, rx in enumerate(windows[row["visit"]].receiver_ids):
            centers = row["centers"][j][:4]
            if centers != base["centers"][j][:4]:
                raise ValueError("The four original proposal centers changed")
            windows_rx = windows[row["visit"]]
            authority = archive[row["visit"], rx]
            covered, fits, slates = {}, {}, {}
            # The prior fixture sealed the authenticated archive-positive fields.
            capture = _probe(windows_rx, rx, authority["archive_candidates"])
            for mode, radius in zip(MODES, (1, 2), strict=True):
                scope = {
                    e
                    for c in centers
                    for e in range(max(0, c - radius), min(FRAME, c + radius + 1))
                }
                covered[mode] = sorted(scope)
                receiver = row["payloads"][mode]["rows"][j]
                candidates = receiver["candidates"]
                native = _probe(
                    windows_rx, rx, (_from_native(k, c) for k, c in enumerate(candidates))
                )
                fits[mode] = compare_probes(capture, native, RATE)
                slates[mode] = [(c["coarse_epoch"], c["coarse_cfo_hz"]) for c in candidates]
            identities = []
            for c in capture["candidates"]:
                rank, epoch = c["candidate_rank"], c["integer_epoch_sample"]
                identities.append(
                    dict(
                        archived=c,
                        eligibility={m: epoch in covered[m] for m in MODES},
                        final_matches={
                            m: [
                                o
                                for o in fits[m]["positive_matches"]
                                if o["production_rank"] == rank
                            ]
                            for m in MODES
                        },
                    )
                )
            results.append(
                dict(
                    visit=row["visit"],
                    receiver=rx,
                    centers=centers,
                    support=covered,
                    slates=slates,
                    baseline_fit=authority["native_fit"]["control"],
                    fits=fits,
                    archived_positives=identities,
                )
            )
    return dict(native_archive_sha256=case["native"]["sha256"], receivers=results)


def probe():
    executable = scout_budget_build.ROOT / "probe"
    if _sha(executable) != fixture("smoke.json.gz")["same_release_probe_sha256"]:
        raise ValueError("Scout prefix diagnostics differ from the prior exact inherited ranker")
    return executable


def held(case, work, bank):
    prior = fixture(f"{case}-held.json.gz")
    promotion = probe()
    with patch.multiple(
        scout_budget_eval,
        MODES=MODES,
        make_probe=lambda _work: promotion,
        archive_audit=lambda c, rows, windows: compare(c, rows, windows, prior),
    ):
        return scout_budget_eval.held(case, work, bank)


def smoke(work, bank):
    expected = fixture("smoke.json.gz")["results"]
    out = {}
    with patch.object(scout_budget_eval, "MODES", MODES):
        for edge in ("lower", "upper"):
            window = synthetic(RATE, edge)
            names = [
                f"{edge}-{name}"
                for name in ("signed-high", "weak", "very-weak", "two", "empty", "noise")
            ]
            with ExitStack() as stack:
                call, _ = scout_budget_eval.native_call(stack, bank, edge)
                for k, name in enumerate(names):
                    source = expected[name]
                    if k < 4:
                        iq = _test_signal(window, source["planted"], 82801 + k).samples
                    elif k == 4:
                        iq = np.zeros_like(window.samples)
                    else:
                        iq = _test_signal(window, (), 82805).samples
                    digest = _digest(iq.tobytes())
                    if digest != source["iq_sha256"]:
                        raise ValueError("Synthetic radius control did not regenerate exact IQ")
                    data = scout_budget_eval.timed(iq, call, k, 1)
                    if data["payload_sha256"]["control"] != source["payload_sha256"]["control"]:
                        raise ValueError("Synthetic off output changed from the previous release")
                    out[name] = dict(data, iq_sha256=digest, planted=source.get("planted", []))
    return dict(release=bank, results=out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=scout_radius_build.ROOT)
    p.add_argument("--case", choices=PRODUCERS)
    a = p.parse_args()
    frozen = sources()
    if json.loads((REPORT / "source-lock.json").read_bytes()) != frozen:
        raise ValueError("Prespecified radius science source changed")
    bank = release(a.work)
    result = held(a.case, a.work, bank) if a.case else smoke(a.work, bank)
    name = f"{a.case}-held.json.gz" if a.case else "smoke.json.gz"
    if frozen != sources():
        raise ValueError("Radius science source changed during measurement")
    write(REPORT / name, gzip.compress(encoded(result), mtime=0))
