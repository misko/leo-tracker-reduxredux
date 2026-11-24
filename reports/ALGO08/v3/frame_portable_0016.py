"""Admit a single standard-format DS30-0016 combined publication."""

import argparse
from pathlib import Path
import shutil
import subprocess

from visit_frame_raw_0016 import AUTHORITY_PIN, HERE, WRITER, WRITER_PIN, checked, digest, new_source, read, references, resident


ROOT = HERE.parents[2]
PAIR = Path("/dev/shm/leo-v3-visit-frame-0016-raw-result02")
PAIR_PIN = "8a084d107e3854bae407836943a1cf21998ff1ca9690ab69bdefdcce4203d6d2"
PRODUCER_CLOCK_PIN = "ea78ecc07d20b61b5f3473d08f849efe178df093c53c095fa9a7a0d6152993f2"
LIBRARIES = ("--short-binary", "--geographic-library", "--regional-track-library", "--frontier-block-library")


def candidate_command(old, root, portable):
    if (Path(old[5]).name != "exact_named_raw.py" or old.count("--cairo-six-sheets") != 1
            or not {"--visit-frame-custody", "--visit-frame-custody-sha256", "--history-risk-route"} <= set(old)
            or any(arg.startswith(("--cairo-residual", "--portable-orbit", "--strict-packed")) for arg in old)):
        raise ValueError("Expected the qualified new-archive selective six-sheet command")
    argv = list(old)
    argv[5] = str(HERE/"frame_portable_scene.py")
    argv[argv.index("--output")+1] = str(root/"candidate")
    argv[argv.index("--cairo-six-sheets")] = "--cairo-residual-layout"
    return argv + portable.arguments()


def eligible_pair(previous):
    from exact_named_raw import staged_path

    pair = checked(staged_path(PAIR/"score-qualified.json"), PAIR_PIN)
    admission = pair["admission"]
    if (not pair["qualified"] or not pair["within_new"] or not pair["cross_manifest"]
            or not all((*pair["within_new"].values(), *pair["cross_manifest"].values()))
            or pair["measured_children"]["frames"]["command"] != admission["commands"]["frames"]
            or pair["measured_children"]["ordinary"]["command"] != admission["commands"]["ordinary"]
            or pair["historical_named"] != previous["reused_stock"]):
        raise ValueError("The authentic within-encoding frame pair must qualify first")
    return pair


def runtime_pins():
    import exact_named_raw
    from exact_named_route import SOURCES
    from history_cairo_render import RESIDUAL_SOURCES

    paths = {*SOURCES, *(HERE/name for name in RESIDUAL_SOURCES + exact_named_raw.RISK_SOURCES),
             *(HERE/name for name in ("frame-portable-0016-protocol.md", "frame_portable_scene.py", Path(__file__).name,
                                        "exact_named_raw.py", "unified_short_bootstrap.py", "visit_frame_input.py",
                                        "visit_frame_reader.py", "named_hybrid_baseline.py", "empty_bootstrap.py"))}
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(paths)}


