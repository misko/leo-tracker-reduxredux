"""Audit the matched project-owned Python and C detector footprints."""

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
RELEASE = Path("/srv/bulk/leo-dev/pipeline-eval-20261118/clean-checkout")
PLANNING = ROOT / "reports/2026_11_19_receiver_screening/coarse-and-navigation/fft-length"
VARIANTS = ROOT / "tools/pipeline_eval/variants"
CAPTURE_EXACT = Path(
    "/srv/bulk/leo-dev/receiver-screening-20261119/capture-exact-v2/source-lock.json"
)
PROTOCOL = (
    ROOT / "reports/2026_11_19_receiver_screening/native-receiver/detector-footprint/PROTOCOL.md"
)
PROTOCOL_SHA = "954374259c8fb586aee45c2b1cc4acc27fb339daccfe84c7811dac6f661a0366"
VISITS = {
    0: (2, 2, "e51418c694fd8a91cd9f3832d487921b3dd16ecf97d6ab3a1471625a4a26a0eb"),
    2: (3, 1, "d96535002ad4d9a64dc2f0091ec1ce22db005ab7ca171893cc09dc887072a2d8"),
    4: (2, 0, "39d828581d6ed5aadbc8736337a63f70f012f191bc46a176937c5f3ebc5dfea7"),
}
TOLERANCE = {
    "fractional_epoch_offset_samples": 2e-9,
    "fractional_tracking_cfo_hz": 1e-6,
    **dict.fromkeys(
        ("fractional_exact_score", "fractional_control_score", "fractional_margin"), 5e-12
    ),
}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    from hashlib import file_digest

    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def checked(path, expected):
    if sha(path) != expected.removeprefix("sha256:"):
        raise ValueError(f"source or evidence seal changed: {path}")
    return path


def save(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, allow_nan=False, indent=2, sort_keys=True)
        stream.write("\n")


def inventory(old, field):
    """The measured library build inputs and sources included by the compiler."""
    from tools.pipeline_eval.variants import conditioned_cfo_bank, fine_search, refine_bank

    plan = read(PLANNING / "planning-lock.json")["variants"]["256"]
    sources = {
        name: checked(PLANNING / "build/planned-256" / name, digest)
        for name, digest in plan["generated"].items()
    }
    if plan["sha256"] != old["libraries"]["prepared"]["sha256"]:
        raise ValueError("prepared source does not bind the measured baseline binary")
    exact = read(CAPTURE_EXACT)
    for role in ("cfo", "fused"):
        if exact["libraries"][role]["sha256"] != old["libraries"][role]["sha256"]:
            raise ValueError(f"instrumented source does not bind the baseline {role} binary")
    frozen = old["fine_search"]["sources"]
    for module in (conditioned_cfo_bank, refine_bank):
        checked(module.SOURCE, exact["sources"][str(module.SOURCE)])
    fine = {
        path.name: checked(path, digest)
        for raw, digest in frozen.items()
        if (path := Path(raw)).suffix == ".c"
    }
    field_source = {
        raw: checked(Path(raw), digest) for raw, digest in field["build"]["sources"].items()
    }
    return {
        "accelerated": {
            "prepared": (
                [
                    plan["command"][0],
                    *plan["command"][1:12],
                    str(sources["capture_fft.c"]),
                    "-lfftw3f",
                    "-lm",
                ],
                [
                    sources[name]
                    for name in ("capture_fft.c", "folded_bank.c", "original_kernel_cache.h")
                ],
                [sources["capture_fft.c"]],
            ),
            "cfo": (
                ["cc", *conditioned_cfo_bank.FLAGS, str(conditioned_cfo_bank.SOURCE)],
                [conditioned_cfo_bank.SOURCE],
                [conditioned_cfo_bank.SOURCE],
            ),
            "fused": (
                ["cc", *refine_bank.FLAGS, str(refine_bank.SOURCE), "-lm"],
                [refine_bank.SOURCE],
                [refine_bank.SOURCE],
            ),
            "fine": (
                ["cc", *fine_search.FLAGS, "-mavx2", str(fine["fine_batch.c"]), "-lm"],
                [fine["fine_batch.c"], fine["fine_search.c"]],
                [fine["fine_batch.c"]],
            ),
        },
        "portable": {
            "portable_field": (
                field["build"]["command"][:-2],
                list(field_source.values()),
                [p for p in field_source.values() if p.suffix == ".c"],
            ),
        },
    }, sources["fftw.wisdom"]


