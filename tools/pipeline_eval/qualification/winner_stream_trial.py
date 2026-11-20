"""Qualify the fixed per-probe winner stream on full wide, saved native inputs."""

import argparse
import gzip
import resource
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter, process_time, time_ns
from uuid import uuid4

from .. import cavity_runtime, whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS
from ..variants import winner_stream
from . import cavity_payload_trial as apparatus
from . import cavity_pressure_trial as pressure
from .full_receiver_comparison import read, require_fields, sha

SCREEN = pressure.direct.common.SCREEN
REPORT = SCREEN / "acquisition-support/winner-stream"
WIDE = SCREEN / "detector-origins/whole-band"
REPLAY = pressure.ORIGINAL.parent.parent
LANES = {3: ("DS26-0036", "DS29-0247"), 5: ("DS29-0082",)}
ORDER = {
    "DS26-0036": ("stock", "winner"),
    "DS29-0082": ("winner", "stock"),
    "DS29-0247": ("winner", "stock"),
}
METHODS = {"stock": "phase_release_stock", "winner": "winner_stream"}
LIMIT = 190
OVERLAY = "tools/pipeline_eval/variants/winner_stream.py"
DIRECT = "tools/pipeline_eval/variants/v5_direct_cavity.py"
INPUT = "leo/application/localization_v3.py"
OBSERVE = Path(__file__).with_name("winner_stream_observe.py")


def splice(text, old, new):
    if text.count(old) != 1:
        raise ValueError("standalone source does not contain the pinned winner-stream anchor")
    return text.replace(old, new)


def install(root, candidate):
    files = cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")
    cavity_runtime.install(root, profile="phase-release")
    for name, expected in files.items():
        if (root / name).read_bytes() != expected:
            raise ValueError("installed release changed before the optional input overlay")
    if candidate:
        entry = root / "__main__.py"
        entry.write_text(
            splice(
                entry.read_text(),
                '    parser.add_argument("--width-km", type=float, default=25)',
                '    parser.add_argument("--width-km", type=float, default=25)\n'
                '    parser.add_argument("--native-origin-sha256")',
            )
        )
        direct = root / DIRECT
        source = splice(
            direct.read_text(),
            "    width_km=25.0,\n",
            "    width_km=25.0,\n    native_origin_sha256=None,\n",
        )
        read_native = (
            'document = read_native(dict(path=native, sha256="sha256:" + '
            'native_sha256.removeprefix("sha256:")))\n'
        )
        direct.write_text(
            splice(
                source,
                "    " + read_native,
                "    if native_origin_sha256 is None:\n"
                "        " + read_native + "    else:\n"
                "        from .winner_stream import read\n\n"
                "        document = read(native, native_sha256, native_origin_sha256)\n",
            )
        )
        handoff = root / INPUT
        handoff.write_text(
            splice(
                handoff.read_text(),
                "    prepared = prepare_owned(prepare_tracks, document, track_config)\n",
                "    from tools.pipeline_eval.variants.winner_stream "
                "import WinnerInput, prepare\n\n"
                "    if isinstance(document, WinnerInput):\n"
                "        prepared = prepare(document, track_config)\n"
                "    else:\n"
                "        prepared = prepare_owned(prepare_tracks, document, track_config)\n",
            )
        )
        (root / OVERLAY).write_bytes(Path(winner_stream.__file__).read_bytes())
    return whole_iq.receiver_identity(root)


def bindings(ident, wide):
    folder = REPLAY / ident / "wide"
    raw = read(folder / "raw.json")
    case, original = whole_iq.binding(ident)
    source = whole_iq.checked(folder / "recording/native.json", raw["native_sha256"])
    request = whole_iq.checked(folder / "recording/request.json", raw["request_sha256"])
    pressure.verify_request(
        read(request),
        original,
        native_path=str(source),
        native_sha256=raw["native_sha256"],
    )
    compressed = WIDE / "native" / (ident + ".json.gz")
    require_fields(wide["files"], {str(compressed.relative_to(WIDE)): sha(compressed)})
    with gzip.open(compressed, "rb") as stream:
        from hashlib import file_digest

        if file_digest(stream, "sha256").hexdigest() != sha(source):
            raise ValueError(
                "scratch wide native input differs from the published authenticated export"
            )
    return dict(
        id=ident,
        native=str(source),
        request=str(request),
        native_sha256=sha(source),
        request_sha256=sha(request),
        input_sha256=sha(request),
        tile=case["regions"][0],
        catalog_sha256=case["catalog"]["sha256"],
        original_native_sha256=case["native"]["sha256"],
        detector_sha256=read(folder / "plan.json")["detector_sha256"],
    )