def preflight(root):
    from aperture_trial import write
    from combined_raw_trial import PRODUCER, checked_producer
    from dense_geographic_trial import host
    from empty_bootstrap import clock, now
    from exact_named_raw import parser, portable_binding, staged_path
    from leo.operations.tle_archive import TleArchiveReader
    from reports.ALGO08.v3.history_risk_0016_cairo import measured_reference
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    common_start = now()
    if root.parent != Path("/dev/shm") or root.exists():
        raise ValueError("Use a fresh private tmpfs scope")
    previous = references()
    pair = eligible_pair(previous)
    machine = host()
    old = pair["admission"]
    request = previous["admission"]["request"]
    writer, _, plan, wavepaths = new_source(WRITER, AUTHORITY_PIN, WRITER_PIN)
    if (machine != old["machine"] or plan != old["source"] or writer != old["writer_receipt"]
            or old["archive"] != request["archive"] or old["cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or digest(staged_path(Path(request["region"]))) != "sha256:"+request["offer_sha256"]):
        raise ValueError("The original offer, new recording custody, cutoff or host changed")
    archive = staged_path(Path(request["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (archive_identity(archive) != request["archive"] or len(refs) != 46
            or any(ref.collected_utc_ns >= request["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Expected exactly the enrolled causal archive")
    tlepaths = [staged_path(ref.path, root=archive) for ref in refs]
    old_frames = old["commands"]["frames"]
    command = candidate_command(old_frames, root, PRODUCER)
    args = parser().parse_args(command[6:])
    if str(args.recording) != plan["recording"] or args.archive != archive or args.region != Path(request["region"]):
        raise ValueError("The published combined arguments do not retain the enrolled assignments")
    old_raw = previous["admission"]["reference"]
    original = measured_reference(Path(old_raw["root"]), Path(old_raw["score"]), old_raw["sha256"])
    libraries = original["admission"]["candidate_libraries"]
    for flag in LIBRARIES:
        entry = libraries[flag]
        if command[command.index(flag)+1] != entry["path"] or digest(Path(entry["path"])) != "sha256:"+entry["sha256"]:
            raise ValueError(f"The signed native library changed: {flag}")
    pins = runtime_pins()
    for name in ("visit_frame_input.py", "visit_frame_reader.py", "unified_short_bootstrap.py"):
        if pins[f"reports/ALGO08/v3/{name}"] != old["sources"][name]:
            raise ValueError(f"The qualified receiver source changed: {name}")
    revision = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(PAIR/"fonts", root/"fonts")
    shared = clock(common_start)
    start = now()
    wave_cache, tle_cache = resident(wavepaths), resident(tlepaths)
    indexpaths = [staged_path(path) for path in (PRODUCER.file, PRODUCER.file.parent/"artifact-bind.json")]
    index_cache = resident(indexpaths)
    build = checked(staged_path(PRODUCER.file.parent/"dense-export-clock.json"), PRODUCER_CLOCK_PIN)
    producer = checked_producer(request["cutoff_utc_ns"], {ref.sha256 for ref in refs})
    if (build["exit_code"] or not producer["overlapping_bodies"] or portable_binding(args, request["cutoff_utc_ns"]) is None):
        raise ValueError("Need the earlier published index, actual overlap and a causal accepted binding")
    ready = clock(start)
    write(root/"preflight.json", dict(revision=revision, source_pins=pins, machine=machine,
          prior_pair_sha256=PAIR_PIN, archive=request["archive"], authority_sha256=AUTHORITY_PIN, source=plan,
          offer_sha256=request["offer_sha256"], cutoff=request["cutoff_utc_ns"], command=command,
          writer_receipt_sha256=WRITER_PIN, custody=shared, candidate_ready=ready, producer=producer, producer_clock=build,
          native_libraries=libraries, wavepaths=list(map(str, wavepaths)), tlepaths=list(map(str, tlepaths)),
          indexpaths=list(map(str, indexpaths)), cached=dict(waveform=wave_cache, catalogue=tle_cache, index=index_cache)))


def seal(root):
    return {str(path.relative_to(root)): digest(path) for path in sorted(root.rglob("*"))
            if path.is_file() and path.relative_to(root).parts[0] not in ("fonts", "tmp")
            and path.name not in ("prediction-seal.json", "result.json", "render-verification.json")}


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from raw_0016_best_trial import measure_mode

    pre = read(root/"preflight.json")
    if (host() != pre["machine"] or runtime_pins() != pre["source_pins"]
            or any((root/name).exists() for name in ("candidate", "candidate-clock.json", "prediction-seal.json"))):
        raise ValueError("The frozen runtime changed or the one raw opportunity is already spent")
    measure_mode(root, "candidate", pre["command"], environment_for(root), lambda: resident(pre["wavepaths"]), require_success=False)
    write(root/"causal-after.json", dict(tle=resident(pre["tlepaths"]), index=resident(pre["indexpaths"])))
    write(root/"prediction-seal.json", seal(root))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("preflight", "launch"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"preflight": preflight, "launch": launch}[args.action](args.root)
