"""Build a source-bound research binary and prepare a small saved-IQ ARM workload."""

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.storage.persistent_hop import PersistentHopIqStore
from tools.investigate_adaptive_decision_budget import decimate_window, taps_for
from tools.native_presence import NATIVE, ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(
    output: Path,
    compiler: str = "cc",
    fftw_prefix: Path | None = None,
    shared: bool = False,
    sanitize: bool = False,
):
    flags = json.loads((ROOT / "runtime/scanner-glrt/algorithm.json").read_text())["native_defines"]
    sources = [NATIVE / f for f in ("presence.c", "fft.c", "progressive_decision.c")]
    if not shared:
        sources += [ROOT / "tools/progressive_decision_replay.c"]
    dependencies = [
        *NATIVE.glob("*.[ch]"),
        ROOT / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        ROOT / "tools/progressive_decision_replay.c",
        Path(__file__),
    ]
    command = [
        compiler,
        "-std=c11",
        "-O3",
        "-fno-math-errno",
        "-Wall",
        "-Wextra",
        "-Werror",
        *flags,
    ]
    if fftw_prefix:
        command += [
            "-mcpu=cortex-a9",
            "-mfpu=neon",
            "-mfloat-abi=hard",
            "-DLEO_PRESENCE_FFTW=1",
            f"-I{fftw_prefix / 'include'}",
        ]
        dependencies += [fftw_prefix / "include/fftw3.h", fftw_prefix / "lib/libfftw3.so"]
    if shared:
        command += ["-shared", "-fPIC"]
    if sanitize:
        command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    before = {str(p): sha(p) for p in dependencies}
    command += [str(p) for p in sources]
    if fftw_prefix:
        command += [f"-L{fftw_prefix / 'lib'}", "-lfftw3"]
    command += ["-lm", "-o", str(output)]
    if output.exists():
        raise FileExistsError(output)
    subprocess.run(command, check=True)
    assert before == {str(p): sha(p) for p in dependencies}
    receipt = dict(command=command, sources_sha256=before, binary_sha256=sha(output))
    output.with_suffix(output.suffix + ".build.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    return output


def select(rows: list[dict]) -> list[dict]:
    selected = []
    for receiver in (0, 1):
        for edge in ("lower", "upper"):
            for positive in (False, True):
                matches = [
                    r
                    for r in rows
                    if r["rate_hz"] == 5_000_000
                    and r["receiver"] == receiver
                    and r["edge"] == edge
                    and r["decisions"]["all6"]["positive"] == positive
                ]
                if len(matches) < 2:
                    raise ValueError("workload lacks a required receiver/edge/decision stratum")
                selected += matches[:2]
    return selected


def prepare(output: Path, rows_path: Path, bulk: Path):
    selected = select([json.loads(line) for line in rows_path.read_text().splitlines()])
    store = PersistentHopIqStore.open_read_only(bulk)
    manifest = []
    with output.open("xb") as sink:
        sink.write(struct.pack("<4sIII", b"LPG1", 5_000_000, 6667, len(selected)))
        sink.write(taps_for(5_000_000).astype("<f4").tobytes())
        for edge in ("lower", "upper"):
            for roll in (0, 17):
                sink.write(
                    qin_edge_pilot_frame(5_000_000, edge, symbol_roll=roll).astype("<c16").tobytes()
                )
        for index, row in enumerate(selected):
            capture = store.inspect(row["session"])
            assert capture.manifest_sha256 == row["input_manifest_sha256"]
            reader = store.valid_ci16_reader(capture)
            iq = np.ascontiguousarray(
                reader.read_valid_ci16(row["visit"] * 1_200_000, 1_200_000)[:, 0]
            )
            assert hashlib.sha256(iq.tobytes()).hexdigest() == row["iq_sha256"]
            reference, _ = decimate_window(iq, 5_000_000, 0)
            sink.write(
                struct.pack(
                    "<IIII", index, row["receiver"], int(row["edge"] == "upper"), row["visit"]
                )
            )
            sink.write(iq.tobytes())
            sink.write(reference.tobytes())
            manifest.append(
                {k: row[k] for k in ("session", "visit", "receiver", "edge", "iq_sha256")}
                | {"case": index, "reference_positive": row["decisions"]["all6"]["positive"]}
            )
    output.with_suffix(".json").write_text(
        json.dumps(
            dict(
                schema="progressive-arm-replay-development-v1",
                cases=manifest,
                pack_sha256=sha(output),
                scope="16 development dwells balanced by RX/edge/reference decision; no RF",
            ),
            indent=2,
        )
        + "\n"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--rows", type=Path)
    p.add_argument("--compiler", default="cc")
    p.add_argument("--fftw-prefix", type=Path)
    p.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    p.add_argument("--sanitize", action="store_true")
    args = p.parse_args()
    args.output = args.output.resolve()
    if any(args.output.is_relative_to(Path(root)) for root in ("/mnt/qnap01", "/srv/bulk/leo")):
        p.error("research output must be separate from corpus storage")
    args.output.mkdir(parents=True, exist_ok=False)
    build(args.output / "replay", args.compiler, args.fftw_prefix, sanitize=args.sanitize)
    if args.rows:
        prepare(args.output / "workload.pack", args.rows, args.bulk_root)


if __name__ == "__main__":
    main()
