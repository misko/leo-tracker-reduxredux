from __future__ import annotations

import fnmatch
import json
import tomllib
from pathlib import Path

import pytest

from leo.qualification.arm_glrt_release import CLI, LIBRARY, build

ROOT = Path(__file__).resolve().parents[2]


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source"
    for relative in (
        "native_glrt.c",
        "native_glrt.h",
        "native_glrt_cli.c",
        "kernel/proposal_core_wrapper.c",
        "kernel/proposal_tracking_wrapper.c",
        "kernel/conditioned_czt_wrapper.c",
        "kernel/fft_full_wrapper.c",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"/* {relative} */\n")
    fftw = tmp_path / "fftw"
    (fftw / "include").mkdir(parents=True)
    (fftw / "lib").mkdir()
    (fftw / "include/fftw3.h").write_text("/* fixture */\n")
    (fftw / "lib/libfftw3f.a").write_bytes(b"fixture archive")
    (fftw / "lib/libfftw3.so").write_bytes(b"fixture shared library")
    compiler = tmp_path / "cc"
    compiler.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib,sys\n"
        "if '--version' in sys.argv: print('fixture cc 1.0'); raise SystemExit\n"
        "if '-print-file-name=libfftw3.so' in sys.argv:\n"
        " print(pathlib.Path(__file__).parent/'fftw/lib/libfftw3.so'); raise SystemExit\n"
        "p=pathlib.Path(sys.argv[sys.argv.index('-o')+1]);p.write_bytes(b'binary')\n"
    )
    compiler.chmod(0o755)
    archiver = tmp_path / "ar"
    archiver.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib,sys\n"
        "pathlib.Path(sys.argv[2]).write_bytes(b'archive')\n"
    )
    archiver.chmod(0o755)
    return source, fftw, compiler, archiver


def test_arm_build_records_sources_outputs_and_safe_flags(tmp_path: Path) -> None:
    source, fftw, compiler, archiver = _fixture(tmp_path)
    receipt_path = build(
        source_root=source,
        output_dir=tmp_path / "out",
        work_dir=tmp_path / "work",
        compiler=compiler,
        archiver=archiver,
        fftw_prefix=fftw,
        target="arm-cortex-a9",
    )
    receipt = json.loads(receipt_path.read_text())
    assert set(receipt["outputs"]) == {LIBRARY, CLI}
    assert receipt["compiler_version"] == "fixture cc 1.0"
    assert set(receipt["sources"]) >= {"native_glrt.c", "kernel/proposal_core_wrapper.c"}
    commands = [entry["argv"] for entry in receipt["commands"]]
    proposal = next(
        command for command in commands if "proposal_core_wrapper.c" in " ".join(command)
    )
    native = next(command for command in commands if command[-3].endswith("native_glrt.c"))
    assert "-fno-lto" in proposal
    assert "-fno-lto" not in native
    assert "-fno-fast-math" in native
    assert "-mcpu=cortex-a9" in native
    assert all("reports/" not in argument for command in commands for argument in command)


def test_pgo_use_fails_closed_without_collected_profiles(tmp_path: Path) -> None:
    source, fftw, compiler, archiver = _fixture(tmp_path)
    profile = tmp_path / "profiles"
    with pytest.raises(ValueError, match=r"collected \.gcda"):
        build(
            source_root=source,
            output_dir=tmp_path / "out",
            work_dir=tmp_path / "work",
            compiler=compiler,
            archiver=archiver,
            fftw_prefix=fftw,
            target="arm-cortex-a9",
            pgo="use",
            profile_dir=profile,
        )


def test_pgo_generate_and_use_keep_matching_object_paths(tmp_path: Path) -> None:
    source, fftw, compiler, archiver = _fixture(tmp_path)
    profile = tmp_path / "profiles"
    work = tmp_path / "stable-work"
    generated = build(
        source_root=source,
        output_dir=tmp_path / "generate",
        work_dir=work,
        compiler=compiler,
        archiver=archiver,
        fftw_prefix=fftw,
        target="arm-cortex-a9",
        pgo="generate",
        profile_dir=profile,
    )
    (profile / "native_glrt.gcda").write_bytes(b"profile")
    used = build(
        source_root=source,
        output_dir=tmp_path / "use",
        work_dir=work,
        compiler=compiler,
        archiver=archiver,
        fftw_prefix=fftw,
        target="arm-cortex-a9",
        pgo="use",
        profile_dir=profile,
    )
    generated_commands = json.loads(generated.read_text())["commands"]
    used_document = json.loads(used.read_text())
    used_commands = used_document["commands"]
    generated_objects = [a for c in generated_commands for a in c["argv"] if a.endswith(".o")]
    used_objects = [a for c in used_commands for a in c["argv"] if a.endswith(".o")]
    assert generated_objects == used_objects
    assert used_document["profiles"] == {
        "native_glrt.gcda": receipt_hash(profile / "native_glrt.gcda")
    }


def receipt_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wheel_package_data_covers_native_source_closure() -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())
    patterns = configuration["tool"]["setuptools"]["package-data"]["leo.analysis"]
    source = ROOT / "src/leo/analysis"
    native = source / "native_glrt"
    missing = [
        path.relative_to(source).as_posix()
        for path in native.rglob("*")
        if path.is_file()
        and not any(fnmatch.fnmatch(path.relative_to(source).as_posix(), pattern)
                    for pattern in patterns)
    ]
    assert missing == []
