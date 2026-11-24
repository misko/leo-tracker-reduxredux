"""Validate one original physical 20/8 history+Cairo strict-packed handoff."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from reports.ALGO08.v3 import history_risk_0016_cairo as cairo
from reports.ALGO08.v3 import history_risk_0016_raw as original


REFERENCE = Path("/dev/shm/leo-v3-history-risk-0016-raw-result02")
RAW_SCORE = Path("/dev/shm/leo-v3-history-risk-0016-raw-score02.json")
RAW_PIN = "920456558c3b3ed29fcad552ee9b369b1b5ca0fda456211b85c6ee73748f662f"
CAIRO_SCORE = Path("/dev/shm/leo-v3-history-risk-0016-cairo-score01.json")
CAIRO_PIN = "b340a594fadae0b871c42d31ac269efe2cfe0a34d26089038c739e4bb8822e39"
CAIRO_ROOT = Path("/dev/shm/leo-v3-history-risk-0016-cairo-result01")
CAIRO_BOOTSTRAP = "b403ef121ad2dd8bff1269133240d3134c041b1ca16002d9735f29179eac4758"
SOURCES = ("strict-cairo-0016-protocol.md", Path(__file__).name, "history_risk_0016_raw.py", "history_risk_0016_cairo.py",
           "north_strict_read.py", "packed_combined_input.py", "seekable_member.py", "seekable_eight_raw.py", "ci16_packing.c")
DERIVATIVE_LIMIT = 1_400_000_000


def pins():
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}


def quote(command, output, packed):
    command = list(command)
    if (Path(command[5]).name != "exact_named_raw.py" or "--cairo-six-sheets" not in command
            or "--history-risk-route" not in command or "--strict-packed-eight" in command):
        raise ValueError("Expected the actual qualified original-input history and Cairo command")
    command[5] = str(HERE/"exact_named_raw.py")
    command[command.index("--output")+1] = str(output)
    return command + ["--strict-packed-eight", "--packed-ci16-map", packed["map"],
                      "--packed-ci16-map-sha256", packed["map_sha256"], "--packed-ci16-codec", packed["codec"]]


def source_inputs(signed, stage):
    """Conversion addresses only the verified tmpfs subdirectory, never the backing path."""
    recording = stage/original.RECORDING.name
    return dict(recording=str(recording), compressed_bytes=original.WAVEFORM_BYTES, issued=original.ISSUED,
                manifests=[dict(path=str(recording/row["relative"]), digest=row["signed_sha256"])
                           for row in signed["files"] if row["kind"] == "manifest"])


def controls():
    from empty_bootstrap import checked

    raw = cairo.measured_reference(REFERENCE, RAW_SCORE, RAW_PIN)
    earlier = cairo.checked_json(CAIRO_SCORE, CAIRO_PIN)
    same = dict(root=str(REFERENCE), score=str(RAW_SCORE), sha256=RAW_PIN)
    prior_raw = json.loads(checked(CAIRO_ROOT/"candidate/unified-short-bootstrap.json", CAIRO_BOOTSTRAP))
    proof = CAIRO_ROOT/"prediction-seal.json"
    if (not earlier["qualified"] or not all(earlier["checks"].values()) or earlier["admission"]["reference"] != same
            or earlier["pair_sha256"] != RAW_PIN or earlier["optional_process"]["clock"]["exit_code"]
            or earlier["reused_stock"] != raw["runs"]["stock"]["process"]["clock"]
            or earlier["native"]["digest"] != raw["runs"]["candidate"]["digest"]
            or earlier["admission"]["request"] != raw["admission"]["request"]
            or earlier["seal_sha256"] != sha256(proof.read_bytes()).hexdigest()
            or original.read(proof) != original.roster(CAIRO_ROOT)
            or prior_raw.get("packed_ci16_input") is not None or prior_raw["native_sha256"] != earlier["native"]["digest"]):
        raise ValueError("Require both the scored ordinary pair and the unchanged original-input Cairo publication")
    for key in ("science", "adapters", "renderer_sources"):
        original.bundle_sha(ROOT, earlier["admission"][key])
    return raw, earlier, prior_raw


def extents_after(stage, signed, expected, *, canonical=False):
    from eight_ms_0107_pair import verified_scope
    from guarded_cfo_0016_stage import cache_states, fully_resident

    current = original.readiness(stage, signed)
    if not current["ready"] or current["files"] != expected["files"]:
        raise ValueError("The signed input extent changed")
    if canonical:
        verified_scope(stage/original.RECORDING.name, original.RECORDING)
    actual = original.stage_files(signed)
    if not canonical:
        actual = {kind: [(stage/original.RECORDING.name/Path(path).relative_to(original.RECORDING), size, pin)
                         for path, size, pin in rows] for kind, rows in actual.items()}
    scopes = cache_states({kind: [(Path(path), size, pin) for path, size, pin in rows] for kind, rows in actual.items()})
    if not fully_resident(scopes):
        raise ValueError("Require all complete physical members and indexes resident")
    return scopes["payload"] | {"index_cache": scopes["index"]}


def prepared_setup(root, config, folders, codec, expected):
    """Independently bind each converted root before starting the candidate clock."""
    from empty_bootstrap import checked
    from north_strict_read import resident_packed
    from packed_combined_input import member_map
    from seekable_eight_raw import PREFIX
    from seekable_member import open_member

    mapping = Path(config["map"])
    codec_pin, entries = member_map(checked(mapping, config["map_sha256"][7:]), strict_eight=True)
    checked(Path(config["codec"]), codec_pin[7:])
    expected_map = {(row["binding"]["manifest_sha256"], row["binding"]["chunk_index"]):
                    (row["binding"]["directory"], row["binding"]["seek_sha256"]) for row in expected}
    if entries != expected_map or len(entries) != 13 or mapping.parent != root/"conversion":
        raise ValueError("The archive map must describe all independently verified derivative members")
    for folder, row in zip(folders, expected, strict=True):
        bound = row["binding"]
        with open_member(folder, bound["seek_sha256"], codec=codec, prefix_samples=PREFIX) as evidence:
            if (evidence.manifest_sha256 != bound["manifest_sha256"] or evidence.chunk.model_dump(mode="json") != row["original"]
                    or evidence.counts()["payload_bytes"] != 0):
                raise ValueError("The derivative metadata is not the original signed member")
    return resident_packed(mapping.parent, folders, codec)


def run(root, stage):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import checked, clock, now
    from exact_named_raw import parser, staged_path
    from guarded_stage_checkpoint import staging_lock
    from leo.operations.tle_archive import TleArchiveReader
    from north_strict_read import transform, resident_packed
    from raw_0016_best_trial import measure_mode
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    start = now()
    machine = host()
    staged_path(root.parent)
    if (stage != original.STAGE or root.parent != original.TMPFS or root.exists()
            or shutil.disk_usage(root.parent).free < DERIVATIVE_LIMIT + 6*2**30):
        raise ValueError("Use the complete approved stage, fresh private tmpfs and sufficient shared headroom")
    signed = original.enrolled()
    stock, raw_cairo, _ = controls()
    req = raw_cairo["admission"]["request"]
    with staging_lock(original.STAGING_LOCK):
        ready = original.readiness(stage, signed)
        if not ready["ready"] or ready["files"] != raw_cairo["admission"]["stage"]["files"]:
            raise ValueError("Current 0016 custody differs from the completed original-input Cairo run")
        custody = original.require_custody(stage, signed)
        if custody != raw_cairo["admission"]["custody_sha256"] or machine != raw_cairo["admission"]["machine"]:
            raise ValueError("The named comparison used a different source or host")
        original.authenticate_sidecars(stage, signed)
        checked(staged_path(Path(req["region"])), req["offer_sha256"])
        archive = staged_path(Path(req["archive"]["root"]))
        refs = TleArchiveReader(archive).list_snapshots("space-track")
        if (archive_identity(archive) != req["archive"] or len(refs) != 46
                or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)):
            raise ValueError("Require the same 46 signed, staged causal references")
        targets = [staged_path(ref.path, root=archive) for ref in refs]
        residency = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *targets]))["fincore"]
        if len(residency) != len(refs) or any(row["res"] < row["size"] for row in residency):
            raise ValueError("The original causal archive is no longer fully resident")
        for item in stock["admission"]["candidate_libraries"].values():
            checked(Path(item["path"]), item["sha256"])
        staged_cache = extents_after(stage, signed, ready)
        extents_after(stage, signed, ready, canonical=True)
        root.mkdir(mode=0o700)
        (root/"tmp").mkdir()
        shutil.copytree(Path(req["region"]).parent/"fonts", root/"fonts")
        common_setup = clock(start)
        clip = source_inputs(signed, stage)
        config, folders, codec = transform(root, clip, staged_cache, member_count=13)
        conversion = original.read(root/"conversion.json")
        new_setup = now()
        retained = sum(p.stat().st_size for p in (root/"conversion").rglob("*") if p.is_file())
        if retained > DERIVATIVE_LIMIT:
            raise ValueError("The completed derivative exceeded its byte budget")
        packed_before = prepared_setup(root, config, folders, codec, conversion["sections"])
        command = quote(raw_cairo["command"], root/"candidate", config)
        verified = parser().parse_args(command[6:])
        if not (verified.cairo_six_sheets and verified.history_risk_route and verified.strict_packed_eight):
            raise ValueError("The real CLI parser must activate all three frozen policies")
        packed_setup = clock(new_setup)
        write(root/"admission.json", dict(request=req, machine=machine, custody_sha256=custody, stage=ready,
             sources=pins(), stock_score_sha256=RAW_PIN, cairo_score_sha256=CAIRO_PIN, command=command,
             phase_setup=dict(common=common_setup, candidate_specific=packed_setup, packed_before=packed_before),
             conversion_sha256=sha256((root/"conversion.json").read_bytes()).hexdigest(),
             derivative_bytes=retained, free_tmpfs_after_conversion=shutil.disk_usage(root.parent).free,
             no_backing_data=True, named_children=0))

        try:
            measure_mode(root, "candidate", command, environment_for(root),
                         lambda: extents_after(stage, signed, ready, canonical=True), require_success=False)
        finally:
            write(root/"packed-after.json", resident_packed(root/"conversion", folders, codec))
            write(root/"prediction-seal.json", roster(root))


def roster(root):
    return original.roster(root) | {name: sha256((root/name).read_bytes()).hexdigest()
                                    for name in ("conversion.json", "packed-after.json")}


def price(through_exit, packed_setup, conversion, named, previous):
    ready = through_exit + packed_setup
    first = ready + conversion
    return dict(child_elapsed_s=through_exit, candidate_specific_setup_s=packed_setup, ready_elapsed_s=ready,
                conversion_and_readback_s=conversion, charged_first_s=first, child_ratio_to_stock=named/through_exit,
                ready_ratio_to_stock=named/ready, charged_first_ratio_to_stock=named/first,
                saving_vs_cairo_s=previous-through_exit, ready_saving_vs_cairo_s=previous-ready)


def score(root, output):
    from aperture_trial import write
    from leo.contracts.digests import canonical_digest
    from publication_media_checks import image_comparison_fields, verify_position_sidecars
    from strict_history_raw_trial import packed_integrity

    receipt = original.read(root/"admission.json")
    seal = original.read(root/"prediction-seal.json")
    if (receipt["sources"] != pins() or seal != roster(root)
            or receipt["conversion_sha256"] != seal["conversion.json"]):
        raise ValueError("The completed physical output and source must match the approved launch")
    stock_score, cairo_score, earlier = controls()
    req, _, stock, saved = original.references()
    conversion = original.read(root/"conversion.json")
    log = original.read(root/"candidate-clock.json")
    if (log["command"] != quote(cairo_score["command"], root/"candidate", conversion["request"])
            or receipt["request"] != req or (root/"stock").exists()):
        raise ValueError("Expected one strict candidate on the original Cairo command and no new stock")
    if log["clock"]["exit_code"]:
        write(output, dict(qualified=False, command=log["command"], candidate=log["clock"],
                           conversion=conversion, admission=receipt))
        return
    raw = original.read(root/"candidate/unified-short-bootstrap.json")
    packed = packed_integrity(raw["packed_ci16_input"], conversion)
    pin = conversion["request"]["map_sha256"]
    witnessed = original.published(root, "candidate", log, req, stock, saved,
                                   adapters=cairo_score["admission"]["adapters"], strict_map_sha256=pin)
    previous = cairo_score["native"]
    raw_keys = ("native_sha256", "detector_recipe_sha256", "receiver_recipe", "archive_root", "requested_offer_sha256",
                "causal_cutoff_utc_ns", "clock_anchor", "raw_acquisitions", "verified_handoffs", "route", "graph_proof")
    fields = ("digest", "probes", "opportunities", "excluded", "factors", "owners", "owner_counts", "all_owned_rf_rms_hz")
    checks = dict(raw=all(raw[key] == earlier[key] for key in raw_keys), same_detectors=packed["apertures"] == earlier["receiver_audit"]["native"]["visits"],
        publication=all(witnessed[key] == previous[key] for key in fields),
        arms=witnessed["science"]["arms"] == previous["science"]["arms"],
        terminal=witnessed["terminal_parity"] and witnessed["science"]["receipt"]["terminal_sha256"] == previous["science"]["receipt"]["terminal_sha256"],
        numerical=witnessed["route_parity"] and witnessed["sidecar_science_parity"],
        images=canonical_digest(image_comparison_fields(witnessed["figures"])) == canonical_digest(image_comparison_fields(previous["figures"])),
        renderer=cairo.active_renderer(witnessed["route"]),
        packed_residency=original.read(root/"packed-after.json")["cached_pages"] == receipt["phase_setup"]["packed_before"]["cached_pages"])
    if not all(checks.values()):
        raise ValueError(f"Strict storage changed the measured original-input Cairo science: {checks}")
    sidecars = verify_position_sidecars(CAIRO_ROOT/"candidate", root/"candidate", witnessed["science"]["receipt"]["run_id"],
                                        previous["figures"], witnessed["figures"])
    estimate = price(log["clock"]["elapsed_s"], receipt["phase_setup"]["candidate_specific"]["elapsed_s"],
                     conversion["total_including_compiler_and_verification"]["wall_ns"]/1e9,
                     cairo_score["reused_stock"]["elapsed_s"], cairo_score["optional_process"]["clock"]["elapsed_s"])
    write(output, dict(qualified=True, case="DS30-0016", checks=checks, sidecars=sidecars, admission=receipt,
        conversion=conversion, candidate=log["clock"], stock=cairo_score["reused_stock"], cairo=cairo_score["optional_process"]["clock"],
        physical_scores=stock_score["geographical_and_rf"], witness=witnessed, acquire=packed, breakdown=estimate, no_new_stock=True))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--stage", type=Path, default=original.STAGE)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.action == "run":
        run(args.root, args.stage)
    else:
        score(args.root, args.output or args.root/"result.json")
