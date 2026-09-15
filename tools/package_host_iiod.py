"""Package the static host-feedback ARM daemon and measured build provenance."""

import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/home/mouse9911/gits/libiio-adaptive-multirate")
BUILD = Path("/var/tmp/leo-host-multirate-provider")
NATIVE = Path("/var/tmp/leo-host-multirate-native")
SCANNER_ARCHIVE = Path("/var/tmp/leo-host-production-20260915/libscanner.a")
SDK = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host")


def command(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True, timeout=60).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if command("git", "status", "--porcelain", cwd=SOURCE):
        raise ValueError("provider source must be clean")
    tests = [
        "test_spf_buffer_layout",
        "test_spf_tandem_metadata",
        "test_spf_tandem_session",
        "test_spf_hop_device_userspace",
        "test_spf_hop_scheduler",
        "test_spf_hop_session",
        "test_spf_hop_protocol",
        "test_spf_hop_adaptive",
        "test_spf_sampler_coverage",
    ]
    results = {test: command(str(NATIVE / "tests" / test)) for test in tests}
    destination = ROOT / "runtime/scanner-iiod/iiod"
    shutil.copyfile(BUILD / "iiod/iiod", destination)
    command(str(SDK / "bin/arm-linux-gnueabihf-strip"), "--strip-unneeded", str(destination))
    destination.chmod(0o755)
    dynamic = command("readelf", "-d", str(destination))
    symbols = command("readelf", "-Ws", str(destination))
    if re.search(r"\bUND\s+iio_", symbols) or "RPATH" in dynamic or "RUNPATH" in dynamic:
        raise ValueError("daemon contains an unbundled libiio dependency or build path")
    if "Machine:                           ARM" not in command("readelf", "-h", str(destination)):
        raise ValueError("daemon is not ARM")
    document = {
        "schema": "spf.iiod-build-provenance.v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hardware_accessed": False,
        "artifact": {
            "path": str(BUILD / "iiod/iiod"),
            "sha256": digest(destination),
            "size_bytes": destination.stat().st_size,
            "elf_machine": "ARM",
            "format": command("file", "-b", str(destination)),
            "libiio_linkage": "static",
            "scanner_sdk_linkage": "static",
            "undefined_iio_symbol_count": 0,
            "elf_build_id_sha1": re.search(
                r"Build ID: ([0-9a-f]+)", command("readelf", "-n", str(destination))
            )[1],
        },
        "source": {
            "repository": str(SOURCE),
            "origin": command("git", "remote", "get-url", "origin", cwd=SOURCE),
            "head": command("git", "rev-parse", "HEAD", cwd=SOURCE),
            "tree": command("git", "rev-parse", "HEAD^{tree}", cwd=SOURCE),
            "base_commit": "a1088b61de3c57762cfed5533e1baf8076a7b726",
            "worktree_clean": True,
            "provider_input_sha256": {
                str(path.relative_to(SOURCE)): digest(path)
                for path in sorted((SOURCE / "iiod").glob("*"))
                if path.is_file() and path.suffix in (".c", ".h", ".txt", ".l", ".y")
            },
        },
        "scanner_sdk": {
            "archive_sha256": digest(SCANNER_ARCHIVE),
            "source_sha256": {
                str(path.relative_to(ROOT)): digest(path)
                for path in sorted((ROOT / "src/leo/scanner/native_presence").glob("*"))
                if path.is_file() and path.suffix in (".c", ".h")
            },
        },
        "configuration": {
            "build_type": "Release",
            "build_shared_libs": False,
            "dns_sd": False,
            "arm_cmake_cache_sha256": digest(BUILD / "CMakeCache.txt"),
            "single_rx_multirate_capability": "15/20 MS/s; RX0; 2.5 MS/s decisions",
            "host_feedback_wire_versions": [3, 4],
            "note": (
                "Host-adaptive requests disable on-radio GLRT. "
                "Legacy GLRT uses its separate companion bundle."
            ),
        },
        "dynamic_dependencies": re.findall(r"Shared library: \[([^]]+)\]", dynamic),
        "validation": {
            "native_tests": tests,
            "outputs": results,
            "all_passed": True,
            "hardware_accessed": False,
        },
        "runtime": {
            "recommended_release_relative_path": "runtime/scanner-iiod/iiod",
            "interactive_flag_must_be_absent": True,
            "default_port": 30431,
            "alternate_port": 30432,
        },
        "reproduction": {
            "script": str(Path(__file__).relative_to(ROOT)),
            "commands": [
                ["cmake", "-S", str(SOURCE), "-B", str(BUILD),
                 "-DCMAKE_TOOLCHAIN_FILE=" + str(SDK / "share/buildroot/toolchainfile.cmake")],
                ["cmake", "--build", str(BUILD), "--target", "iiod", "-j4"],
            ],
            "compiler_version": command(str(SDK / "bin/arm-linux-gnueabihf-gcc"), "--version"),
            "toolchain_file_sha256": digest(SDK / "share/buildroot/toolchainfile.cmake"),
            "strip": [
                str(SDK / "bin/arm-linux-gnueabihf-strip"),
                "--strip-unneeded",
                str(destination),
            ],
        },
    }
    (destination.parent / "provenance.json").write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps(document["artifact"], indent=2))


if __name__ == "__main__":
    main()
