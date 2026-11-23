"""Time one tiny fresh raw pair and verify one nonempty saved handoff."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch

from empty_bootstrap import BASELINE, BASELINE_PIN, PAYLOAD, RELEASE, bind_native

WEAK = "sha256:4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0"


def saved_stock(args):
    from empty_bootstrap import checked

    checked(BASELINE, BASELINE_PIN)
    namespace = runpy.run_path(str(BASELINE))
    specification = namespace["checked_spec"](PAYLOAD)
    sys.path[:0] = [str(PAYLOAD), str(RELEASE / "src"), str(RELEASE)]
    from tools.pipeline_eval.variants.experimental.lean_startup import install
    install()
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import experimental_publication

    native = json.loads(args.saved.read_bytes())

    def verified_handoff(session, digest, *_):
        bind_native(native, session, digest, specification["detector_sha256"], expected=args.saved_digest)
        return native

    with patch.object(algo08_scan, "acquire", verified_handoff):
        return experimental_publication.run(args, dict(specification, startup="stock"))


def document_bytes(root, relative):
    files = (root / relative).rglob("*")
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in files if path.is_file()}


def exact_raw(stock, candidate):
    result = {}
    for publication in ("fast-scan-inputs", "fast-scan-reports", "fast-scan-automatic-work", "fast-scan-standard-v2"):
        a, b = document_bytes(stock, publication), document_bytes(candidate, publication)
        if a != b:
            raise ValueError(f"Raw detector or withheld publication differs: {publication}")
        result.update(a)
    stdout = stock.with_suffix(".stdout").read_bytes()
    if stdout != candidate.with_suffix(".stdout").read_bytes():
        raise ValueError("The candidate printed a different numeric receipt")
    if not all(any(path.endswith("/" + name) for path in result) for name in ("detections.json", "terminal.json", "withheld.json")):
        raise ValueError("Expected the full empty publication payload")
    return dict(files=result, stdout=sha256(stdout).hexdigest())


def timed_pair(root):
    from aperture_trial import read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from joint_publication import artifacts
    from local_future_cli_trial import cache_before, native_packet
    from short_raw_diagnostic import (
        CACHE_LIB, CACHE_SHA, CASES, HERE, FastScanStore, assignment, cache_residency, checked, measure, pairs, science,
    )
    from weak_combined_raw import REFERENCE, REFERENCE_PIN

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use private tmpfs roots for both publication arms")
    case, pin, decision, visits, order = CASES[0]
    if (case, decision, visits, order) != ("DS30-0227", "withheld", 18, ("stock", "candidate")):
        raise ValueError("Expected only the frozen tiny raw case")
    pair, archived = assignment(case, pin, decision, visits)
    stock_build = pairs.verified_v3(pairs.NAMED_V3)
    cache_query = cache_residency.load_query(checked(CACHE_LIB, CACHE_SHA))
    request = read(checked(REFERENCE, REFERENCE_PIN))
    checked(Path(request["region_file"]), request["offer_sha256"])
    packet = checked(native_packet(REFERENCE.parent / "stock"), WEAK)

    root.mkdir()
    env, python = environment(root), RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    recording = Path(pair["recording"])
    store = FastScanStore(root)
    session, inventory_pin, inventory = store.inventory(recording, verify_windows=False)
    if session != archived["receipt"]["session_id"] or inventory["window_count"] != visits:
        raise ValueError("The signed recording inventory differs")
    manifests = tuple((Path(row["path"]), row["sha256"]) for row in pair["cache_observation"]["manifests"])
    candidate = [python, "-IB", HERE / "empty_bootstrap.py"]
    raw_arguments = ["--recording", recording, "--archive", pair["archive"]["root"], "--region", pair["region"]]
    commands = dict(stock=[BASELINE, *raw_arguments], candidate=[*candidate, *raw_arguments])
    raw = {}
    for arm in order:
        cache = cache_before(store, recording, manifests, cache_query)
        output = root / arm
        output.mkdir()
        command = [*commands[arm], "--bulk-root", output]
        run = measure(command, env, output)
        raw[arm] = dict(clock=run, cache=cache, command=list(map(str, command)))
        write(root / f"{arm}-clock.json", raw[arm])
        if run["exit_code"]:
            raise RuntimeError(f"{arm} exited with {run['exit_code']}: {run['stderr_tail']}")

    raw_evidence = science(root, "stock", raw["stock"]["clock"], archived, inventory_pin)
    raw_exact = exact_raw(root / "stock", root / "candidate")
    raw_audit = read(root / "candidate/empty-bootstrap.json")
    if (raw_audit["route"], raw_audit["factors"], raw_audit["probes"], raw_audit["raw_acquisitions"]) != ("authenticated_empty", 0, 28, 1):
        raise ValueError("The raw route did not earn the empty proof")
    write(root / "raw-verified.json", dict(clock=raw, exact=raw_exact, evidence=raw_evidence, audit=raw_audit))

    saved_args = ["--recording", request["recording"], "--archive", request["archive"]["root"],
                  "--region", request["region_file"], "--saved", packet, "--saved-digest", WEAK]
    saved = {}
    for arm, argv in (("stock-saved", [python, "-BPs", Path(__file__).resolve(), "saved-stock"]), ("candidate-saved", candidate)):
        output = root / arm
        output.mkdir()
        command = [*argv, *saved_args, "--bulk-root", output]
        run = measure(command, env, output)
        write(root / f"{arm}-clock.json", dict(clock=run, command=list(map(str, command))))
        if run["exit_code"]:
            raise RuntimeError(f"{arm} exited with {run['exit_code']}: {run['stderr_tail']}")
        original = json.loads(output.with_suffix(".stdout").read_text())
        evidence = pairs.evidence(output, original, run["started_unix_ns"], read_only=True)
        saved[arm] = dict(clock=run, published=evidence, images=artifacts(output, original)["images"])
    stock, revised = saved.values()
    compare = ("arms", "owners", "scientific_digests", "artifacts", "raw_authority", "reason")
    saved_audit = read(root / "candidate-saved/empty-bootstrap.json")
    if (any(stock["published"][key] != revised["published"][key] for key in compare)
            or stock["images"] != revised["images"] or len(stock["images"]) != 8
            or saved_audit["route"] != "ordinary_installed_fit" or saved_audit["raw_acquisitions"] != 0
            or saved_audit["verified_handoffs"] != 1 or saved_audit["factors"] <= 0):
        raise ValueError("The active same-process handoff changed published science or figures")
    write(root / "result.json", dict(case=case, machine=machine, stock_build=stock_build, raw=raw,
          exact_raw=raw_exact, raw_evidence=raw_evidence, raw_audit=raw_audit, saved=saved,
          saved_audit=saved_audit, weak_packet=WEAK, raw_assignment=pin,
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "empty-bootstrap-protocol.md").read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["saved-stock"]:
        for name in ("recording", "archive", "region", "bulk-root", "saved"):
            parser.add_argument("--"+name, type=Path, required=True)
        parser.add_argument("--saved-digest", required=True)
        print(json.dumps(saved_stock(parser.parse_args(sys.argv[2:]))))
    else:
        parser.add_argument("root", type=Path)
        timed_pair(parser.parse_args().root)
