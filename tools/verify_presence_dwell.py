"""Check complete native dwell replay identity, numerical output and timing."""

from __future__ import annotations

import math

import numpy as np

from tools.qualify_presence_worker import compare_values


def validate_screens(row):
    screens = row["screen_diagnostics"]
    mask, selected = screens["available_mask"], screens["selected"]
    if (
        type(mask) is not int
        or mask not in (1, 2, 3)
        or type(selected) is not int
        or selected not in (0, 1)
        or not mask & (1 << selected)
        or len(screens["contrast"]) != 2
        or any(
            len(screens[name]) != 2 or any(len(x) != 6 for x in screens[name])
            for name in ("scores", "order", "epochs")
        )
    ):
        raise ValueError("invalid screen inventory")
    for index in range(2):
        scores, order, epochs = (screens[name][index] for name in ("scores", "order", "epochs"))
        contrast = screens["contrast"][index]
        if any(
            type(x) not in (int, float) or not math.isfinite(x) or x < 0
            for x in (*scores, contrast)
        ) or any(type(x) is not int for x in (*order, *epochs)):
            raise ValueError("invalid screen values")
        if not mask & (1 << index):
            if any((*scores, *order, *epochs, contrast)):
                raise ValueError("unavailable screen has evidence")
            continue
        if (
            order != sorted(range(6), key=lambda i: -scores[i])
            or any(not 0 <= x < round(row["rate_hz"] / 750) for x in epochs)
            or not math.isclose(
                contrast,
                scores[order[0]] / max(scores[order[1]], 1e-30),
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("invalid screen order or contrast")
    if mask == 3 and selected != int(screens["contrast"][1] > screens["contrast"][0]):
        raise ValueError("hybrid screen selection changed")
    for rank_name, screen_name in (
        ("scores", "scores"),
        ("order", "order"),
        ("projected_epoch_samples", "epochs"),
    ):
        if row["rank"][rank_name] != screens[screen_name][selected]:
            raise ValueError("selected screen does not supply the confirmation rank")


def key(row, *, multires=False):
    rate, counter = row["rate_hz"], row["counter"]
    if (
        type(rate) is not int
        or rate not in (2500000, 5000000)
        or type(row["edge"]) is not int
        or row["edge"] not in (0, 1)
        or type(counter) is not str
        or not counter.isdecimal()
        or counter != str(int(counter))
        or not 0 <= int(counter) <= 2**64 - 1 - rate // 50 * 6
        or type(row["bins"]) is not int
        or row["bins"] != (512 if multires else (2048 if rate == 2500000 else 4096))
        or row.get("timing_bins", 0) != ((2048 if rate == 2500000 else 4096) if multires else 0)
        or row["mode"] not in ("blind", "seeded")
        or type(row["iteration"]) is not int
        or not 0 <= row["iteration"] < 3
    ):
        raise ValueError("invalid whole-dwell replay identity")
    rank = row["rank"]
    if (
        type(row["confirmation_count"]) is not int
        or row["confirmation_count"] != 6
        or type(row["confirmation_window_mask"]) is not int
        or row["confirmation_window_mask"] != 63
        or len(rank["scores"]) != 6
        or len(rank["order"]) != 6
        or len(rank["projected_epoch_samples"]) != 6
        or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in rank["scores"])
        or any(type(x) is not int for x in rank["order"])
        or rank["order"] != sorted(range(6), key=lambda i: -rank["scores"][i])
        or any(
            type(x) is not int or not 0 <= x < round(rate / 750)
            for x in rank["projected_epoch_samples"]
        )
        or any(
            len(row[name]) != 6
            for name in ("confirmations", "nuisances", "prefix_cpu_ms", "prefix_wall_ms")
        )
    ):
        raise ValueError("invalid confirmation inventory or ranking")
    times = [row["total_cpu_ms"], row["total_wall_ms"], rank["total_cpu_ms"], rank["total_wall_ms"]]
    for name in ("prefix_cpu_ms", "prefix_wall_ms"):
        times.extend(row[name])
        if row[name] != sorted(row[name]):
            raise ValueError("prefix timing is reversed")
    for c in row["confirmations"]:
        if (
            type(c["candidate_count"]) is not int
            or not 0 <= c["candidate_count"] <= 2
            or c["candidate_count"] != len(c["candidates"])
        ):
            raise ValueError("candidate count mismatch")
        times.extend((c["total_cpu_ms"], c["total_wall_ms"]))
        stages = ("conversion_cpu_ms", "coarse_cpu_ms", "fine_cpu_ms", "fractional_cpu_ms")
        if any(name in c for name in stages):
            if not all(name in c for name in stages):
                raise ValueError("incomplete confirmation stage timing")
            values = [c[name] for name in stages]
            if any(
                type(x) not in (int, float) or not math.isfinite(x) or x < 0
                for x in (*values, c["total_cpu_ms"])
            ):
                raise ValueError("invalid confirmation stage timing")
            times.extend(values)
            if sum(values) > c["total_cpu_ms"] + 0.001:
                raise ValueError("confirmation stages exceed total CPU")
    if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in times):
        raise ValueError("invalid timing")
    for suffix in ("cpu_ms", "wall_ms"):
        if row[f"total_{suffix}"] + 0.001 < row[f"prefix_{suffix}"][-1]:
            raise ValueError("prefix exceeds total timing")
        if (
            row[f"prefix_{suffix}"][0] + 0.001
            < rank[f"total_{suffix}"] + row["confirmations"][0][f"total_{suffix}"]
        ):
            raise ValueError("first prefix omits screen or confirmation")
    if multires:
        if len(row["timing_proposals"]) != 6:
            raise ValueError("missing high-resolution timing inventory")
        for proposal in row["timing_proposals"]:
            if type(proposal["epoch"]) is not int or not 0 <= proposal["epoch"] < round(rate / 750):
                raise ValueError("invalid high-resolution epoch")
            if any(
                type(proposal[name]) not in (int, float)
                or not math.isfinite(proposal[name])
                or proposal[name] < 0
                for name in ("score", "total_cpu_ms", "total_wall_ms")
            ):
                raise ValueError("invalid high-resolution timing result")
        for suffix in ("cpu_ms", "wall_ms"):
            subtotal = (
                rank[f"total_{suffix}"]
                + row["timing_proposals"][0][f"total_{suffix}"]
                + row["confirmations"][0][f"total_{suffix}"]
            )
            if row[f"prefix_{suffix}"][0] + 0.001 < subtotal:
                raise ValueError("first prefix omits high-resolution timing")
    if "screen_diagnostics" in row:
        validate_screens(row)
    return rate, row["edge"], counter, row["bins"], row["mode"], row["iteration"]


