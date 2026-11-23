"""Verify a bounded no-track proof on sealed packets and one tiny raw pair."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent


def saved_check(root, literal, region, archive, recording):
    import empty_bootstrap as staged
    from short_graph_guard import prove
    from unified_short_bootstrap import Handoff, withhold

    _, specification, sources, _, _ = staged.load_runtime()
    from empty_bootstrap_trial import document_bytes
    from full_short_raw import RECIPE_SHA
    from leo.contracts.digests import canonical_digest

    scan = staged.staged_scanner(sources)
    offer = scan.Algo08Region.parse(json.loads(region.read_bytes()))
    args = SimpleNamespace(recording=recording, output=root / "saved", archive=archive)
    (tiny_file,) = (literal / "tiny/candidate/fast-scan-automatic-work").glob("*/detections.json")
    (weak_file,) = (literal / "weak/candidate/fast-scan-automatic-work").glob("*/detections.json")
    packet, weak = (json.loads(path.read_bytes()) for path in (tiny_file, weak_file))
    session, digest, _ = scan.FastScanStore(args.output).inventory(recording, verify_windows=False)
    staged.bind_native(packet, session, digest, RECIPE_SHA, expected="sha256:9321bfb1269d3d190403cf21118223c040ef381dfcf22ea78ff5daac901f60f9")
    if canonical_digest(weak) != "sha256:c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589":
        raise ValueError("Unexpected sealed active packet")
    with TemporaryDirectory() as tmp:
        assets = Path(tmp)
        scan.PINS["cancellation-factors.so"] = specification["detector_sha256"]
        for name in (*scan.PINS, "native", "projector.so"):
            source = Path(specification["detector"]) if name == "cancellation-factors.so" else staged.RELEASE / "assets" / name
            (assets / name).symlink_to(source)
        clocks = staged.now()
        proof, active = prove(packet, assets), prove(weak, assets)
        elapsed = staged.clock(clocks)
        if not proof["proven"] or proof["winning_rows"] != 13 or active["proven"] or active["winning_rows"] != 475:
            raise ValueError("The sealed tiny or active packets did not exercise the expected cutoff")
        staged.check_inert_solver_assets(assets)
        handoff = Handoff(session, digest, RECIPE_SHA, packet)
        receipt = withhold(scan, args, offer, assets, handoff, "no_active_curvature", graph_proof=proof)
        if handoff.calls != 1 or any(name in sys.modules for name in staged.SCIENTIFIC_IMPORTS):
            raise ValueError("The certified saved case did not follow receiver-first publication")
    files = {}
    for namespace in ("fast-scan-inputs", "fast-scan-reports", "fast-scan-automatic-work", "fast-scan-standard-v2"):
        expected = document_bytes(literal / "tiny/candidate", namespace)
        if expected != document_bytes(args.output, namespace):
            raise ValueError(f"Saved no-track proof changed byte content in {namespace}")
        files.update(expected)
    return dict(tiny=proof, weak=active, proof_pair=elapsed, receipt=receipt, files=files, waveform_calls=0)


def run(root, literal, short, geographic, regional, block):
    from aperture_trial import archive_identity, read, write
    from dense_geographic_trial import host
    from empty_bootstrap import BASELINE, RELEASE
    from empty_bootstrap_trial import document_bytes
    from full_short_physical import environment
    from local_future_cli_trial import cache_before
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, CASES, FastScanStore, assignment, cache_residency, checked, measure, pairs
    from unified_short_bootstrap_trial import condition_tiny

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("The frozen launch requires tmpfs publication roots")
    case, pin, decision, visits, _ = CASES[0]
    pair, archived = assignment(case, pin, decision, visits)
    recording, region, archive = Path(pair["recording"]), Path(pair["region"]), Path(pair["archive"]["root"])
    if archive_identity(archive) != pair["archive"] or not (literal / "result.json").is_file():
        raise ValueError("Require the completed literal comparison and original causal archive")
    installed = pairs.verified_v3(pairs.NAMED_V3)
    root.mkdir()
    env, python = environment(root), RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    validation = subprocess.check_output([python, "-IB", __file__, "saved-check", root, literal, region, archive, recording],
                                         env=env, timeout=30)
    checked_saved = json.loads(validation)
    write(root / "saved-verified.json", checked_saved)
    store = FastScanStore(root)
    session, digest, inventory = store.inventory(recording, verify_windows=False)
    if session != archived["receipt"]["session_id"] or inventory["window_count"] != visits:
        raise ValueError("The original signed tiny recording changed")
    members = tuple((Path(row["path"])/"manifest.json", row["manifest_digest"]) for row in inventory["segments"])
    query = cache_residency.load_query(checked(CACHE_LIB, CACHE_SHA))
    (root / "stock").mkdir()
    shared = ["--recording", recording, "--archive", archive, "--region", region]
    commands = dict(stock=[BASELINE, *shared, "--bulk-root", root / "stock"],
                    candidate=[python, "-IB", HERE / "unified_short_bootstrap.py", *shared, "--prove-empty-graph",
                               "--short-binary", short, "--geographic-library", geographic, "--regional-track-library", regional,
                               "--frontier-block-library", block, "--output", root / "candidate"])
    order, rows = ("candidate", "stock"), {}
    collection = ("fast-scan-inputs", "fast-scan-reports", "fast-scan-automatic-work", "fast-scan-standard-v2")
    with ExitStack() as scope:
        mapped = condition_tiny(members, scope)
        for arm in order:
            cache = cache_before(store, recording, members, query)
            clock = measure(commands[arm], env, root / arm)
            rows[arm] = dict(clock=clock, cache=cache, command=list(map(str, commands[arm])))
            write(root / f"{arm}-clock.json", rows[arm])
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])
    for arm in order:
        receipt = json.loads((root / f"{arm}.stdout").read_bytes())
        rows[arm]["evidence"] = pairs.evidence(root / arm, receipt, rows[arm]["clock"]["started_unix_ns"], read_only=True)
        if arm == "stock":
            pairs.verify_v3_publication(root / arm, receipt)
        files = {}
        for namespace in collection:
            matched = document_bytes(literal / "tiny" / arm, namespace)
            if document_bytes(root / arm, namespace) != matched:
                raise ValueError(f"Raw {arm} bytes changed in {namespace}")
            files.update(matched)
        rows[arm]["byte_parity"] = files
    audit = read(root / "candidate/unified-short-bootstrap.json")
    if (audit["route"] != "authenticated_installed_graph_ineligible" or audit["graph_proof"] != checked_saved["tiny"]
            or audit["scientific_imports_after"] or audit["raw_acquisitions"] != 1 or audit["verified_handoffs"] != 1):
        raise ValueError("The raw comparison did not exercise the exact no-track route")
    write(root / "result.json", dict(case=case, machine=machine, installed=installed, archive=pair["archive"],
          input_manifest=digest, order=order, mapped_bytes=mapped, rows=rows, saved=checked_saved, audit=audit,
          literal_trial_source_sha256=sha256((literal / "result.json").read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "short-graph-guard-protocol.md").read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["saved-check"]:
        sys.path.insert(0, str(HERE))
        for name in ("root", "literal", "region", "archive", "recording"):
            parser.add_argument(name, type=Path)
        print(json.dumps(saved_check(**vars(parser.parse_args(sys.argv[2:]))), allow_nan=False))
    else:
        for name in ("root", "literal", "short", "geographic", "regional", "block"):
            parser.add_argument(name, type=Path)
        run(**vars(parser.parse_args()))
