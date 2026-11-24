"""Repeat the sealed resident original ALGO08v3 stock commands only."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import resource
import shutil
import subprocess
from time import perf_counter


HERE = Path(__file__).resolve().parent
ORDER = ("DS30-0107", "DS30-0016")
CONTROLS = {
    ORDER[0]: ("history-risk-0107-raw.json.gz", "7c4b5443533a3d8f3c08ed08a788ee4e236843b17575ef20e62fc672b7722d00"),
    ORDER[1]: ("history-risk-0016-raw.json.gz", "5b84151697623d67ce43f7ec2ddcf3f9fc488701625754fabb8d6f7a612d23d3"),
}


def sealed_control(case):
    name, pin = CONTROLS[case]
    encoded = (HERE / "measurements" / name).read_bytes()
    if sha256(encoded).hexdigest() != pin:
        raise ValueError("Frozen stock comparison receipt changed")
    doc = json.loads(gzip.decompress(encoded))
    return doc["score"]["value"] if case == ORDER[0] else doc


def stock_command(admission, root):
    req = admission["request"]
    prior = admission["commands"]["stock"]
    expected = ["/opt/leo-algo08/algo08v3/run", "--recording", req["recording"],
                "--archive", req["archive"]["root"], "--region", req["region"], "--bulk-root"]
    if prior[:-1] != expected or Path(prior[-1]).name != "stock":
        raise ValueError("Unexpected installed ALGO08v3 command")
    return [*expected, str(root / "stock")]


def read_resident_custody(case, req, admitted):
    from eight_ms_0107_pair import is_resident, verified_scope
    from empty_bootstrap import checked
    from exact_named_raw import staged_path
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import pairs

    recording = Path(req["recording"])
    if case == ORDER[0]:
        import continued_cfo_small_raw as original

        stage = Path(admitted["stage"])
        verified_scope(stage, recording)
        session, members = original.input_inventory()
        actual = {name: dict(path=str(path), bytes=size, sha256=pin)
                  for name, (path, size, pin) in members.items()}
        if session != req["session"] or actual != admitted["member_files"]:
            raise ValueError("Original staged 0107 authority changed")

        def resident():
            verified_scope(stage, recording)
            caches = original.residency(members)
            if not is_resident(caches):
                raise ValueError("Expected complete resident original 0107")
            return caches["payload"] | {"index_cache": caches["index"]}

        custody, count = actual, admitted["catalogue"]["snapshots"]
    else:
        import history_risk_0016_raw as original
        from guarded_cfo_0016_stage import cache_states, fully_resident

        stage = Path(admitted["stage"]["stage"])
        verified_scope(stage / recording.name, recording)
        signed = original.enrolled()
        if any(signed[k] != req[v] for k, v in (("recording", "recording"), ("inventory_sha256", "inventory"),
                                                ("raw_authority", "authority"), ("session", "session"))):
            raise ValueError("Original staged 0016 authority changed")
        custody = original.require_custody(stage, signed)
        if custody != admitted["custody_sha256"]:
            raise ValueError("Original staged 0016 custody changed")
        original.authenticate_sidecars(stage, signed)
        files = {kind: [(Path(path), size, pin) for path, size, pin in rows]
                 for kind, rows in original.stage_files(signed).items()}

        def resident():
            verified_scope(stage / recording.name, recording)
            progress = original.readiness(stage, signed)
            if not progress["ready"] or progress["files"] != admitted["stage"]["files"]:
                raise ValueError("Original staged 0016 file identities changed")
            caches = cache_states(files)
            if not fully_resident(caches):
                raise ValueError("Expected complete resident original 0016")
            return caches["payload"] | {"index_cache": caches["index"]}

        count = admitted["archive_before"]["snapshots"]
    archive = staged_path(Path(req["archive"]["root"]))
    offer = staged_path(Path(req["region"]))
    checked(offer, req["offer_sha256"])
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != count or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)
            or pairs.archive_identity(archive) != req["archive"]):
        raise ValueError("Original offer or causal archive changed")
    bodies = [staged_path(ref.path, root=archive) for ref in refs]

    def archive_resident():
        rows = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *bodies]))["fincore"]
        if len(rows) != count or any(row["res"] < row["size"] for row in rows):
            raise ValueError("Expected complete resident original causal archive")
        return dict(snapshots=count, bytes=sum(row["size"] for row in rows))

    return resident, archive_resident, custody, offer


def pressure():
    return {kind: values.strip() for kind, values in
            (line.split(" ", 1) for line in Path("/proc/pressure/io").read_text().splitlines())}


def qualified_science(case, root, log, req, expected):
    if log["clock"]["exit_code"] != 0:
        raise ValueError("Installed ALGO08v3 child failed")
    if case == ORDER[0]:
        from history_risk_0107_raw import controls, published

        request, _, references = controls()
        if req != request:
            raise ValueError("Sealed 0107 requests differ")
        result = published(root, "stock", log, req, references["stock"])
        keys = ("digest", "science", "opportunities", "excluded", "figures", "owner_counts", "factors")
    else:
        from history_risk_0016_raw import published, references

        request, _, prior, saved = references()
        if req != request:
            raise ValueError("Sealed 0016 requests differ")
        result = published(root, "stock", log, req, prior, saved)
        if (not all(result[name] for name in ("native_parity", "terminal_parity", "reference_owner_parity", "sidecar_science_parity"))
                or len(result["png_parity"]) != 8 or not all(result["png_parity"].values())
                or result["full_sidecar_record_parity"] != expected["full_sidecar_record_parity"]):
            raise ValueError("Stock publication differs from original signed science")
        keys = ("digest", "opportunities", "excluded", "figures", "owners", "owner_counts", "factors", "sidecars")
    # The image inspector returns tuple dimensions and DPI, while archived JSON
    # stores the same ordered values in arrays.
    if any(json.dumps(result[key], sort_keys=True) != json.dumps(expected[key], sort_keys=True) for key in keys):
        raise ValueError("Stock publication differs from the preregistered installed comparison")
    return result


def launch(case, root):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path
    from history_risk_0016_raw import roster
    from raw_0016_best_trial import measure_mode
    from short_raw_diagnostic import pairs

    start = perf_counter()
    machine = host()
    control = sealed_control(case)
    admitted = control["admission"]
    req = admitted["request"]
    if machine != admitted["machine"] or pairs.verified_v3(pairs.NAMED_V3) != admitted["stock"]:
        raise ValueError("Expected the original low-priority installed comparison environment")
    staged_path(root.parent)
    argv = stock_command(admitted, root)
    resident, archive_resident, custody, offer = read_resident_custody(case, req, admitted)
    resident()
    archive_before = archive_resident()
    root.mkdir()
    (root / "tmp").mkdir()
    shutil.copytree(offer.parent / "fonts", root / "fonts")
    env = environment_for(root)
    write(root / "admission.json", dict(case=case, order=ORDER, command=argv, request=req, machine=machine,
          historical_control=CONTROLS[case], driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          custody=custody, archive_before=archive_before, prelaunch_setup_s=perf_counter() - start,
          original_backing_bytes=0, conditioning_bytes=0))
    before_io = pressure()
    before_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    measure_mode(root, "stock", argv, env, resident, require_success=False)
    after_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    write(root / "process-context.json", dict(io_before=before_io, io_after=pressure(),
          peak_child_rss_kib=after_rss if after_rss > before_rss else None,
          child_maxrss_before_kib=before_rss, child_maxrss_after_kib=after_rss, archive_after=archive_resident()))
    seal = roster(root) | {"process-context.json": sha256((root / "process-context.json").read_bytes()).hexdigest()}
    write(root / "prediction-seal.json", seal)


def score(case, root, destination):
    if case == ORDER[0]:
        from portable_orbit_index_trial import local_launcher_tools

        local_launcher_tools()

    from aperture_trial import write
    from history_risk_0016_raw import read, roster

    seal = root / "prediction-seal.json"
    context = root / "process-context.json"
    control = sealed_control(case)
    admitted = read(root / "admission.json")
    log = read(root / "stock-clock.json")
    if (read(seal) != roster(root) | {context.name: sha256(context.read_bytes()).hexdigest()}
            or admitted["case"] != case or admitted["request"] != control["admission"]["request"]
            or log["command"] != stock_command(control["admission"], root)):
        raise ValueError("Measured stock launch changed before scoring")
    checked = qualified_science(case, root, log, admitted["request"], control["runs"]["stock"])
    write(destination, dict(case=case, qualified=True, admission=admitted, process_context=read(context),
                            scorer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                            stock=checked, seal_sha256=sha256(seal.read_bytes()).hexdigest()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("case", choices=ORDER)
    cli.add_argument("root", type=Path)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.action == "launch" and args.output is None:
        launch(args.case, args.root)
    elif args.action == "score" and args.output is not None and not args.output.resolve().is_relative_to(args.root.resolve()):
        score(args.case, args.root, args.output)
    else:
        cli.error("Supply --output outside the sealed run for scoring only")
