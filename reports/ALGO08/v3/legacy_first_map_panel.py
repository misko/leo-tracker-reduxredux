"""Compare first-use maps derived without a prior plan on two signed originals."""

import argparse
from collections import Counter
import json
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from legacy_first_map_0107 import (
    CURRENT, CURRENT_PIN, ENTRY, LIBRARIES, ORDINARY, ORDINARY_PIN, POSITIVE, POSITIVE_PIN,
    READY, READY_PIN, reference,
)
from visit_frame_raw_0016 import digest, read, resident

ORDER = ("DS30-0107", "DS30-0016")
CHANGED = {ENTRY, "reports/ALGO08/v3/legacy_first_map_input.py"}
SCOPED_FLAGS = ("--recording", "--archive", "--region", "--archive-sha256")


def command_for(template, scoped, output):
    command = list(template)
    if Path(command[5]).name != Path(ENTRY).name:
        raise ValueError("Expected the qualified original first-use runtime")
    command[5] = str(ROOT / ENTRY)
    for flag in ("--legacy-first-map-plan", "--legacy-first-map-plan-sha256"):
        start = command.index(flag)
        del command[start:start + 2]
    for flag in SCOPED_FLAGS:
        command[command.index(flag) + 1] = scoped[scoped.index(flag) + 1]
    command[command.index("--output") + 1] = str(output)
    if any(arg.startswith(("--legacy-first-map-plan", "--legacy-map-custody")) for arg in command):
        raise ValueError("The candidate must derive maps only from its original input")
    return command