def verify(
    desktop, arm, specifications, *, multires=False, require_screens=False, fft_version=None
):
    identities = {(r["rate_hz"], int(r["edge"] == "upper"), r["counter"]) for r in specifications}
    if not identities or len(identities) != len(specifications):
        raise ValueError("unique source inventory required")
    expected = {
        (
            *identity,
            512 if multires else (2048 if identity[0] == 2500000 else 4096),
            mode,
            iteration,
        )
        for identity in identities
        for mode in ("blind", "seeded")
        for iteration in range(3)
    }
    indexed = []
    for records in (desktop, arm):
        if require_screens and any("screen_diagnostics" not in r for r in records):
            raise ValueError("missing required screen diagnostics")
        if fft_version is not None and any(
            type(r.get("fft_backend")) is not str
            or not (
                r["fft_backend"] == fft_version or r["fft_backend"].startswith(fft_version + "-")
            )
            for r in records
        ):
            raise ValueError("FFT runtime identity mismatch")
        pairs = [(key(r, multires=multires), r) for r in records]
        mapping = dict(pairs)
        if len(mapping) != len(records) or set(mapping) != expected:
            raise ValueError("missing, duplicate or unexpected whole-dwell replay")
        indexed.append(mapping)
    for identity, actual in indexed[1].items():
        reference = indexed[0][identity]
        if "screen_diagnostics" in actual and "screen_diagnostics" in reference:
            a, b = actual["screen_diagnostics"], reference["screen_diagnostics"]
            if any(
                a[name] != b[name] for name in ("available_mask", "selected", "order", "epochs")
            ) or any(
                not np.allclose(a[name], b[name], rtol=2e-6, atol=2e-7)
                for name in ("scores", "contrast")
            ):
                raise ValueError("ARM screen diagnostics differ from desktop")
        if (
            actual["rank"]["order"] != reference["rank"]["order"]
            or actual["rank"]["projected_epoch_samples"]
            != reference["rank"]["projected_epoch_samples"]
            or not np.allclose(
                actual["rank"]["scores"], reference["rank"]["scores"], rtol=2e-6, atol=2e-7
            )
        ):
            raise ValueError("ARM ranking differs from desktop")
        for a, b in zip(actual["confirmations"], reference["confirmations"], strict=True):
            if a["candidate_count"] != b["candidate_count"]:
                raise ValueError("ARM candidate count differs")
            for x, y in zip(a["candidates"], b["candidates"], strict=True):
                compare_values(x, y)
        for a, b in zip(actual["nuisances"], reference["nuisances"], strict=True):
            compare_values(a, b, nuisance=True)
        if multires:
            for a, b in zip(actual["timing_proposals"], reference["timing_proposals"], strict=True):
                if a["epoch"] != b["epoch"] or not math.isclose(
                    a["score"], b["score"], rel_tol=2e-6, abs_tol=2e-7
                ):
                    raise ValueError("ARM high-resolution timing differs")
    statistics = {}
    for rate, mode in sorted({(r["rate_hz"], r["mode"]) for r in arm}):
        subset = [r for r in arm if (r["rate_hz"], r["mode"]) == (rate, mode)]
        statistics[f"{rate}:{mode}"] = {
            "executions": len(subset),
            "prefixes": {
                str(k): {
                    name: {
                        "mean": float(np.mean([r[name][k - 1] for r in subset])),
                        **dict(
                            zip(
                                ("p50", "p99", "max"),
                                np.percentile(
                                    [r[name][k - 1] for r in subset], [50, 99, 100]
                                ).tolist(),
                                strict=True,
                            )
                        ),
                    }
                    for name in ("prefix_cpu_ms", "prefix_wall_ms")
                }
                for k in (1, 2, 3, 6)
            },
        }
    return {
        "multires": multires,
        "required_screen_diagnostics": require_screens,
        "required_fft_version": fft_version,
        "verified_dwell_executions": len(expected),
        "verified_confirmation_windows": len(expected) * 6,
        "statistics": statistics,
    }
