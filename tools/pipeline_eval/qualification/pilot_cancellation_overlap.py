"""Measure both fixed candidates in common held raw sample blocks."""

import argparse
from pathlib import Path

import numpy as np

from .. import whole_iq
from ..__main__ import local_output
from ..variants import pilot_cancellation as pilot
from . import pilot_cancellation_results as results
from . import pilot_cancellation_trial as trial
from .full_v5_check import _load_case
from .original_kernel_trial import decode

BLOCK = 25_000
CONTRAST = 4.0


def wave(edge, choice, rolled=False):
    values = np.zeros(pilot.SAMPLES - pilot.SPLIT, dtype=np.complex64)
    starts = choice.epoch + pilot.FRAME_OFFSETS
    reference = pilot.waves(edge, choice.third, 1, rolled)
    for start, residue in zip(starts, pilot.FRAME_NUMBERS % 3, strict=True):
        lo, hi = max(start, pilot.SPLIT), min(start + pilot.FRAME, pilot.SAMPLES)
        if lo < hi:
            values[lo - pilot.SPLIT : hi - pilot.SPLIT] = reference[
                residue, lo - start : hi - start
            ] * np.exp(2j * np.pi * choice.cfo_hz * np.arange(lo, hi) / pilot.RATE)
    return values.reshape(-1, BLOCK)


def partial_power(raw, target, nuisance):
    nuisance_energy = np.sum(abs(nuisance) ** 2, axis=-1)
    overlap = np.sum(nuisance.conj() * target, axis=-1) / np.maximum(nuisance_energy, 1)
    independent = target - overlap[:, None] * nuisance
    power = abs(np.sum(independent.conj() * raw, axis=-1)) ** 2
    return power / np.maximum(np.sum(abs(independent) ** 2, axis=-1), 1)


def check(raw, edge, first, second):
    actual = raw[pilot.SPLIT :].reshape(-1, BLOCK)
    a, b = wave(edge, first), wave(edge, second)
    c, d = wave(edge, first, rolled=True), wave(edge, second, rolled=True)
    gram = abs(np.sum(a.conj() * b, axis=-1)) / np.sqrt(
        np.sum(abs(a) ** 2, axis=-1) * np.sum(abs(b) ** 2, axis=-1)
    )
    energy = np.maximum(np.mean(abs(actual) ** 2, axis=-1), 1)
    contrast_a = (partial_power(actual, a, b) - partial_power(actual, c, b)) / energy
    contrast_b = (partial_power(actual, b, a) - partial_power(actual, d, a)) / energy
    concurrent = (gram < 0.5) & (contrast_a > CONTRAST) & (contrast_b > CONTRAST)
    return dict(
        gram=gram.tolist(),
        first_contrast=contrast_a.tolist(),
        second_contrast=contrast_b.tolist(),
        simultaneous=concurrent.tolist(),
        supported=bool(np.count_nonzero(concurrent) >= 2),
    )


def fitted(row):
    return pilot.Pilot(
        row["epoch"],
        row["third"],
        row["cfo_hz"],
        row["center_rank"],
        row["power"],
        complex(*row["amplitude"]),
    )


def archived(row):
    phase, cfo = trial.location(row)
    rounded = round(3 * phase) / 3
    epoch = round(rounded)
    shifts = round(3 * (rounded - epoch))
    return pilot.Pilot(epoch, shifts, cfo, row["candidate_rank"], 0, 0j)


def publish(folder):
    seal = whole_iq.read(folder / "prediction-lock.json")
    for filename, digest in seal["files"].items():
        whole_iq.checked(folder / filename, digest)
    plan = whole_iq.read(folder / "input-lock.json")
    receipts = []
    for ident in plan["cases"]:
        case = _load_case(ident)
        document = trial.read_receipt(folder / f"{ident}-predictions.json.gz")
        for row in document["rows"]:
            if "failure" in row or row["original"]["public"]["status"] != "processed":
                continue
            modes = row["modes"] | {mode: row["controls"][mode] for mode in results.TRANSFER[1:-1]}
            offers = []
            for rx, probe in enumerate(row["original"]["probes"]):
                controls = results.archive_ranks(probe)
                primary = modes["primary"]["lanes"][rx]["primary"]
                if primary and controls and results.match(primary, controls[0]) != "literal":
                    first, second = fitted(primary), archived(controls[0])
                    if not pilot.comparable(first, second):
                        matched = results.choice(primary, controls)["state"] == "literal"
                        offers.append((rx, "missed_winner", first, second, matched))
                if row["cohort"] == "targeted" and controls:
                    first = archived(controls[0])
                    other = next(
                        (
                            second
                            for ref in controls[1:]
                            if not pilot.comparable(first, second := archived(ref))
                        ),
                        None,
                    )
                    if other is not None:
                        offers.append((rx, "original", first, other, True))
                for mode, values in modes.items():
                    branch = values["lanes"][rx]
                    if branch["primary"] and branch["secondary"]:
                        first, second = (fitted(branch[key]) for key in ("primary", "secondary"))
                        matches = all(
                            results.choice(branch[k], controls)["state"] == "literal"
                            for k in ("primary", "secondary")
                        )
                        offers.append((rx, mode, first, second, matches))
            if not offers:
                continue
            _, manifest, window = decode(case, row["visit"])
            if (manifest, window.iq_sha256) != (row["manifest_sha256"], row["iq_sha256"]):
                raise ValueError("overlap check reopened a different waveform")
            samples = pilot.lane_values(window.samples)
            for rx, mode, first, second, matches in offers:
                measurement = check(samples[rx], window.target["edge"], first, second)
                receipts.append(
                    dict(
                        case=ident,
                        visit=row["visit"],
                        cohort=row["cohort"],
                        stratum=row["stratum"],
                        rx=rx,
                        mode=mode,
                        iq_sha256=row["iq_sha256"],
                        matched_original=matches,
                        first=trial.pilot_payload(first),
                        second=trial.pilot_payload(second),
                        **measurement,
                    )
                )
    for edge in ("lower", "upper"):
        samples, (first, second) = trial.planted(edge, "two_pilots")
        raw = pilot.lane_values(samples)[0]
        receipts.append(
            dict(
                case="injection", stratum=edge, mode="two_pilots", **check(raw, edge, first, second)
            )
        )
        solo, _ = trial.planted(edge, "one_pilot")
        receipts.append(
            dict(
                case="injection",
                stratum=edge,
                mode="one_pilot",
                **check(pilot.lane_values(solo)[0], edge, first, second),
            )
        )
        sequential = raw.copy()
        separate = pilot.render(edge, second)
        sequential[pilot.SPLIT : pilot.SPLIT + 2 * BLOCK] -= separate[
            pilot.SPLIT : pilot.SPLIT + 2 * BLOCK
        ]
        left = pilot.render(edge, first)
        sequential[pilot.SPLIT + 2 * BLOCK :] -= left[pilot.SPLIT + 2 * BLOCK :]
        receipts.append(
            dict(
                case="injection",
                stratum=edge,
                mode="sequential",
                **check(sequential, edge, first, second),
            )
        )
    trial.save_receipt(folder / "overlap.json.gz", receipts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, nargs="?", default=trial.REPORT)
    args = parser.parse_args()
    publish(local_output(args.folder))