def positive_input(prior):
    import empty_bootstrap as boot
    from combined_raw_trial import PRODUCER, checked_producer
    from eight_ms_0107_pair import verified_scope
    from exact_named_raw import staged_path
    from history_risk_0016_raw import RECORDING, STAGE, authenticate_sidecars, enrolled, require_custody
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    book = prior["admission"]
    req = book["request"]
    verified_scope(STAGE / RECORDING.name, RECORDING)
    signed = enrolled()
    if (str(RECORDING) != req["recording"] or
            require_custody(STAGE, signed) != book["source_custody_sha256"]):
        raise ValueError("Require the sealed complete tmpfs original")
    authenticate_sidecars(STAGE, signed)
    session, pin, inventory = FastScanStore(RECORDING).inventory(RECORDING, verify_windows=False)
    if (session, pin, inventory["window_count"]) != (req["session"], req["inventory"], 808):
        raise ValueError("Original session, inventory, or issued visits changed")
    archive = staged_path(Path(req["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    paths = [staged_path(ref.path, root=archive) for ref in refs]
    if (len(refs) != 46 or archive_identity(archive) != req["archive"] or
            any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("The staged original causal archive changed")
    boot.checked(staged_path(Path(req["region"])), req["offer_sha256"])
    producer = checked_producer(req["cutoff_utc_ns"], {ref.sha256 for ref in refs})
    if producer != book["producer"]:
        raise ValueError("The earlier independent orbit producer changed")
    index = [staged_path(path) for path in (PRODUCER.file, PRODUCER.file.parent / "artifact-bind.json")]
    physical = [staged_path(Path(path), root=RECORDING) for path in book["wavepaths"]]
    archive_ready = dict(tle=resident(paths), index=resident(index))
    return dict(request=req, resident=dict(waveform=resident(physical), **archive_ready),
                wavepaths=list(map(str, physical)), producer=producer, custody=book["source_custody_sha256"])


def tiny_input():
    from eight_ms_0107_pair import verified_scope
    from exact_named_raw import staged_path
    from legacy_block_0107_metadata import metadata

    tiny = metadata(ROOT)
    rec = Path(tiny["request"]["recording"])
    verified_scope(Path(tiny["signed_stage"]), rec)
    paths = [staged_path(Path(row["path"]), root=rec) for row in tiny["files"].values()]
    return tiny | {"wavepaths": list(map(str, paths))}


def source_pins(expected):
    return {path: digest(ROOT / path) for path in expected}


def panel_seal(root):
    from frame_portable_0016 import seal

    return {"admission.json": digest(root / "admission.json"),
            "cases": {case: seal(root / case) for case in ORDER}}


def launch(root):
    import empty_bootstrap as boot

    sys.path.extend((str(ROOT), str(boot.RELEASE / "src"), str(boot.RELEASE)))
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from raw_0016_best_trial import measure_mode

    started = boot.now()
    if root.exists() or root.parent != Path("/dev/shm"):
        raise ValueError("Require a fresh private tmpfs output")
    pos = reference(POSITIVE, POSITIVE_PIN)
    tiny = reference(ORDINARY, ORDINARY_PIN)
    machine = host()
    if machine != pos["admission"]["machine"] or machine != tiny["admission"]["machine"]:
        raise ValueError("The original low-priority single-core environment changed")
    expected = pos["admission"]["sources"]
    sources = source_pins(expected)
    if {path for path in expected if sources[path] != expected[path]} != CHANGED:
        raise ValueError("Only normal no-prior-plan discovery and issuance may differ")
    template = pos["clock"]["command"]
    for label in LIBRARIES:
        flag = "--legacy-first-map-" + label
        pin = template[template.index(flag + "-sha256") + 1]
        boot.checked(Path(template[template.index(flag) + 1]), pin.removeprefix("sha256:"))
    root.mkdir(mode=0o700)
    inputs, commands, admission = {}, {}, {}
    for case, load in zip(ORDER, (tiny_input, lambda: positive_input(pos)), strict=True):
        stage = boot.now()
        folder = root / case
        folder.mkdir(mode=0o700)
        (folder / "tmp").mkdir()
        shutil.copytree(POSITIVE / "fonts", folder / "fonts")
        inputs[case] = load()
        scoped = tiny["admission"]["commands"]["ordinary"] if case == ORDER[0] else template
        commands[case] = command_for(template, scoped, folder / "fused")
        admission[case] = boot.clock(stage)
    revision = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT}", "-C", ROOT, "rev-parse", "HEAD"], text=True,
    ).strip()
    write(root / "admission.json", dict(order=ORDER, machine=machine, inputs=inputs, commands=commands,
          sources=sources, changed=sorted(CHANGED), runtime_revision=revision, admission=admission,
          controller_admission=boot.clock(started), prior_map_files_used_by_candidate=0,
          original_waveform_bytes_opened_by_preflight=0, compiler_invocations=0))
    for case in ORDER:
        folder, argv = root / case, commands[case]
        usage, started = getrusage(RUSAGE_CHILDREN), boot.now()
        probe = subprocess.run([*argv, "--first-map-setup-only"], env=environment_for(folder),
                               capture_output=True, text=True, timeout=15)
        elapsed, after = boot.clock(started), getrusage(RUSAGE_CHILDREN)
        child_cpu = after.ru_utime - usage.ru_utime + after.ru_stime - usage.ru_stime
        write(folder / "upfront-probe.json", dict(clock=elapsed, child_cpu_s=child_cpu,
              exit_code=probe.returncode, stdout=probe.stdout, stderr=probe.stderr))
        if probe.returncode:
            raise ValueError(f"First-use startup probe refused: {probe.stderr}")
        receipt = json.loads(probe.stdout)
        if ((folder / "fused").exists() or not receipt["reached_scanner"] or receipt["waveform_opens"]
                or receipt["audit"]["authority_mode"] != "verified-first-use"):
            raise ValueError("Upfront probe must reach installed scanner without waveform I/O or publication")
    for case in ORDER:
        folder = root / case
        measure_mode(folder, "fused", commands[case], environment_for(folder),
                     lambda: resident(inputs[case]["wavepaths"]), require_success=False)
    write(root / "prediction-seal.json", panel_seal(root))


def map_parity(folder, independent, pin, req, windows, kinds):
    from reports.ALGO08.v3 import legacy_block_input as port

    bundle = folder / "legacy-first-maps"
    plan = port.load_custody(bundle / "custody.json", pin)
    audit = read(folder / "legacy-first-map-acquisition.json")
    if ((bundle / "custody.json").read_bytes() != (independent / "custody.json").read_bytes()
            or (plan["session"], plan["inventory"], plan["raw_authority"], plan["windows"])
            != (req["session"], req["inventory"], req["authority"], windows)
            or audit["authority_mode"] != "verified-first-use" or audit["plan_sha256"] != pin
            or audit["finished_raw_authority"] != req["authority"]
            or Counter(m["map_kind"] for m in plan["members"]) != kinds
            or {p.name for p in bundle.iterdir()} != {"custody.json", *(m["map"] for m in plan["members"])}):
        raise ValueError("The fresh complete replay bundle must match independently constructed custody")
    for row, declaration in zip(audit["members"], plan["members"], strict=True):
        leaf, sha = declaration["map"], declaration["map_sha256"]
        content = port.checked_file(bundle / leaf, sha, port.MAX_CUSTODY)
        if (any(row[key] != value for key, value in declaration.items())
                or content != port.checked_file(independent / leaf, sha, port.MAX_CUSTODY)
                or len(content) != row["map_bytes"]
                or row["proof"]["original_encoded_reused"] != declaration["encoded"]
                or row["proof"]["prefix_bytes"] != 640_000):
            raise ValueError("A published map failed durable readback or original replay proof")
    return audit


def score(root):
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from aperture_trial import write
    from history_risk_residual_layout_0402 import media_identity
    from legacy_block_0107_score import snapshot as withheld, speedup_gate
    from legacy_block_raw_score import snapshot as complete
    from legacy_first_map_0016 import ALL, PREVIOUS, references
    from leo.contracts.digests import canonical_digest
    from publication_media_checks import verify_position_sidecars

    book = read(root / "admission.json")
    if read(root / "prediction-seal.json") != panel_seal(root) or book["sources"] != source_pins(book["sources"]):
        raise ValueError("The issued and sealed outputs or runtime source changed")
    tiny_control = reference(ORDINARY, ORDINARY_PIN)
    tiny_ready = reference(READY, READY_PIN)
    writer_ready = reference(CURRENT, CURRENT_PIN)
    large_control, large_ready = references()
    records = {}
    for case in ORDER:
        folder = root / case
        output = folder / "fused"
        log = read(folder / "fused-clock.json")
        req = book["inputs"][case]["request"]
        if log["command"] != book["commands"][case] or log["clock"]["exit_code"]:
            raise ValueError("No successful original candidate for " + case)
        if case == ORDER[0]:
            current = withheld(output, log["clock"], req)
            for old in (tiny_control["paired"]["ordinary"], writer_ready["proof"]):
                for key in ("native_digest", "terminal", "scan_digest", "graph_proof", "receiver_visits"):
                    if current[key] != old[key]:
                        raise ValueError("The exact original withholding changed: " + key)
            sidecars = None
            maps = map_parity(output, READY / "maps", tiny_ready["admission"]["plan_pin"], req, 29, {"literal": 1})
            original = tiny_control["admission"]["installed_prior"]
            ordinary = tiny_control["clocks"]["ordinary"]
        else:
            old = large_control["products"]["ordinary"]
            current = complete(output, log, req, book["inputs"][case]["producer"])
            for key in ("native_sha256", "native_source", "ordered_owners", "history_risk"):
                if current[key] != old[key]:
                    raise ValueError("The exact original complete fix changed: " + key)
            for key in ("raw_authority", "arms", "owners", "scientific_digests"):
                if current["published"][key] != old["published"][key]:
                    raise ValueError("A published scientific product changed: " + key)
            receipt_fields = ("decision", "session_id", "run_id", "terminal_sha256", "region", "window_count", "counts")
            if (canonical_digest(current["positions"]) != canonical_digest(old["positions"])
                    or media_identity(current["images"]) != media_identity(old["images"])
                    or any(current["receipt"][key] != old["receipt"][key] for key in receipt_fields)):
                raise ValueError("Position, figures or terminal differ from the sealed ordinary control")
            sidecars = verify_position_sidecars(PREVIOUS / "ordinary", output, current["receipt"]["run_id"],
                                                old["images"], current["images"])
            maps = map_parity(output, ALL / "maps", large_ready["admission"]["map_custody_sha256"],
                              req, 808, {"literal": 5, "exception": 8})
            original = large_control["admission"]["prior_installed"]
            ordinary = old["process"]
        for lib in LIBRARIES:
            flag = "--legacy-first-map-" + lib + "-sha256"
            if maps[lib + "_sha256"] != log["command"][log["command"].index(flag) + 1]:
                raise ValueError("A different native build was loaded")
        records[case] = dict(science=current, maps=maps, clock=log, sidecars=sidecars, original=original,
                             ordinary=ordinary, upfront_probe=read(folder / "upfront-probe.json"))
    gates = {}
    for metric in ("elapsed_s", "cpu_s"):
        installed = {case: row["original"][metric] for case, row in records.items()}
        ordinary = {case: row["ordinary"][metric] for case, row in records.items()}
        fresh = {case: row["clock"]["clock"][metric] for case, row in records.items()}
        gates[metric] = dict(original=speedup_gate(installed, fresh), ordinary=speedup_gate(ordinary, fresh))
    write(root / "result.json", dict(qualified=True, cases=records, paired_gates=gates,
          admission=book, prediction_seal_sha256=digest(root / "prediction-seal.json")))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "score": score}[args.mode](args.root)
