"""Bounded local cross-build, never an installer or RF runner."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import uuid

from tools.native_presence import ROOT, build_scanner_glrt_port, build_worker, write_templates
from tools.presence_fftw import fftw_options
from pluto_plus.userspace_iiod_bundle import load_iiod_companion_bundle

out = Path(__file__).resolve().parent
release = out / "release"
release.mkdir(mode=0o700)
runtime = "/tmp/ppu-iiod-bundle-" + uuid.uuid4().hex
fw = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host")
sysroot = fw / "arm-buildroot-linux-gnueabihf/sysroot"
libiio = Path("/home/mouse9911/gits/libiio-arm-glrt-frame-integration")
previous = ROOT / "reports/evidence/2026_09_08_scanner_glrt_provider/receipt.json"
protocol = ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()

def save(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value))
    path.chmod(0o600)

def run(command, log):
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    save(out / (log + ".json"), dict(command=list(map(str, command)), returncode=result.returncode,
                                    stdout=result.stdout, stderr=result.stderr))
    if result.returncode:
        raise RuntimeError(f"{log}: {result.stderr[-2000:]}")
    return result.stdout

compiler = str(fw / "bin/arm-linux-gnueabihf-gcc")
config = json.loads(protocol.read_bytes())
flags = tuple(config["common_flags"]) + tuple(
    f"-DLEO_PRESENCE_{key}={value}" for key, value in config["variants"][0]["defines"].items()
) + (
    "-DLEO_PRESENCE_DIFFERENTIAL_CI16=1", "-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1",
    "-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1", "-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED=1",
    "-DLEO_PRESENCE_BOUNDED_MAGNITUDE=1", "-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION=1",
)
armflags = ("-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard")
fftw = fftw_options(sysroot / "usr", runtime_rpath=False)
inputs = {str(p): sha(p) for p in (previous, protocol, Path(__file__), *fftw["dependencies"])}
sources = {str(p): sha(p) for p in libiio.rglob("*")
           if p.is_file() and p.suffix in {".c", ".h", ".txt", ".cmake", ".in", ".y", ".l"}}
sdk = build_scanner_glrt_port(release / "libleo-scanner-glrt.so", compiler=compiler,
    cflags=armflags + ("-Wl,-soname,libleo-scanner-glrt.so",))
worker = build_worker(release / "worker", compiler=compiler,
    cflags=flags + armflags + fftw["cflags"], dependencies=fftw["dependencies"],
    ldflags=fftw["ldflags"] + (f"-Wl,--disable-new-dtags,-rpath,{runtime}",))
shutil.copyfile(fftw["dependencies"][1], release / "libfftw3.so.3")
templates = {}
for rate in (2500000, 5000000):
    path = release / f"templates-{rate}.bin"
    write_templates(path, rate)
    templates[str(rate)] = sha(path)
algorithm = {
    "schema": "org.leo.scanner.glrt-algorithm-build/v1",
    "worker_sha256": sha(worker), "sdk_sha256": sha(sdk),
    "fftw_sha256": sha(release / "libfftw3.so.3"),
    "native_defines": flags,
}
configuration = {
    "schema": "org.leo.scanner.glrt-runtime-configuration/v1",
    "rx": 1, "rates_hz": [2500000, 5000000], "bandwidth_equals_rate": True,
    "valid_dwell_ms": 120, "maximum_capture_seconds": 300,
    "confirmation_budget": 1, "decision_policy": "unqualified-evidence",
    "profile_if_hz": [959687500 + j * 250000000 for j in range(4)]
                     + [1190312500 + j * 250000000 for j in range(4)],
    "templates_sha256": templates,
}
algorithm_hash = hashlib.sha256(canonical(algorithm)).hexdigest()
configuration_hash = hashlib.sha256(canonical(configuration)).hexdigest()
save(release / "algorithm.json", algorithm)
save(release / "configuration.json", configuration)
receipt = json.loads(previous.read_bytes())
arguments = receipt["arm_cmake_args"]
overrides = {
    "CMAKE_BUILD_TYPE": "Release", "WITH_TESTS": "OFF",
    "CMAKE_BUILD_WITH_INSTALL_RPATH": "ON", "CMAKE_INSTALL_RPATH": runtime,
    "CMAKE_INSTALL_RPATH_USE_LINK_PATH": "OFF",
    "CMAKE_EXE_LINKER_FLAGS": "-Wl,--disable-new-dtags",
    "CMAKE_SHARED_LINKER_FLAGS": "-Wl,--disable-new-dtags",
    "IIOD_SCANNER_GLRT_LIBRARY": str(sdk),
    "IIOD_SCANNER_GLRT_WORKER_PATH": runtime + "/worker",
    "IIOD_SCANNER_GLRT_TEMPLATES_2500000": runtime + "/templates-2500000.bin",
    "IIOD_SCANNER_GLRT_TEMPLATES_5000000": runtime + "/templates-5000000.bin",
    "IIOD_SCANNER_GLRT_ALGORITHM_SHA256": algorithm_hash,
    "IIOD_SCANNER_GLRT_CONFIGURATION_SHA256": configuration_hash,
}
options = {}
for arg in arguments:
    if arg.startswith("-D"):
        key, value = arg[2:].split("=", 1)
        options[key] = value
options.update(overrides)
external_sources = options["IIOD_BUFFER_METADATA_PROVIDER_EXTRA_SOURCES"].split(";")
external_roots = options["IIOD_BUFFER_METADATA_INCLUDE_DIRS"].split(";")
for filename in external_sources:
    inputs[filename] = sha(Path(filename))
for directory in external_roots:
    for path in Path(directory).rglob("*.h"):
        inputs[str(path)] = sha(path)
run(["cmake", "-S", str(libiio), "-B", str(out / "build")]
    + [f"-D{k}={v}" for k, v in options.items()], "configure")
run(["cmake", "--build", str(out / "build"), "--target", "iiod", "-j", "4"], "compile")
shutil.copyfile(out / "build/iiod/iiod", release / "iiod")
shutil.copyfile((out / "build/libiio.so.0").resolve(), release / "libiio.so.0")
for name in ("libxml2.so.2", "libz.so.1"):
    source = (sysroot / "usr/lib" / name).resolve()
    inputs[str(source)] = sha(source)
    shutil.copyfile(source, release / name)

names = ["worker", "libleo-scanner-glrt.so", "libfftw3.so.3", "libiio.so.0",
         "libxml2.so.2", "libz.so.1", "templates-2500000.bin", "templates-5000000.bin"]
for name in ["iiod", *names]:
    (release / name).chmod(0o700 if name in {"iiod", "worker"} else 0o600)
core = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1",
        "ld-linux-armhf.so.3", "libgcc_s.so.1"}
elf = {}
for name in ["iiod", *names[:6]]:
    dynamic = run([str(fw / "bin/arm-linux-gnueabihf-readelf"), "-d", str(release / name)],
                  "dynamic-" + name)
    header = run([str(fw / "bin/arm-linux-gnueabihf-readelf"), "-h", str(release / name)],
                 "header-" + name)
    assert "ARM" in header and "hard-float ABI" in header
    needed = re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic)
    paths = re.findall(r"\((?:RPATH|RUNPATH)\).*?\[(.*?)\]", dynamic)
    assert set(needed) <= set(names) | core, (name, needed)
    assert not paths or paths == [runtime], (name, paths)
    if name in {"iiod", "worker", "libiio.so.0"}:
        assert paths == [runtime], (name, paths)
    elf[name] = dict(needed=needed, runtime_paths=paths, sha256=sha(release / name))
manifest = dict(schema_version=1, remote_directory=runtime,
                daemon_sha256=sha(release / "iiod"), daemon_bytes=(release / "iiod").stat().st_size,
                files=[dict(name=name, sha256=sha(release / name),
                            bytes=(release / name).stat().st_size, executable=name == "worker")
                       for name in names])
save(release / "bundle.json", manifest)
snapshot = load_iiod_companion_bundle(release / "bundle.json")
assert snapshot.daemon_sha256 == sha(release / "iiod")
assert inputs == {path: sha(Path(path)) for path in inputs}
assert sources == {path: sha(Path(path)) for path in sources}
save(out / "receipt.json", dict(
    schema="org.leo.research.scanner-glrt-userspace-bundle/v1",
    scope="Local ARM cross-build and loader-path inspection, not execution/deployment/RF",
    runtime_directory=runtime, algorithm_sha256=algorithm_hash,
    configuration_sha256=configuration_hash, manifest_sha256=sha(release / "bundle.json"),
    release_manifest=manifest, elf=elf, build_inputs=inputs, libiio_sources=sources,
    system_dependencies_not_bundled=sorted(core),
    open_gates=["target system-library compatibility and startup", "live no-duty-regression",
                "detector decision qualification", "authorized deployment/merge"],
))
print(json.dumps(dict(release=str(release), manifest_sha256=snapshot.manifest_sha256,
    algorithm_sha256=algorithm_hash, configuration_sha256=configuration_hash,
    files=len(names) + 1, bytes=manifest["daemon_bytes"] + sum(f["bytes"] for f in manifest["files"])),
    indent=2), flush=True)
