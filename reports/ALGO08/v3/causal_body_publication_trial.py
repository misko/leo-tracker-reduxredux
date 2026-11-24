"""Validate the gated causal election through the normal saved publication."""

import argparse
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import shutil
import subprocess
import sys
from time import perf_counter, time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from causal_body_election_trial import REFERENCE, deny_backing, enrolled


MODES = ("control", "election")
REPORTS = ("exact_named_route.py", "exact_named_raw.py", "historical_orbit_index.py", "causal_body_election.py",
           "causal_body_publication_trial.py", "causal_body_election_trial.py", "causal-body-election-protocol.md")


def pins():
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in REPORTS}


def route_evidence(choice):
    census = choice["census"]
    prior = {name: {k: v for k, v in row.items() if k not in ("cpu_ns", "elapsed_ns")}
             for name, row in census["prior"].items()}
    return dict(route=choice["route"], reason=choice["reason"], census=dict(census, prior=prior))


@contextmanager
def election_port(audit):
    """Keep the existing exact preparation and publish the opt-in witness."""
    import exact_named_route as route
    from causal_body_election import binding

    original = route.exact_ports

    @contextmanager
    def extended(*args, **options):
        with original(*args, **options), binding(audit):
            yield

    with patch.object(route, "exact_ports", extended):
        yield


def worker(root, mode):
    import empty_bootstrap as boot

    sys.addaudithook(deny_backing)
    _, specification, _, publication, _ = boot.load_runtime()
    from cumulative_grid_projection import saved_inventory_port
    from exact_named_raw import publish_active, write
    from leo.storage.fast_scan import FastSegmentSource
    from named_constrained_research import deny_waveform
    from unified_short_bootstrap import Handoff

    launch = json.loads((root/"binding.json").read_bytes())
    if launch["sources"] != pins():
        raise ValueError("Frozen saved comparison sources changed")
    native, archive, _, _, portable, req, _ = enrolled()
    output = root/mode
    args = SimpleNamespace(recording=Path(req["recording"]), archive=archive, region=Path(req["region"]),
                           archive_sha256=req["archive"]["snapshots_sha256"], output=output,
                           portable_orbit_index=portable.file, portable_orbit_index_sha256=portable.sha256,
                           portable_orbit_producer_sha256=portable.producer_sha256,
                           history_risk_route=True, cairo_residual_layout=True)
    handoff = Handoff(req["session"], req["inventory"], req["detector"][7:], native)
    audit = {}
    with (saved_inventory_port(req | {"receiver": "native-20-8-held-history"}) as authorized,
          patch.object(FastSegmentSource, "windows", deny_waveform),
          election_port(audit) if mode == "election" else nullcontext()):
        receipt, _ = publish_active(args, publication, specification, handoff)
    native_file, = (output/"fast-scan-automatic-work").glob("*/detections.json")
    boot.checked(native_file, req["native"][7:])
    if not authorized or handoff.calls != 1 or receipt["decision"] != "complete":
        raise ValueError("Expected precisely one authenticated saved physical publication")
    write(output/"causal-election.json", dict(receipt=receipt, sources=launch["sources"], audit=audit,
                                             waveform_reads=0, saved_handoffs=handoff.calls))


def paired(root, preparation):
    import empty_bootstrap as boot

    sys.addaudithook(deny_backing)
    from exact_named_raw import staged_path, write

    staged_path(root.parent)
    pre = json.loads(preparation.read_bytes())
    source = pins()
    if (not pre["advances"] or min(pre["preparation_cpu_gains_s"]) < .1
            or pre["source_sha256"] != source["causal_body_election.py"]
            or pre["protocol_sha256"] != source["causal-body-election-protocol.md"]):
        raise ValueError("The unchanged candidate must clear the exact prepared-input gate")
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(REFERENCE/"fonts", root/"fonts")
    env = os_environ(root)
    commands = {mode: ["/usr/bin/timeout", "--kill-after=2s", "25s", str(boot.RELEASE/"venv/bin/python"),
                       "-BPs", str(Path(__file__).resolve()), "worker", str(root), mode] for mode in MODES}
    write(root/"binding.json", dict(preparation_sha256=sha256(preparation.read_bytes()).hexdigest(),
                                    sources=source, order=MODES, commands=commands))
    measured = {}
    for mode in MODES:
        clock = measure(commands[mode], env, root/mode)
        measured[mode] = clock
        write(root/f"{mode}-clock.json", clock)
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])
    write(root/"through-exit.json", measured)
    score(root, pre)


