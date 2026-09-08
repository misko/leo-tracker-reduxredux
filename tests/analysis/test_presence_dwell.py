import ctypes as ct
import json
import subprocess

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import (
    ROOT,
    Candidate,
    NativePresence,
    Result,
    build_dwell_presence,
    pointer,
    write_templates,
)
from tools.presence_dwell import DwellResult, NativeDwell, unpack
from tools.presence_window_rank import write_rank_probe


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    flags = tuple(protocol["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in protocol["variants"][0]["defines"].items()
    )
    return build_dwell_presence(
        tmp_path_factory.mktemp("dwell-presence") / "dwell.so", cflags=flags
    )


def signal(rate, edge, epoch=317, cfo=312345):
    rng = np.random.default_rng(713)
    values = 20 * (rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50))
    template = qin_edge_pilot_frame(rate, edge)
    for frame in range(15):
        start = epoch + round(frame * rate / 750)
        stop = min(start + len(template), len(values))
        if stop > start:
            values[start:stop] += (
                1000
                * template[: stop - start]
                * np.exp(2j * np.pi * cfo * np.arange(start, stop) / rate)
            )
    return np.rint(np.column_stack((values.real, values.imag))).astype(np.int16)


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("cfo", [-399999, -153271, 312345, 399999])
def test_seeded_confirmation_keeps_exact_blind_fractional_computation(library, rate, edge, cfo):
    iq = signal(rate, edge, cfo=cfo)
    before = iq.tobytes()
    with NativePresence(library, rate, edge) as native:
        blind = Result()
        assert (
            native.library.leo_presence_run_ci16(
                native.workspace, pointer(iq), len(iq), ct.byref(blind)
            )
            == 0
        )
        assert blind.candidate_count == 1
        candidate = blind.candidates[0]
        seeded = native.confirm(iq, candidate.epoch)
        for name, _ in Candidate._fields_:
            if name != "coarse_score":
                np.testing.assert_array_equal(
                    unpack(getattr(seeded.candidates[0], name)), unpack(getattr(candidate, name))
                )
        assert seeded.candidates[0].coarse_score == 0
        assert seeded.candidates[0].fractional_complete
        assert abs(seeded.candidates[0].tracking_cfo_hz - cfo) < 1500
        assert seeded.candidates[0].margin > 0.2
        assert native.profile()["local_coarse_cpu_ms"] == 0
    assert iq.tobytes() == before


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("window", [0, 3, 5])
@pytest.mark.parametrize("seeded", [False, True])
def test_whole_dwell_selects_signal_and_keeps_bounded_prefix_timings(library, rate, window, seeded):
    rng = np.random.default_rng(42)
    iq = rng.integers(-30, 31, (6 * rate // 50, 2), dtype=np.int16)
    iq[window * rate // 50 : (window + 1) * rate // 50] = signal(rate, "upper")
    before = iq.tobytes()
    with NativeDwell(library, rate, "upper", 4096 if rate == 2500000 else 8192) as native:
        result = native.run(iq, maximum=3, seeded=seeded)
        prefix = native.run(iq, maximum=1, seeded=seeded)
    assert result.rank.order[0] == window
    assert result.confirmation_count == 3
    assert result.confirmation_window_mask == sum(1 << k for k in result.rank.order[:3])
    assert result.confirmations[0].candidates[0].fractional_complete
    assert result.confirmations[0].candidates[0].margin > 0.2
    assert bytes(result.confirmations[0].candidates) == bytes(prefix.confirmations[0].candidates)
    assert sorted(result.prefix_cpu_ms[:3]) == list(result.prefix_cpu_ms[:3])
    assert (
        result.prefix_cpu_ms[0]
        >= result.rank.total_cpu_ms + result.confirmations[0].total_cpu_ms - 1e-5
    )
    assert result.total_cpu_ms >= result.prefix_cpu_ms[2]
    assert not any(result.prefix_cpu_ms[3:])
    assert not any(c.candidate_count for c in result.confirmations[3:])
    assert iq.tobytes() == before


def test_invalid_or_partial_dwell_never_mutates_output(library):
    iq = np.zeros((300000, 2), dtype=np.int16)
    with NativeDwell(library, 2500000, "lower", 2048) as native:
        out = DwellResult()
        ct.memset(ct.byref(out), 0x27, ct.sizeof(out))
        before = bytes(out)
        for count, maximum, seeded in (
            (50000, 1, 1),
            (299999, 1, 1),
            (300001, 1, 1),
            (300000, 0, 1),
            (300000, 7, 1),
            (300000, 1, 2),
        ):
            assert (
                native.library.leo_presence_dwell_run_ci16(
                    native.workspace, pointer(iq), count, maximum, seeded, ct.byref(out)
                )
                == -1
            )
            assert bytes(out) == before
        for maximum in (0, 7, True):
            with pytest.raises(ValueError):
                native.run(iq, maximum=maximum)
    with pytest.raises(ValueError, match="closed"):
        native.run(iq)


def test_bad_seed_is_unknown_and_both_apis_reject_invalid_geometry(library):
    iq = np.zeros((50000, 2), dtype=np.int16)
    with NativePresence(library, 2500000, "lower") as native:
        for epoch in (-1, 3333, 1.25, True):
            with pytest.raises(ValueError):
                native.confirm(iq, epoch)
        result = native.confirm(iq, 1)
        assert not any(c.fractional_complete for c in result.candidates)
        out = Result()
        ct.memset(ct.byref(out), 0x27, ct.sizeof(out))
        before = bytes(out)
        assert (
            native.library.leo_presence_confirm_ci16(
                native.workspace, pointer(iq), 50000, -1, ct.byref(out)
            )
            == -1
        )
        assert bytes(out) == before


def test_saved_iq_executable_checks_templates_and_preserves_counter(tmp_path):
    binary = build_dwell_presence(tmp_path / "replay", executable=True)
    packet, templates = tmp_path / "input.rank", tmp_path / "templates"
    counter = 10**16 + 37
    write_rank_probe(packet, np.zeros((300000, 2), dtype=np.int16), 2500000, "upper", counter)
    write_templates(templates, 2500000)
    command = [str(binary), str(packet), str(templates), "2048", "2", "seeded", "1"]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
    row = json.loads(result.stdout)
    assert row["counter"] == str(counter)
    assert row["confirmation_count"] == 2 and row["confirmation_window_mask"] == 3
    assert len(row["prefix_cpu_ms"]) == 2
    assert not any(c["fractional_complete"] for r in row["confirmations"] for c in r["candidates"])
    data = templates.read_bytes()
    templates.write_bytes(data[:-1])
    bad = subprocess.run(command, capture_output=True, timeout=10)
    assert bad.returncode == 2 and not bad.stdout


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_multires_uses_selected_window_high_resolution_seed(library, rate):
    # Isolate high-resolution dispatch from the 512-bin screen's known ranking
    # misses in noise. Historic quality is evaluated separately, not assumed.
    iq = np.zeros((6 * rate // 50, 2), dtype=np.int16)
    selected = 5
    samples = signal(rate, "upper")
    iq[selected * rate // 50 : (selected + 1) * rate // 50] = samples
    with NativeDwell(library, rate, "upper", 512, 4096 if rate == 2500000 else 8192) as native:
        result = native.run(iq, maximum=1)
        blind = native.run(iq, maximum=1, seeded=False)
    assert result.rank.order[0] == selected
    timing = result.timing_proposals[0]
    assert abs(timing.epoch - 317) <= 1
    assert result.confirmations[0].candidates[0].fractional_complete
    assert result.confirmations[0].candidates[0].margin > 0.2
    with NativePresence(library, rate, "upper") as confirmation:
        expected = confirmation.confirm(samples, timing.epoch)
    assert bytes(result.confirmations[0].candidates) == bytes(expected.candidates)
    assert (
        result.prefix_cpu_ms[0] + 1e-5
        >= result.rank.total_cpu_ms + timing.total_cpu_ms + result.confirmations[0].total_cpu_ms
    )
    assert not any(t.score or t.total_cpu_ms for t in blind.timing_proposals)