def dependencies(binary):
    text = subprocess.check_output(["readelf", "-d", binary], text=True)
    return sorted(re.findall(r"\(NEEDED\).*?\[(.+?)\]", text))


def prepare(out, baseline, portable):
    sources = {"accelerated": baseline, "portable": portable}
    locks = {role: read(work / "source-lock.json") for role, work in sources.items()}
    a, b = locks.values()
    if (
        a["recording"] != b["recording"]
        or a["producer"] != b["producer"]
        or a["case"]["id"] != "DS26-0020"
    ):
        raise ValueError("matched work must share the signed DS26 source and producer")
    checked(PROTOCOL, PROTOCOL_SHA)
    out.mkdir(mode=0o755)
    plan, wisdom = inventory(a, b)
    info = dict(protocol_sha256=PROTOCOL_SHA, visits=VISITS, wisdom=str(wisdom), arms={})
    for role in sources:
        dest = out / role
        dest.mkdir(mode=0o777)
        dest.chmod(0o777)
        libraries = {}
        for name, (cmd, paths, units) in plan[role].items():
            binary = dest / (name + ".so")
            command = [*cmd, "--coverage", "-o", str(binary)]
            subprocess.run(
                command, env=os.environ | {"TMPDIR": str(dest)}, cwd=dest, check=True, timeout=50
            )
            sealed = locks[role]["libraries"][name]
            original = checked(Path(sealed["path"]), sealed["sha256"])
            libraries[name] = dict(
                release=str(original),
                release_sha256=sha(original),
                release_bytes=original.stat().st_size,
                needed=dependencies(original),
                command=command,
                coverage=str(binary),
                sources={str(path): sha(path) for path in sorted(paths)},
                translation_units=[str(path) for path in sorted(units)],
            )
        work = sources[role]
        info["arms"][role] = dict(
            work=str(work), lock_sha256=sha(work / "source-lock.json"), libraries=libraries
        )
    save(out / "plan.json", info)
    return info


class Trace:
    def __init__(self, producer, checkout):
        self.root = (str(producer) + "/", str(checkout) + "/")
        self.events = {}
        self.foreign = set()

    def __call__(self, frame, event, _):
        if event != "call":
            return None
        code = frame.f_code
        path = code.co_filename
        if path.startswith(self.root) and not path.startswith(str(__file__)):
            key = path, code.co_qualname, code.co_firstlineno
            lines = self.events.setdefault(key, set())

            def line(inner, name, _):
                if name == "line":
                    lines.add(inner.f_lineno)
                return line

            return line
        package = frame.f_globals.get("__name__", "").split(".")[0]
        if package in ("numpy", "pydantic", "zstandard", "ctypes"):
            self.foreign.add(package)
        return None

    def records(self):
        return [
            dict(path=p, name=n, definition=d, lines=sorted(ls))
            for (p, n, d), ls in sorted(self.events.items())
            if ls
        ]


@contextmanager
def traced(producer, checkout):
    trace = Trace(producer, checkout)
    old = sys.gettrace()
    sys.settrace(trace)
    try:
        yield trace
    finally:
        sys.settrace(old)