def measure(command, env, destination):
    before = getrusage(RUSAGE_CHILDREN)
    started_ns, started = time_ns(), perf_counter()
    with destination.with_suffix(".stdout").open("x") as stdout, destination.with_suffix(".stderr").open("x") as stderr:
        child = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, check=False)
    elapsed = perf_counter() - started
    after = getrusage(RUSAGE_CHILDREN)
    return dict(started_unix_ns=started_ns, elapsed_s=elapsed, exit_code=child.returncode,
                cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                input_blocks=after.ru_inblock-before.ru_inblock, major_faults=after.ru_majflt-before.ru_majflt,
                stderr_tail=destination.with_suffix(".stderr").read_text()[-2500:])


def os_environ(root):
    import os
    from empty_bootstrap import PAYLOAD, RELEASE

    paths = (HERE, PAYLOAD, RELEASE/"src", RELEASE, HERE.parents[2])
    return os.environ | dict(
        PYTHONPATH=os.pathsep.join(map(str, paths)), TMPDIR=str(root/"tmp"),
        MPLCONFIGDIR=str(root/"fonts"), XDG_CACHE_HOME=str(root/"tmp"))


def score(root, preparation):
    import empty_bootstrap as boot
    from exact_named_raw import write
    from publication_media_checks import verify_position_sidecars

    sys.addaudithook(deny_backing)

    def read(path):
        return json.loads(path.read_bytes())

    _, _, _, _, _, request, reference = enrolled()
    control, candidate = [read(root/mode/"exact-named-raw-witness.json") for mode in MODES]
    clocks = read(root/"through-exit.json")
    products = []
    old_cairo = reference["ports"]["cairo_layout"]
    for mode, live in zip(MODES, (control, candidate), strict=True):
        output = root/mode
        audit = read(output/"causal-election.json")
        receipt = audit["receipt"]
        actual = live["evidence"]
        run = receipt["run_id"]
        terminal_name = Path("fast-scan-automatic-work")/run/"terminal.json"
        previous = REFERENCE/"indexed"/terminal_name
        terminal = boot.checked(output/terminal_name, receipt["terminal_sha256"][7:])
        checks = verify_position_sidecars(REFERENCE/"indexed", output, run, reference["evidence"]["images"],
                                          actual["images"])
        comparisons = ("owner_rows", "owner_maps", "images", "grid", "detail")
        ports = live["ports"]
        cairo = ports["cairo_layout"]
        if (terminal != previous.read_bytes() or audit["saved_handoffs"] != 1 or audit["waveform_reads"]
                or actual["grid"] != 179 or set(actual["owner_rows"]) != {"c0", "fitted_c"}
                or any(actual[k] != reference["evidence"][k] for k in comparisons)
                or route_evidence(ports["history_risk"]["choice"]) != route_evidence(reference["ports"]["history_risk"]["choice"])
                or ports["verified_tle"] != reference["ports"]["verified_tle"]
                or live["solver_recipe"] != reference["solver_recipe"]
                or ports["png"]["verified"] != ports["png"]["reused"] or ports["png"]["reused"] != 8
                or ports["png"]["fallbacks"] or any(k.endswith("fallback") for k in cairo)
                or any(cairo[k] != old_cairo[k] for k in ("native_residual_figures", "position_figures", "track_figures"))
                or cairo["ordinary_orbit_draws"][0]["figures"] != 4):
            raise ValueError("Saved publication differs from the full qualified physical reference")
        if mode == "election":
            counts = audit["audit"]["counts"]
            if (not audit["audit"]["admissible_source"] or counts["initial_success"] != 1
                    or counts["history_success"] != 1 or counts.get("projection_fallback", 0)):
                raise ValueError("The new port must execute in the ordinary signed solver")
        products.append(dict(terminal_sha256=receipt["terminal_sha256"], terminal=json.loads(terminal),
                             owners=actual["owner_maps"], ordered_count={a: len(r) for a, r in actual["owner_rows"].items()},
                             figures=actual["images"], sidecars=checks, election=audit["audit"],
                             installed=live["installed"], timings=live["timing"], prepare=ports["history"]["prepare"],
                             verified_tle_bytes=sum(ports["verified_tle"].values()), archive_port=ports["portable"]["attempts"]))
    write(root/"score.json", dict(binding=read(root/"binding.json"), request=request, through_exit=clocks,
                                  preparation_gains_s=preparation["preparation_cpu_gains_s"],
                                  products=dict(zip(MODES, products, strict=True)), waveform_reads=0, parity=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("detail")
    args = parser.parse_args()
    if args.action == "worker" and args.detail in MODES:
        worker(args.root, args.detail)
    elif args.action == "launch":
        paired(args.root, Path(args.detail))
    elif args.action == "score":
        score(args.root, json.loads(Path(args.detail).read_bytes()))
    else:
        parser.error("Unknown saved worker mode")
