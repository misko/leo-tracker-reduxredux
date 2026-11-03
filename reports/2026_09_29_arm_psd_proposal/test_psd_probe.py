import importlib.util
import json
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
ORACLE = Path("/var/tmp/leo-arm-full-search-oracle-allrates")
SPEC = importlib.util.spec_from_file_location("psd_proposal", HERE / "psd_proposal.py")
assert SPEC is not None and SPEC.loader is not None
PSD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PSD)


def _write_bank(path: Path, template: np.ndarray, rate: int) -> dict:
    bank = PSD.make_bank(template, rate)
    with path.open("wb") as stream:
        stream.write(struct.pack("<8sIId", b"PSD11V1\0", bank["nfft"], 11, rate))
        for key in ("cfo_bins_hz", "log_features", "sqrt_features"):
            np.asarray(bank[key], dtype="<f8", order="C").tofile(stream)
    return bank


@pytest.fixture(scope="module")
def probe(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("psd-probe-build") / "psd_probe"
    subprocess.run(
        ["cc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", str(HERE / "psd_probe.c"), "-lfftw3", "-lm", "-o", str(output)],
        check=True,
    )
    return output


def _templates() -> dict[int, Path]:
    if not (ORACLE / "oracle.json").exists():
        pytest.skip("all-rates oracle is not available")
    cases = json.loads((ORACLE / "oracle.json").read_text())["cases"]
    result = {}
    for case in cases:
        result.setdefault(case["context"]["rate_hz"], ORACLE / case["templates"]["exact"]["file"])
    return result


def _python_rows(raw: np.ndarray, bank: dict, rate: int) -> list[dict]:
    rows = []
    for window in range(11):
        for receiver in range(2):
            start = window * (rate // 100)
            block = raw[start : start + rate // 50, receiver]
            iq = block[:, 0].astype(float) + 1j * block[:, 1]
            rows.append(PSD.propose(iq, bank))
    return rows


@pytest.mark.parametrize("zero", [False, True])
def test_c_matches_python_for_actual_banks_at_all_rates(probe: Path, tmp_path: Path, zero: bool) -> None:
    rng = np.random.default_rng(9911)
    for rate, template_path in _templates().items():
        template = PSD.load_complex128(template_path)
        bank_path = tmp_path / f"{rate}.bank"
        bank = _write_bank(bank_path, template, rate)
        shape = (rate * 120 // 1000, 2, 2)
        raw = np.zeros(shape, dtype="<i2") if zero else rng.integers(-12000, 12001, size=shape, dtype=np.int16)
        raw_path = tmp_path / f"{rate}-{'zero' if zero else 'noise'}.ci16"
        raw.tofile(raw_path)
        completed = subprocess.run([str(probe), str(rate), str(bank_path), str(raw_path)], check=True, text=True, capture_output=True)
        actual = [json.loads(line) for line in completed.stdout.splitlines()]
        expected = _python_rows(raw, bank, rate)
        assert len(actual) == len(expected) == 22
        for got, want in zip(actual, expected, strict=True):
            assert got["ranking"] == want["ranking"]
            assert got["sqrt_ranking"] == want["sqrt_ranking"]
            assert np.isfinite(got["cpu_ms"]) and got["cpu_ms"] >= 0.0
            if zero:
                assert got["confidence"] == 0.0
                assert got["scores"] == [0.0] * 11


def test_rejects_bad_bank(probe: Path, tmp_path: Path) -> None:
    bad_bank = tmp_path / "bad.bank"
    bad_bank.write_bytes(b"not a PSD bank")
    raw = tmp_path / "empty.ci16"
    raw.write_bytes(b"")
    completed = subprocess.run([str(probe), "2500000", str(bad_bank), str(raw)])
    assert completed.returncode == 3
