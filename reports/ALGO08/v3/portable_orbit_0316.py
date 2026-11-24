"""Thrice isolated, signed 0306 archive build and medium 0316 saved transfer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
PRODUCER = Path("/dev/shm/leo-v3-raw-band-pair-0306-result02")
TARGET = Path("/dev/shm/leo-v3-final-0316-transfer-result02")
SCORE = Path("/dev/shm/leo-v3-final-0316-transfer-score02.json")
PRODUCER_SHA = "c8010b5930a476b496d299a547a85ec73d3cabad35864d14a76aae60a98e4f1b"
REQUEST_SHA = "c9be0ae39a59a69621f9b9a6f4062ea7e33d1ba1de05c394771001f1b26ce4b3"
TARGET_SEAL_SHA = "070a18b187737d20036fa0aa220664ce13872d3e785b0e8bed6367434a3c2b46"
SCORE_SHA = "a9b58b411f29e430e4df47829b3b15e95cf2c0d5d9ef80bed521a92b9e83647b"
ARTIFACT = "0306-orbit-index.bin"
ORDER = ("producer", "ordinary", "portable")


def distinct_sources(rows, cutoff):
    from historical_orbit_index import HOUR_NS

    unique = {}
    for row in sorted(rows):
        if not 0 <= cutoff-row.collected_utc_ns <= 72*HOUR_NS:
            raise ValueError("Original source roster reaches outside its signed causal interval")
        unique.setdefault(row.sha256, row)
    return unique


def chronology(earlier_cutoff, target_cutoff, earlier, target):
    if earlier_cutoff >= target_cutoff:
        raise ValueError("Prior signed admission must precede the target's acquisition")
    return sorted(earlier.keys() & target.keys())


def admission():
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    earlier = json.loads(checked(PRODUCER/"admission.json", PRODUCER_SHA))
    target = json.loads(checked(TARGET/"request.json", REQUEST_SHA))
    if (earlier["case"], target["case"]) != ("DS30-0306", "DS30-0316"):
        raise ValueError("The frozen producer or target request changed")
    inventories = []
    for root, digest, cutoff in (
        (PRODUCER/"tle", earlier["archive"]["sha256"], earlier["cutoff_utc_ns"]),
        (Path(target["local_archive"]["root"]), target["local_archive"]["snapshots_sha256"],
         target["causal_cutoff_utc_ns"]),
    ):
        if not root.resolve(strict=True).is_relative_to(Path("/dev/shm")):
            raise ValueError("The signed archive must already be staged in tmpfs")
        reader = TleArchiveReader(root)
        listed = reader.list_snapshots("space-track")
        membership = {row.path.name: row.sha256 for row in listed}
        if canonical_digest(membership) != digest:
            raise ValueError("Staged snapshot roster differs from the original signed acquisition")
        unique = distinct_sources(listed, cutoff)
        if any(not row.path.resolve(strict=True).is_relative_to(root) for row in unique.values()):
            raise ValueError("The authenticated source escaped its earlier archive")
        inventories.append((reader, unique, dict(root=str(root), archive_sha256=digest, cutoff_utc_ns=cutoff,
                            snapshot_count=len(listed), body_digests=sorted(unique),
                            distinct_bytes=sum(row.byte_size for row in unique.values()))))
    unique = [entry[1] for entry in inventories]
    own, future = [entry[2] for entry in inventories]
    intersect = chronology(own["cutoff_utc_ns"], future["cutoff_utc_ns"], *unique)
    if (len(unique[0]), len(unique[1]), len(intersect)) != (40, 40, 37):
        raise ValueError("Original earlier and target source overlap changed")
    return inventories[0][:2], dict(producer=own, target=future, overlap=intersect,
                                     producer_request_sha256=PRODUCER_SHA, target_request_sha256=REQUEST_SHA)


def producer(root):
    from historical_orbit_index import SourceIndex
    from portable_orbit_index import versions, write_index
    from portable_orbit_index_trial import begin, observed, settings, timing

    start = begin()
    _, native, _ = settings()
    from aperture_trial import write
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    (reader, sources), binding = admission()
    index, verify, parse = SourceIndex(), {}, {}
    read = observed(reader.read, verify)
    with batch_records(Path(native["library"])) as validation:
        step = begin()
        compatible = versions()
        version_time = timing(step)
        step = begin()
        with patch.object(installed, "parse_element_set_records", observed(installed.parse_element_set_records, parse)):
            for digest, snapshot in sources.items():
                index.catalogue(digest, read(snapshot))
        build = timing(step)
    step = begin()
    artifact = write_index(root/ARTIFACT, index, compatible) | timing(step)
    if verify["calls"] != len(sources) or validation["fallback"] or len(index.bodies) != len(sources):
        raise ValueError("The producer must verify and strictly parse all earlier unique source bodies")
    write(root/"producer.json", dict(binding=binding, artifact=artifact, compatibility=compatible,
          versions=version_time, build=build, verify_reads=verify, strict_parse=parse, native_validation=validation,
          input_blocks=getrusage(RUSAGE_SELF).ru_inblock, peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
          total=timing(start), original_waveform_calls=0, position_solves=0))


def work(root, mode, pin):
    from active_preparation_trial import bind_preparation
    from aperture_trial import write
    from empty_bootstrap import checked
    from historical_orbit_index import fingerprint, guarded_preparation
    from named_final_0316 import run_worker
    from portable_orbit_index import PortableSourceIndex, load_index, versions
    from portable_orbit_index_trial import begin, observed, timing

    job = TARGET/"request.json"
    checked(job, REQUEST_SHA)
    audit = {}

    def bind(ordinary, counters):
        def call(document, reader, config, **options):
            from leo.operations.tle_archive import TleArchiveReader
            from tools.pipeline_eval.variants import algo08_causal_reuse as installed

            if len(counters):
                raise ValueError("The original named-final candidate did not take one prepared input")
            start = begin()
            method = ordinary
            if mode == "portable":
                step = begin()
                compatible = versions()
                version_time = timing(step)
                artifact, load = load_index(root/ARTIFACT, pin, compatible)
                if artifact is None:
                    raise ValueError("Frozen cache did not activate: "+load["fallback"])
                counters.update(loading=load, compatibility=version_time, index_sha256=pin,
                                artifact_record_sources=len(artifact.bodies))
                index = PortableSourceIndex(artifact)
                method = guarded_preparation(ordinary, counters, index_factory=lambda: index)
            verify, parse = {}, {}
            with (patch.object(TleArchiveReader, "read", observed(TleArchiveReader.read, verify)),
                  patch.object(installed, "parse_element_set_records", observed(installed.parse_element_set_records, parse))):
                prepared = method(document, reader, config, **options)
            counters.update(active_preparation=timing(start), verified_original_reads=verify, strict_parse=parse)
            if mode == "portable":
                counters.update(index_counts=index.counts, retained_source_bytes=index.size())
            step = begin()
            counters["fingerprint"] = fingerprint(prepared)
            counters["fingerprinting"] = timing(step)
            return prepared
        return call

    with bind_preparation(bind, audit):
        run_worker(job, root/mode)
    usage = getrusage(RUSAGE_SELF)
    audit.update(peak_rss_kib=usage.ru_maxrss, process_input_blocks=usage.ru_inblock)
    write(root/f"{mode}-preparation.json", audit)


def score(root, output=None):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from regional_history_score import scientific

    admission = read(root/"binding.json")
    building = read(root/"producer.json")
    sealed = read(root/"artifact-seal.json")
    if (building["binding"] != admission or sealed["binding"] != admission
            or sealed["index_sha256"] != building["artifact"]["sha256"]):
        raise ValueError("Producer index was not sealed before the consumer pair")
    checked(root/"producer.json", sealed["producer_sha256"])
    checked(root/ARTIFACT, sealed["index_sha256"].removeprefix("sha256:"))
    historic = json.loads(checked(SCORE, SCORE_SHA))
    seal = json.loads(checked(TARGET/"prediction-seal.json", TARGET_SEAL_SHA))
    checked(TARGET/"candidate/joint-research-receipt.json", seal["candidate/joint-research-receipt.json"])
    original = scientific(TARGET/"candidate")
    original_worker = read(TARGET/"candidate/saved-0316-worker.json")
    original_media = artifacts(TARGET/"candidate", original_worker["receipt"])
    pair = {}
    for mode in ORDER[1:]:
        current = root/mode
        clock = read(root/f"{mode}.clock.json")
        work = read(current/"saved-0316-worker.json")
        trace = read(current/"joint-research-receipt.json")
        finish = read(current/"final-fit-options.json")
        active = read(root/f"{mode}-preparation.json")
        product = artifacts(current, work["receipt"])
        if (clock["exit_code"] or not work["no_waveform"] or work["handoffs"] != 1
                or work["receipt"]["decision"] != "complete" or not work["graph"]["enabled"]
                or not finish["named_survivor_finish"]["paid_final_fit"]
                or scientific(current) != original or product["images"] != original_media["images"]
                or product["path"] != original_media["path"]):
            raise ValueError(f"{mode} changed the exact original research publication")
        pair[mode] = dict(process=clock, active=active, solve=trace["solve"], route=finish,
                          publication={key: trace[key] for key in ("publication_cpu_s", "publication_elapsed_s")},
                          native_record_parser=work["receipt"]["tle_records"],
                          stage_clocks={k: v for k, v in trace["route_details"].items() if k.endswith("_clocks")},
                          terminal_sha256=work["receipt"]["terminal_sha256"])
    ordinary, portable = (pair[mode]["active"] for mode in ORDER[1:])
    observed = portable["index_counts"]
    attempt, = portable["attempts"]
    if (portable["fingerprint"] != ordinary["fingerprint"] or observed["sidecar_hit_bodies"] != len(admission["overlap"])
            or observed["invalid_bodies"] or observed["cold_bodies"] != 3 or attempt["fallback"]
            or portable["index_sha256"] != building["artifact"]["sha256"]
            or pair["ordinary"]["native_record_parser"] != pair["portable"]["native_record_parser"]
            or pair["portable"]["native_record_parser"]["fallback"]
            or portable["verified_original_reads"]["calls"] != ordinary["verified_original_reads"]["calls"]
            or portable["strict_parse"]["calls"] != ordinary["strict_parse"]["calls"]):
        raise ValueError("Causal cache handoff activated without exact matching preparation inputs and counts")
    write(output or root/"result.json", dict(binding=admission, historical_named_and_research=historic["clocks"],
          historical_geographic=historic["geographic"], historical_score_sha256=SCORE_SHA,
          producer=building, producer_process=read(root/"producer.clock.json"), runs=pair,
          scientific=original, waveform_reads=0))


def launch(root):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import RELEASE, read, write
    from empty_bootstrap import checked
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs root")
    _, binding = admission()
    checked(TARGET/"prediction-seal.json", TARGET_SEAL_SHA)
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root/name).mkdir()
    for font in (TARGET/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/font.name).write_bytes(font.read_bytes())
    write(root/"binding.json", binding)
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    pin = None
    for mode in ORDER:
        command = ["/usr/bin/timeout", "--kill-after=2s", "60s", RELEASE/"venv/bin/python", "-IB",
                   __file__, mode, root]
        if mode == "portable":
            command.extend(("--pin", pin))
        clock = measure(command, env, root/mode)
        write(root/f"{mode}.clock.json", clock)
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])
        if mode == "producer":
            built = read(root/"producer.json")
            pin = built["artifact"]["sha256"]
            checked(root/ARTIFACT, pin.removeprefix("sha256:"))
            write(root/"artifact-seal.json", dict(index_sha256=pin, binding=binding,
                producer_sha256=sha256((root/"producer.json").read_bytes()).hexdigest()))
    score(root)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=(*ORDER, "launch", "admit", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin")
    parser.add_argument("--score-to", type=Path)
    args = parser.parse_args()
    if args.action == "admit":
        from empty_bootstrap import load_runtime

        load_runtime()
        print(json.dumps(admission()[1], sort_keys=True))
    elif args.action == "score":
        from empty_bootstrap import load_runtime

        load_runtime()
        score(args.root, output=args.score_to)
    elif args.action in ORDER[1:]:
        work(args.root, args.action, args.pin)
    else:
        {"launch": launch, "producer": producer}[args.action](args.root)
