"""Offline FIT changes preserve all original software and configuration bytes."""

import importlib.util
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "repack_fpga_fit", Path(__file__).resolve().parents[2] / "tools/repack_fpga_fit.py"
)
pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pack)


def bit(payload=b"\xaa\x99\x55\x66" + b"\xff" * 100, part=b"7z010clg400\0"):
    result = bytes.fromhex("00090ff00ff00ff00ff0000001")
    for tag, value in (
        (b"a", b"unit-test\0"),
        (b"b", part),
        (b"c", b"2026/10/09\0"),
        (b"d", b"00:00:00\0"),
    ):
        result += tag + struct.pack(">H", len(value)) + value
    return result + b"e" + struct.pack(">I", len(payload)) + payload


@pytest.fixture
def fit(tmp_path):
    import hashlib

    original = bit()
    data = " ".join(f"{value:02x}" for value in original)
    digest = " ".join(f"{value:02x}" for value in hashlib.md5(original).digest())
    source = tmp_path / "image.dts"
    target = tmp_path / "image.itb"
    source.write_text(f"""/dts-v1/;
    / {{ description="fixture"; images {{
      fpga@1 {{ type="fpga"; compression="none"; data=[{data}];
        hash@1 {{ algo="md5"; value=[{digest}]; }};
      }};
      kernel@1 {{ type="kernel"; data=[00 01 02 03]; load=<0x8000>; }};
      ramdisk@1 {{ type="ramdisk"; data=[1f 8b 08 00]; }};
      fdt@3 {{ type="flat_dt"; data=[d0 0d fe ed]; }};
    }}; configurations {{ default="config@8"; config@8 {{
      kernel="kernel@1"; ramdisk="ramdisk@1"; fdt="fdt@3"; fpga="fpga@1";
    }}; }}; }};
    """)
    subprocess.run(
        ["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(target), str(source)], check=True
    )
    return target.read_bytes()


def test_only_fpga_data_and_hash_change(fit):
    replacement = bit(b"\xaa\x99\x55\x66" + b"\x01" * 300)
    output, manifest = pack.repack(fit + b"\xff" * 4096, replacement)
    before, after = pack.Fit(fit).nodes(), pack.Fit(output).nodes()
    assert after["/images/fpga@1"]["data"] == replacement
    for path in before.keys() - {"/images/fpga@1", "/images/fpga@1/hash@1"}:
        assert after[path] == before[path]
    assert manifest["hardware_qualified"] is False
    assert manifest["all_other_fit_properties_preserved"] is True
    image = pack.dfu(output)
    assert image[:-16] == output and image[-8:-5] == b"UFD"
    assert struct.unpack_from("<I", image, len(image) - 4)[0] == zlib.crc32(image[:-4]) ^ 0xFFFFFFFF


def test_part_mismatch_and_truncated_input_rejected(fit):
    with pytest.raises(ValueError, match="part differs"):
        pack.repack(fit, bit(part=b"7z020clg400\0"))
    with pytest.raises(ValueError):
        pack.repack(fit[:-1], bit())
    with pytest.raises(ValueError, match="Xilinx"):
        pack.repack(fit, b"\0" * 200)


def test_original_hash_damage_and_unsupported_algorithm_rejected(fit):
    tree = pack.Fit(fit)
    tree.replace("/images/fpga@1/hash@1", "value", b"\0" * 16)
    with pytest.raises(ValueError, match="hash mismatch"):
        pack.repack(tree.packed(), bit())
    tree = pack.Fit(fit)
    tree.replace("/images/fpga@1/hash@1", "algo", b"rsa2048\0")
    with pytest.raises(ValueError, match="unsupported"):
        pack.repack(tree.packed(), bit())


def test_signed_fit_rejected(fit, tmp_path):
    del fit  # Fixture creates the source DTS as well as the unsigned FIT.
    source = tmp_path / "image.dts"
    signed = tmp_path / "signed.itb"
    source.write_text(source.read_text().replace("hash@1", "signature@1"))
    subprocess.run(
        ["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(signed), str(source)],
        check=True,
    )
    with pytest.raises(ValueError, match="signed FIT"):
        pack.repack(signed.read_bytes(), bit())


def test_cli_writes_new_private_directory_only(fit, tmp_path):
    source, fpga, output = tmp_path / "source", tmp_path / "fpga", tmp_path / "new"
    source.write_bytes(fit)
    fpga.write_bytes(bit())
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[2] / "tools/repack_fpga_fit.py"),
        "--source-qspi",
        str(source),
        "--bitstream",
        str(fpga),
        "--out",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True)
    assert source.read_bytes() == fit
    assert (output / "firmware.dfu").stat().st_mode & 0o777 == 0o600
    assert subprocess.run(command, capture_output=True).returncode != 0
