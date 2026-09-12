"""Package the bounded local iiOD build and its exact source provenance; no RF."""

import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("/home/mouse9911/gits/libiio-single-rx-10m")
BUILD = Path("/tmp/leo-single-rx-iiod-arm")
NATIVE = Path("/tmp/leo-single-rx-iiod-native")
SDK = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host")


def command(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert not command("git", "status", "--porcelain", cwd=SOURCE)
revision = command("git", "rev-parse", "HEAD", cwd=SOURCE)
binary = BUILD / "iiod/iiod"
readelf = str(SDK / "bin/arm-linux-gnueabihf-readelf")
dynamic = command(readelf, "-d", str(binary))
symbols = command(readelf, "-Ws", str(binary))
assert not re.search(r"\bUND\s+iio_", symbols)
assert "RPATH" not in dynamic and "RUNPATH" not in dynamic
assert "Machine:                           ARM" in command(readelf, "-h", str(binary))
tests = [
    "test_spf_buffer_layout",
    "test_spf_tandem_metadata",
    "test_spf_tandem_session",
    "test_spf_hop_device_userspace",
    "test_spf_hop_scheduler",
    "test_spf_hop_session",
    "test_spf_hop_protocol",
    "test_spf_hop_adaptive",
]
for test in tests:
    subprocess.run([NATIVE / "tests" / test], check=True, timeout=30)

document = json.loads(command("git", "show", "HEAD:runtime/scanner-iiod/provenance.json", cwd=ROOT))
old_source = document["source"]["repository"]
document["created_at_utc"] = datetime.now(UTC).isoformat()
document["artifact"].update(
    path=str(binary),
    sha256=digest(binary),
    size_bytes=binary.stat().st_size,
    elf_build_id_sha1=re.search(r"Build ID: ([0-9a-f]+)", command(readelf, "-n", str(binary)))[1],
)
document["source"] = dict(
    repository=str(SOURCE),
    origin=command("git", "remote", "get-url", "origin", cwd=SOURCE),
    head=revision,
    base_commit="a1088b61de3c57762cfed5533e1baf8076a7b726",
    tree=command("git", "rev-parse", "HEAD^{tree}", cwd=SOURCE),
    worktree_clean=True,
    provider_input_sha256={
        str(path.relative_to(SOURCE)): digest(path)
        for path in sorted((SOURCE / "iiod").glob("*"))
        if path.is_file() and path.suffix in (".c", ".h", ".txt", ".l", ".y")
    },
)
document["validation"] = dict(native_tests=tests, all_passed=True, hardware_accessed=False)
document["dynamic_dependencies"] = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
reproduction = document["reproduction"]
old_native = reproduction["native_build_directory"]
for key in ("native_configure_arguments", "arm_configure_arguments"):
    reproduction[key] = [
        arg.replace(old_source, str(SOURCE)).replace(old_native, str(NATIVE))
        for arg in reproduction[key]
    ]
reproduction["native_build_arguments"] = [
    arg.replace(old_native, str(NATIVE)) for arg in reproduction["native_build_arguments"]
]
reproduction["script"] = str(Path(__file__).relative_to(ROOT))
reproduction["native_build_directory"] = str(NATIVE)
reproduction["arm_build_directory_for_staged_artifact"] = str(BUILD)
for key in (
    "arm_install_root_for_staged_artifact",
    "arm_install_environment",
    "arm_install_arguments",
):
    reproduction.pop(key, None)  # This artifact was copied from the build, without cmake install.
for key in ("metadata_provider", "persistent_hop_device_provider"):
    document["configuration"][key] = document["configuration"][key].replace(old_source, str(SOURCE))
document["configuration"]["arm_cmake_cache_sha256"] = digest(BUILD / "CMakeCache.txt")
for key in ("alternate_tcp_server_command", "alternate_tcp_server_command_explicit_local_context"):
    document["runtime"][key][0] = f"/path/to/iiod-armv7l-{revision[:7]}"
document["configuration"]["single_rx_10m_capability"] = "iio,buffer-persistent-hop-single-rx-10m=1"
destination = ROOT / "runtime/scanner-iiod/iiod"
shutil.copyfile(binary, destination)
destination.chmod(0o755)
(destination.parent / "provenance.json").write_text(json.dumps(document, indent=2) + "\n")
print(json.dumps(document["artifact"], indent=2))