def decode(lock):
    from leo.storage import short_window
    from tools.pipeline_eval.qualification import capture_whole as capture

    member, verified = short_window.ShortWindowReader._member, []

    def stream(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return capture.resources.AuthenticatedMember(path, size, digest, verified)
        return member(reader, name, size, digest)

    with patch.object(short_window.ShortWindowReader, "_member", stream):
        source = capture.open_span(lock, 0, 0, max(VISITS) + 1)
        selected = {w.sequence: w for w in source.windows() if w.sequence in VISITS}
    if len(verified) != 1 or selected.keys() != VISITS.keys():
        raise ValueError("failed to close the selected signed chunk")
    for visit, window in selected.items():
        if (
            window.iq_sha256 != "sha256:" + VISITS[visit][2]
            or window.acquisition["global_visit"] != visit
        ):
            raise ValueError("selected physical samples differ from fixed roster")
    return selected, source.receiver_ids, verified[0]


def worker(folder, role, mode):
    from leo.analysis.starlink import acquisition
    from tools.pipeline_eval import original_receiver as original
    from tools.pipeline_eval.qualification import capture_whole as capture
    from tools.pipeline_eval.qualification.full_v5_check import _from_production, _probe

    plan = read(folder / "plan.json")
    config = plan["arms"][role]
    lock = read(checked(Path(config["work"]) / "source-lock.json", config["lock_sha256"]))
    libraries = {name: Path(v[mode]) for name, v in config["libraries"].items()}
    producer, checkout = Path(lock["producer"]), Path.cwd()
    with traced(producer, checkout) as decode_trace:
        windows, receivers, compressed_bytes = decode(lock)
    policy = capture.policy_for(lock)
    setup_trace, rows, visit_traces = None, {}, []
    with ExitStack() as stack:
        with traced(producer, checkout) as setup_trace:
            if role == "accelerated":
                from tools.pipeline_eval.qualification.capture_detector_replay import (
                    scan_capture_window,
                )
                from tools.pipeline_eval.variants import fine_batch
                from tools.pipeline_eval.variants.original_kernel import PersistentGrid

                grid = PersistentGrid(libraries["prepared"])
                fine = fine_batch.FineBatch(libraries["fine"], acquisition)
                if not fine.compatible:
                    raise ValueError("instrumentation failed the deployed arithmetic sentinel")
                stack.enter_context(original.peak_selector_for(lock))
                stack.enter_context(fine.route())
                stack.enter_context(capture.exact.refiners(libraries))
                stack.enter_context(grid.route(acquisition, capture.exact.starts.screen_module()))
                stack.callback(grid.clear_cache)
            else:
                from leo.scanner.fast_scan_analysis import analyze_window
                from tools.pipeline_eval.variants.portable_field import Detector

                detector = stack.enter_context(
                    Detector(libraries["portable_field"], lock["capture"]["edge"])
                )

                def scan_capture_window(window, lanes, policy):
                    status = analyze_window(window, lanes, None, policy, detector=detector)
                    return status, [
                        _probe(window, row.receiver_id, map(_from_production, row.candidates))
                        for row in status.receivers
                    ]

        for visit, window in windows.items():
            with traced(producer, checkout) as trace:
                status, probes = scan_capture_window(window, receivers, policy)
            groups = grid.calls if role == "accelerated" else detector.attempts
            expected_groups, expected_positive, _ = VISITS[visit]
            positives = sum(
                any(c["passed_fractional_margin_gate"] for c in p["candidates"]) for p in probes
            )
            if (len(groups), positives) != (
                expected_groups,
                expected_positive,
            ) or status.status != "processed":
                raise ValueError("matched visit changed gate or genuine retry classification")
            rows[visit] = dict(probes=probes, groups=groups.copy())
            if role == "accelerated":
                if not all(g["applied"] for g in groups):
                    raise ValueError("previous accelerated path fell back before its coarse grid")
                grid.calls.clear()
            visit_traces.append(
                dict(visit=visit, trace=trace.records(), external=sorted(trace.foreign))
            )
    external_maps = sorted(
        {
            line.rsplit(maxsplit=1)[-1]
            for line in Path("/proc/self/maps").read_text().splitlines()
            if "fftw" in line or "pocketfft" in line
        }
    )
    return dict(
        role=role,
        mode=mode,
        rows=rows,
        selected_bytes=compressed_bytes,
        decode=decode_trace.records(),
        setup=setup_trace.records(),
        visits=visit_traces,
        external_maps=external_maps,
    )


def compare(a, b):
    if a.keys() != b.keys():
        raise ValueError("visit coverage differs")
    maxima = dict.fromkeys(TOLERANCE, 0.0)
    counts = dict(visits=len(a), probes=0, candidates=0, positive=0)
    for v, one in a.items():
        for p, q in zip(one["probes"], b[v]["probes"], strict=True):
            if {k: x for k, x in p.items() if k != "candidates"} != {
                k: x for k, x in q.items() if k != "candidates"
            }:
                raise ValueError(f"physical probe metadata changed on {v}")
            counts["probes"] += 1
            for c, d in zip(p["candidates"], q["candidates"], strict=True):
                counts["candidates"] += 1
                counts["positive"] += c["passed_fractional_margin_gate"]
                for k, value in c.items():
                    if k in TOLERANCE:
                        delta = abs(value - d[k])
                        if delta > TOLERANCE[k]:
                            raise ValueError(f"{k} differs beyond tolerance at visit {v}")
                        maxima[k] = max(maxima[k], delta)
                    elif value != d[k]:
                        raise ValueError(f"{k} differs at visit {v}")
    return dict(counts=counts, maximum_delta=maxima)


def gcov(folder, role, libraries):
    dest = folder / role
    built = {path: digest for lib in libraries.values() for path, digest in lib["sources"].items()}
    results = {
        name: dict(
            physical_lines=len(checked(Path(name), digest).read_bytes().splitlines()),
            functions={},
            lines=set(),
            executable=set(),
        )
        for name, digest in built.items()
    }
    command = ["gcov", "--json-format", *map(str, sorted(dest.glob("*.gcda")))]
    subprocess.run(command, cwd=dest, check=True, capture_output=True, text=True)
    external = set()
    for zipped in sorted(dest.glob("*.gcov.json.gz")):
        with gzip.open(zipped, "rt") as stream:
            data = json.load(stream)
        for file in data["files"]:
            name = file["file"]
            if not Path(name).is_absolute():
                name = str((Path(data["current_working_directory"]) / name).resolve())
            if name not in results:
                if Path(name).is_relative_to("/usr"):
                    external.add(name)
                    continue
                raise ValueError(f"unexpected executed C source outside pinned closure: {name}")
            row = results[name]
            row["executable"].update(x["line_number"] for x in file["lines"])
            row["lines"].update(x["line_number"] for x in file["lines"] if x["count"] > 0)
            for item in file["functions"]:
                key = item["name"]
                row["functions"][key] = row["functions"].get(key, 0) + item["execution_count"]
    for row in results.values():
        for name in ("lines", "executable"):
            row[name] = sorted(row[name])
    return dict(sources=results, external_headers=sorted(external))


def published(work):
    found = {}
    with (work / "cpu-0.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["kind"] == "chunk":
                if (row["segment"], row["first"], row["stop"]) != (0, 0, 64):
                    raise ValueError("recorded run did not close the selected signed chunk")
                break
            if row["kind"] == "visit" and row["visit"] in VISITS:
                if row["iq_sha256"] != "sha256:" + VISITS[row["visit"]][2]:
                    raise ValueError("recorded run did not use the selected physical CI16")
                found[str(row["visit"])] = {"probes": row["probes"]}
        else:
            raise ValueError("recorded run ended before the selected chunk closed")
    return found


def finish(out):
    plan = read(out / "plan.json")
    live = {
        (role, mode): read(out / f"{role}-{mode}.json")["rows"]
        for role in plan["arms"]
        for mode in ("release", "coverage")
    }
    coverage = {role: gcov(out, role, entry["libraries"]) for role, entry in plan["arms"].items()}
    verification = {
        "matched_release": compare(live["accelerated", "release"], live["portable", "release"]),
        "coverage_vs_release": {
            role: compare(live[role, "release"], live[role, "coverage"]) for role in plan["arms"]
        },
        "release_vs_published": {
            role: compare(live[role, "release"], published(Path(entry["work"])))
            for role, entry in plan["arms"].items()
        },
    }
    save(out / "c-coverage.json", coverage)
    save(out / "verification.json", verification)


def run(out, old, field, cpu):
    plan = prepare(out, old, field)
    for role, entry in plan["arms"].items():
        lock = read(Path(entry["work"]) / "source-lock.json")
        checkout = RELEASE if role == "accelerated" else ROOT
        for mode in ("release", "coverage"):
            command = [
                "taskset",
                "-c",
                str(cpu),
                "sudo",
                "-n",
                "-u",
                "leo",
                "--",
                "env",
                f"PYTHONPATH={lock['producer']}:{checkout}",
                "OPENBLAS_NUM_THREADS=1",
                "OMP_NUM_THREADS=1",
                str(checked(Path(lock["python"]), lock["python_sha256"])),
                "-Bu",
                str(Path(__file__)),
                "worker",
                str(out),
                role,
                mode,
            ]
            result = json.loads(subprocess.check_output(command, cwd=checkout, timeout=70))
            save(out / f"{role}-{mode}.json", result)
    finish(out)


def main():
    if sys.argv[1:2] == ["worker"]:
        print(json.dumps(worker(Path(sys.argv[2]), *sys.argv[3:]), allow_nan=False))
        return
    if sys.argv[1:2] == ["finish"]:
        finish(Path(sys.argv[2]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("out", "baseline", "portable"):
        parser.add_argument("--" + argument, required=True, type=lambda p: Path(p).resolve())
    parser.add_argument("--cpu", type=int, default=0)
    args = parser.parse_args()
    if args.out.is_relative_to("/mnt/qnap01"):
        raise ValueError("choose local scratch outside QNAP")
    run(args.out, args.baseline, args.portable, args.cpu)


if __name__ == "__main__":
    main()