def lock(work):
    work.mkdir(exist_ok=False)
    wide = read(WIDE / "prediction-lock.json")
    require_fields(wide["files"], {"source-lock.json": sha(WIDE / "source-lock.json")})
    stock, candidate = (install(work / m, m == "winner") for m in METHODS)
    if {name for name, value in candidate.items() if stock.get(name) != value} != {
        DIRECT,
        INPUT,
        OVERLAY,
        "__main__.py",
        "native/manifest.json",
    }:
        raise ValueError("candidate differs outside the phase-release handoff")
    sources = (Path(__file__), OBSERVE, Path(winner_stream.__file__), REPORT / "PROTOCOL.md")
    save_json(
        work / "plan.json",
        dict(
            cases={ident: bindings(ident, wide) for ident in ORDER},
            order=ORDER,
            pins=LANES,
            files={"stock": stock, "winner": candidate},
            wide_lock_sha256=sha(WIDE / "prediction-lock.json"),
            source={p.name: sha(p) for p in sources},
            frozen_at_ns=time_ns(),
            limit_s=LIMIT,
            memory_bytes=512 * 1024**2,
            swap_bytes=0,
        ),
    )


def convert_case(work, ident, case):
    output = work / "input" / (ident + ".winners")
    output.parent.mkdir(exist_ok=True)
    start, cpu = perf_counter(), process_time()
    pending = output.with_suffix(".pending")
    with Path(case["native"]).open("rb") as source, pending.open("xb") as dest:
        digest, size = winner_stream.convert(source, dest, case["native_sha256"])
    pending.rename(output)
    receipt = dict(
        sha256=digest,
        native_sha256=case["native_sha256"],
        bytes=size,
        native_bytes=Path(case["native"]).stat().st_size,
        wall_s=perf_counter() - start,
        cpu_s=process_time() - cpu,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    save_json(output.with_suffix(".json"), receipt)
    return output, receipt


def qualify(work, plan, ident, mode, cpu):
    import subprocess

    case = plan["cases"][ident]
    root = work / mode
    require_fields(whole_iq.receiver_identity(root), plan["files"][mode])
    output = work / "runs" / ident / mode
    output.mkdir(exist_ok=False, parents=True)
    flags = pressure.command_flags(case)
    receipt = None
    if mode == "winner":
        pkg = work / "input" / (ident + ".winners")
        converter = [
            "taskset",
            "-c",
            str(cpu),
            "nice",
            "-n",
            "10",
            str(pressure.direct.v5_lean.PYTHON),
            "-m",
            __spec__.name,
            "convert",
            str(work),
            "--case",
            ident,
        ]
        subprocess.run(converter, check=True, timeout=25)
        receipt = read(pkg.with_suffix(".json"))
        flags[flags.index("--native") + 1] = str(pkg)
        flags[flags.index("--native-sha256") + 1] = receipt["sha256"]
        flags.extend(("--native-origin-sha256", case["native_sha256"]))
    unit = "leo-winners-" + uuid4().hex[:10]
    command = [
        "systemd-run",
        "--user",
        "--pipe",
        "--wait",
        f"--unit={unit}",
        f"--working-directory={root}",
        f"--setenv=TMPDIR={work}",
        "--property=MemoryMax=536870912",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        *(f"--setenv={key}=1" for key in apparatus.THREADS),
        "/usr/bin/taskset",
        "-c",
        str(cpu),
        str(pressure.direct.v5_lean.PYTHON),
        "-IB",
        str(OBSERVE),
        unit,
        str(cpu),
        str(root),
        mode,
        *flags,
    ]
    started = perf_counter()
    code, failure = apparatus.supervise(command, unit, output)
    wall = perf_counter() - started
    result, measured, code = apparatus.service_result(output, code, failure)
    result.setdefault("arms", {arm: {"latlon": None} for arm in ARMS})
    log = output / "stderr"
    import json

    boundary = next(
        (
            json.loads(line[9:])
            for line in log.read_text().splitlines()
            if line.startswith("boundary ")
        ),
        None,
    )
    save_json(
        output / "attempt.json",
        dict(
            case,
            method=METHODS[mode],
            worker_mode=mode,
            mode="matched-tile",
            cpu=cpu,
            wall_s=wall,
            exit_code=code,
            measurements=measured,
            boundary=boundary,
            conversion=receipt,
            result=result,
            worker_log_sha256=sha(log),
            source_lock_sha256=sha(work / "plan.json"),
        ),
    )
    print(ident, mode, result["status"], round(wall, 3), result.get("reason") or "", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "run", "convert", "install"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--case", choices=ORDER)
    args = parser.parse_args()
    if args.action == "install":
        install(args.work, True)
    elif args.action == "seal":
        lock(args.work)
    else:
        plan = read(args.work / "plan.json")
        sources = (Path(__file__), OBSERVE, Path(winner_stream.__file__), REPORT / "PROTOCOL.md")
        require_fields(plan["source"], {path.name: sha(path) for path in sources})
        if args.action == "convert":
            convert_case(args.work, args.case, plan["cases"][args.case])
            return

        def lane(job):
            cpu, cases = job
            for ident in cases:
                for mode in plan["order"][ident]:
                    qualify(args.work, plan, ident, mode, cpu)

        with ThreadPoolExecutor(max_workers=len(LANES)) as pool:
            list(pool.map(lane, LANES.items()))


if __name__ == "__main__":
    main()
