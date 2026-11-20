"""Run real phase-release fits from four substituted visits per archival capture."""

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import cavity_runtime
from ..__main__ import encoded, local_output, save_json, write
from ..variants.selective_capture import visit_pairs
from . import capture_fft_trial as detector
from . import cavity_payload_transfer as receiver
from .input_factor_bridge import BULK, _load_case, _sha, check, read
from .selective_capture_trial import archive_context, digest

REPORT = detector.REPORT
PINS = {"DS26-0036": 4, "DS29-0174": 5}
CONTROL = "capture_fft_installed_factors"
MIX = "capture_fft_partial_iq"
PROFILE = "phase-release"


def substitute(original, indexed):
    pairs = dict(visit_pairs(original["source"]["probes"]))
    if not indexed or not indexed.keys() <= pairs.keys():
        raise ValueError("raw substitutions do not bind to complete archived stereo visits")
    for visit, (baseline, candidate) in indexed.items():
        if tuple(baseline) != pairs[visit] or len(candidate) != 2:
            raise ValueError("installed raw control differs from its frozen native probes")
        for saved, replacement in zip(baseline, candidate, strict=True):
            if any(replacement[k] != v for k, v in saved.items() if k != "candidates"):
                raise ValueError("partial substitution changed acquisition or receiver authority")
    probes = []
    for visit, both in pairs.items():
        probes.extend(indexed[visit][1] if visit in indexed else both)
    return probes, dict(
        total_visits=len(pairs),
        substituted_visits=sorted(indexed),
        untouched_visits=len(pairs) - len(indexed),
        changed_factor_visits=sum(tuple(pair[1]) != pairs[v] for v, pair in indexed.items()),
    )


def prepare(work):
    source_path = REPORT / "source-lock.json"
    detector_source = read(source_path)
    detector.sealed(detector_source)
    lib = Path(detector_source["library"])
    bundle = work / PROFILE
    cavity_runtime.install(bundle, profile=PROFILE)
    source_files = {
        str(path.relative_to(bundle)): _sha(path)
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }
    scientific = cavity_runtime.release_files(cavity_runtime.RELEASE, PROFILE)
    if any((bundle / name).read_bytes() != value for name, value in scientific.items()):
        raise ValueError("the position worker differs from the released phase profile")
    jobs = {}
    traces = {}
    for ident in PINS:
        case = _load_case(ident)
        home = work / ident
        home.mkdir()
        trace = REPORT / f"{ident}.json.gz"
        measurements = json.loads(gzip.decompress(trace.read_bytes()))
        check(lib, measurements["candidate_source_sha256"])
        traces[trace.name] = _sha(trace)
        masks = detector_source["cases"][ident]["roster"].values()
        if {r["visit"] for r in measurements["captures"]} != {r["visit"] for r in masks}:
            raise ValueError("the FFT evidence differs from its independent visit roster")
        archived = BULK / case["native"]["path"]
        original_sha = check(archived, case["native"]["sha256"])
        original = read(archived)
        indexed = {
            row["visit"]: (pair["installed"]["probes"], pair["fft"]["probes"])
            for row in measurements["captures"]
            if (pair := row["rows"][0])["installed"]["status"] == "processed"
        }
        if any(
            pair["installed"]["status"] != pair["fft"]["status"]
            for row in measurements["captures"]
            for pair in row["rows"]
        ):
            raise ValueError("coarse replacement altered original capture status")
        probes, audit = substitute(original, indexed)
        mix = dict(
            original_native_sha256=original_sha,
            candidate_library_sha256=_sha(lib),
            partial_iq=True,
            recomputed_visits=len(indexed),
            detector_trace_sha256=traces[trace.name],
            **audit,
        )
        identity = digest(mix)
        document = dict(
            original,
            source=dict(
                original["source"], probes=probes, analysis_manifest_sha256=("sha256:" + identity)
            ),
            provenance=dict(
                original["provenance"],
                fft_partial_replay=mix,
                run_id="fft-partial-iq-" + identity[:32],
            ),
        )
        native = home / "partial.native.json"
        write(native, encoded(document))
        row, config, archive, history = archive_context(case, home)
        jobs[ident] = dict(
            profile=PROFILE,
            native=str(native),
            stock=str(archived),
            track=str(config),
            archive=str(archive),
            history=history,
            binding=dict(row, native_sha256=_sha(native), original_native_sha256=original_sha),
            audit=audit,
        )
    sources = (Path(__file__), Path(receiver.__file__), receiver.OBSERVER)
    save_json(
        REPORT / "fit-lock.json",
        dict(
            sources={str(p): _sha(p) for p in sources},
            phase_release_files=source_files,
            jobs=jobs,
            cpus=PINS,
            detector_source_sha256=_sha(source_path),
            traces=traces,
        ),
    )


def run(work):
    lock = read(REPORT / "fit-lock.json")
    bundle = work / PROFILE
    for filename, want in lock["phase_release_files"].items():
        check(bundle / filename, want)
    for filename, want in lock["sources"].items():
        check(Path(filename), want)
    check(REPORT / "source-lock.json", lock["detector_source_sha256"])
    for filename, want in lock["traces"].items():
        check(REPORT / filename, want)

    def recording(ident):
        prep = lock["jobs"][ident]
        row = prep["binding"]
        proof = []
        for method, field, sha in (
            (MIX, "native", row["native_sha256"]),
            (CONTROL, "stock", row["original_native_sha256"]),
        ):
            path = Path(prep[field])
            check(path, sha)
            binding = dict(row, native_sha256=sha, detector_method=method)
            binding["input_sha256"] = digest(binding)
            job = binding, path, Path(prep["track"]), Path(prep["archive"]), prep["history"]
            result = receiver.capped(work / "attempts" / method, work, job, PROFILE, PINS[ident])
            result["method"] = method
            proof.append(result)
            save_json(REPORT / f"{ident}-{method}.json", result)
        return proof

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = [row for pair in pool.map(recording, PINS) for row in pair]
    output = REPORT / "fit-results.json"
    save_json(output, rows)
    save_json(
        REPORT / "fit-result-lock.json",
        {name: _sha(REPORT / name) for name in ("fit-lock.json", output.name)},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    (prepare if args.action == "prepare" else run)(local_output(args.work))
