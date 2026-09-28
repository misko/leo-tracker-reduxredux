"""Prepare a self-contained four-rate, four-variant saved-IQ ARM experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from leo.analysis.starlink.templates import qin_edge_pilot_frame

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = ROOT / "reports/2026_09_27_ds5_cached_tracking"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
TOOLCHAIN = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host")
SYSROOT = TOOLCHAIN / "arm-buildroot-linux-gnueabihf/sysroot"
FLOAT_ROOT = Path("/var/tmp/leo-fftw-float-20260912/install")
RATES = (2_500_000, 5_000_000, 7_500_000, 10_000_000)
METHODS = {"A": (False, False), "B": (False, True),
           "C": (True, False), "D": (True, True)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def replace_checked(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError(f"source changed: expected {count} occurrences of {old!r}")
    return text.replace(old, new)


def extend_source(name, text):
    """Experiment-only rate admission and scratch-capacity fixes, no resampling."""
    if name in ("presence.c", "window_rank.c"):
        if name == "presence.c":
            text = replace_checked(text, "(rate != 2500000 && rate != 5000000)",
                "(rate != 2500000 && rate != 5000000 && rate != 7500000 && rate != 10000000)")
            text = replace_checked(text, "12*23*12", "12*45*12", 2)
            text = replace_checked(text, "CFO_COUNT * 23", "CFO_COUNT * 45", 2)
            text = replace_checked(text, "w->rate = rate; w->n = n; w->max_samples = rate / 50;",
                "w->rate = rate; w->n = n; w->max_samples = rate / 50;\n"
                "    size_t input_capacity=rate/500;\n"
                "    if (LEO_PRESENCE_FAST_FINE_FFT) { input_capacity=2; while(input_capacity<n) input_capacity*=2; }")
            text = replace_checked(text, "ALLOC(input, rate / 500)", "ALLOC(input, input_capacity)")
            # 7.5 MS/s uses a 16384-point fine FFT (~457.8 Hz): the full
            # +/-400 kHz grid exceeds the historical 1602-element arrays.
            text = replace_checked(text, "frequencies[1602], scores[1602]",
                                   "frequencies[2048], scores[2048]")
            text = replace_checked(text, "w->fine_step_hz=(double)rate/fine_size;",
                "w->fine_step_hz=(double)rate/fine_size;\n"
                "    if (ceil(800000.0/w->fine_step_hz)+2 > 2048) { leo_presence_destroy(w); return NULL; }")
            text = replace_checked(text, "w->frequencies[k] = -400000.0 + k * 80000.0;",
                "if (w->stops[k]-w->starts[k] > 45) { leo_presence_destroy(w); return NULL; }\n"
                "        w->frequencies[k] = -400000.0 + k * 80000.0;")
        else:
            text = replace_checked(text, "(rate!=2500000 && rate!=5000000)",
                "(rate!=2500000 && rate!=5000000 && rate!=7500000 && rate!=10000000)")
    if name == "coarse_fp32.h":
        text = replace_checked(text, "symbol*23*12", "symbol*45*12", 3)
    return text


def snapshot(output):
    native = output / "src/native_presence"
    native.mkdir(parents=True)
    provenance = {}
    for parent in (DEPLOY / "src/leo/analysis/native_presence", PRIOR / "native"):
        for source in sorted(parent.iterdir()):
            if source.suffix not in (".c", ".h", ".inc"):
                continue
            provenance[str(source)] = sha(source)
            target = native / source.name
            if target.exists():
                raise ValueError(f"duplicate source {target}")
            target.write_text(extend_source(source.name, source.read_text()))
    grid = DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc"
    (output / "src/starlink").mkdir()
    shutil.copyfile(grid, output / "src/starlink" / grid.name)
    provenance[str(grid)] = sha(grid)
    fft = PRIOR / "fft32/fft32_fftw.c"
    shutil.copyfile(fft, native / fft.name)
    provenance[str(fft)] = sha(fft)
    probe = PRIOR / "review/arm_probe/probe.c"
    provenance[str(probe)] = sha(probe)
    text = probe.read_text()
    text = replace_checked(text, "#define _POSIX_C_SOURCE 200809L",
        "#define _GNU_SOURCE\n#define _POSIX_C_SOURCE 200809L\n#include <sched.h>")
    text = replace_checked(text, "if (argc!=7) {", "alarm(15);\n"
        "    cpu_set_t allowed, chosen;\n"
        "    if (sched_getaffinity(0,sizeof(allowed),&allowed)) return 2;\n"
        "    int core=-1;\n"
        "    for(int i=0;i<CPU_SETSIZE;++i) if(CPU_ISSET(i,&allowed)) { core=i; break; }\n"
        "    if(core<0) return 2;\n"
        "    CPU_ZERO(&chosen); CPU_SET(core,&chosen);\n"
        "    if(sched_setaffinity(0,sizeof(chosen),&chosen)) return 2;\n"
        "    if(sched_getaffinity(0,sizeof(allowed),&allowed) || CPU_COUNT(&allowed)!=1 || !CPU_ISSET(core,&allowed)) return 2;\n"
        "    fprintf(stderr,\"single_core=%d pid=%ld\\n\",core,(long)getpid());\n"
        "    if (argc!=7) {")
    text = replace_checked(text, "(rate!=2500000 && rate!=5000000)",
        "(rate!=2500000 && rate!=5000000 && rate!=7500000 && rate!=10000000)")
    text = replace_checked(text, "rep<3", "rep<5")
    (native / "probe.c").write_text(text)
    profile_path = PRIOR / "native/profile.json"
    provenance[str(profile_path)] = sha(profile_path)
    profile = json.loads(profile_path.read_text())
    profile["rates_hz"] = list(RATES)
    profile["experiment_scope"] = "four-rate native blind detection; no RF; no decimation"
    write_json(output / "profile.json", profile)
    for name, expected in provenance.items():
        if sha(name) != expected:
            raise ValueError(f"source changed during snapshot: {name}")
    write_json(output / "source_origins.json", provenance)


def selected_cases():
    result = []
    for directory in (PRIOR / "dataset", PRIOR / "new_data",
                      ROOT / "reports/2026_09_26_ds5_server_eval/dataset"):
        manifest = directory / "cases.json"
        for case in json.loads(manifest.read_text())["cases"]:
            high_dataset = directory.name == "dataset" and "server_eval" in str(directory)
            include = ((case["split"] == "control" or
                        (case["split"] == "dev" and case["rate_hz"] in RATES[2:]))
                       if high_dataset else
                       case["split"] == "dev" and case["block_offset"] < 16)
            if include:
                result.append({**case, "source_directory": str(directory),
                               "manifest_sha256": sha(manifest)})
    return sorted(result, key=lambda c: (c["split"] != "control", c["rate_hz"],
                  c.get("session_id", ""), c.get("source_start_counter", 0), c["case_id"]))


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    snapshot(output)
    data = output / "data"
    data.mkdir()
    cases = []
    templates = {}
    for index, case in enumerate(selected_cases()):
        source = Path(case["source_directory"]) / case["raw_npy"]["path"]
        expected = case["raw_npy"]["sha256"].removeprefix("sha256:")
        if sha(source) != expected:
            raise ValueError(f"IQ hash mismatch: {source}")
        iq = np.load(source, allow_pickle=False)
        if iq.dtype != np.dtype("<i2") or iq.shape != (case["rate_hz"]*120//1000, 2, 2):
            raise ValueError(f"bad shape/dtype: {source}")
        raw = data / f"case-{index:03d}.ci16"
        raw.write_bytes(iq.tobytes(order="C"))
        if sha(source) != expected:
            raise ValueError("IQ changed during export")
        key = f"{case['rate_hz']}-{case['edge']}"
        if key not in templates:
            template = {}
            for roll, label in ((0, "exact"), (17, "control")):
                path = data / f"{key}-{label}.c128"
                values = np.asarray(qin_edge_pilot_frame(case["rate_hz"], case["edge"], symbol_roll=roll), dtype="<c16")
                path.write_bytes(values.tobytes())
                template[label] = path.name
                template[label+"_sha256"] = sha(path)
            templates[key] = template
        cases.append({**case, "raw_file": raw.name, "raw_sha256": sha(raw), "template_key": key})
    write_json(output / "manifest.json", {"cases": cases, "templates": templates,
        "rates_hz": list(RATES), "primary_rate_hz": RATES[0], "repetitions": 5,
        "scope": "exposed development and controls; native rates; no RF"})


def build(output, host=False, sanitize=False):
    native = output / "src/native_presence"
    profile = json.loads((output / "profile.json").read_text())
    bin_dir = output / ("host-asan" if sanitize else "host" if host else "arm")
    bin_dir.mkdir(exist_ok=False)
    cc = "gcc" if host else str(TOOLCHAIN / "bin/arm-linux-gnueabihf-gcc")
    flags = ["-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra", "-Werror", *profile["flags"]]
    if not host:
        flags += ["--sysroot="+str(SYSROOT), "-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard"]
    if sanitize:
        flags += ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-no-pie"]
    receipts = {}
    sources_before = {str(p.relative_to(output)): sha(p) for p in sorted((output / "src").rglob("*")) if p.is_file()}
    for method, (aligned, fp32) in METHODS.items():
        command = [cc, *flags, '-DPROBE_METHOD="'+method+'"', f"-DPROBE_ALIGNED={int(aligned)}",
                   "-I", str(native), str(native / "probe.c")]
        command += ([str(native / "blind_aligned_v5.c")] if aligned else
                    [str(native / f) for f in ("presence.c", "window_rank.c", "dwell.c")])
        if fp32:
            command += [str(native / "fft32_fftw.c")]
            command += ["-lfftw3f"] if host else ["-I", str(FLOAT_ROOT / "include"), str(FLOAT_ROOT / "lib/libfftw3f.a")]
        else:
            command += ["-DLEO_PRESENCE_FFTW=1", str(native / "fft.c")]
            command += ["-lfftw3"] if host else ["-L", str(SYSROOT / "usr/lib"), "-l:libfftw3.so.3.6.10", "-Wl,-rpath,$ORIGIN"]
        command += ["-lm", "-o", str(bin_dir / method)]
        compiled = subprocess.run(command, capture_output=True, timeout=90)
        (bin_dir / (method+".build.stderr")).write_bytes(compiled.stderr)
        if compiled.returncode:
            raise RuntimeError(compiled.stderr.decode(errors="replace"))
        receipts[method] = {"command": command, "sha256": sha(bin_dir / method)}
    if not host:
        shutil.copyfile(SYSROOT / "usr/lib/libfftw3.so.3.6.10", bin_dir / "libfftw3.so.3")
    sources_after = {str(p.relative_to(output)): sha(p) for p in sorted((output / "src").rglob("*")) if p.is_file()}
    if sources_before != sources_after:
        raise ValueError("sources changed while building")
    write_json(bin_dir / "build.json", {"methods": receipts, "sources": sources_before,
        "compiler": subprocess.check_output([cc, "--version"], text=True),
        "profile_sha256": sha(output / "profile.json"),
        "fftw_fp32_archive_sha256": sha(FLOAT_ROOT / "lib/libfftw3f.a") if not host else None,
        "runtime_files": {p.name: sha(p) for p in bin_dir.iterdir()
                          if p.name in METHODS or p.name == "libfftw3.so.3"}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "build", "host", "asan"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.output.resolve())
    else:
        build(args.output.resolve(), host=args.action != "build", sanitize=args.action == "asan")
