"""Publish the frozen DS30-0212 moment-preserving CFO treatment through the normal saved port."""

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from math import fsum, isfinite
import os
from pathlib import Path
from shutil import copytree
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from numpy.polynomial.legendre import legder, legval, legvander


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import masked_cfo_next_two_replay as replay  # noqa: E402
import masked_cfo_saved as graph_overlay  # noqa: E402
from masked_cfo_next_two_replay import capsule, held, saved, scoring, signed  # noqa: E402


CASE = "DS30-0212"
ORIGINAL = Path("/dev/shm/leo-v3-mask-cfo-next-two01/DS30-0212")
ORIGINAL_CLOSURE = "b7baaa38ae42e3014a8d91a6f777a4652d005c85bd03e08b905b272bec068ccf"
ORDINARY_GATE = "ca0c10e336ca03e23787652c1a9c35ff60fc26d152de51cb87bfe544c1562ad2"
DEVELOPMENT_NAME = "moment-preserving-cfo-development.json"
DEVELOPMENT = "6779a1b444a1b0de3e963f4ad60f1c04e309aee0d637e1682c7e4254dcee2c11"
PROJECTION = HERE/"moment_preserving_cfo.py"
PROJECTION_PIN = "f9e0836f40c03a7fa5f20a19a34ac1bcf67f632b830271ef43f0809f3ef8b982"
RULE = HERE/"moment-preserving-cfo-protocol.md"
RULE_PIN = "843795f7ff776ce6e53f65a978f6b4cdb9782532b94948242aa5b810429a485f"
HANDOFF = HERE.parents[3]/"moment-preserving-cfo-handoff/DS30-0212-projected-cfo.json"
HANDOFF_PIN = "46b1d5968bc7b5a7064ee87ab69bfb4a19b98162a60aa809f43899ed73495660"
WORKER = Path(__file__).resolve()
LIMIT = 21


def development():
    book = saved.document(HERE/"measurements"/DEVELOPMENT_NAME, DEVELOPMENT)
    if (book["source_sha256"] != PROJECTION_PIN or book["protocol_sha256"] != RULE_PIN
            or saved.identifier(PROJECTION) != PROJECTION_PIN or saved.identifier(RULE) != RULE_PIN
            or book["cases"][CASE]["binding"]["closure_sha256"] != ORIGINAL_CLOSURE):
        raise ValueError("The checked prospective projection source, rule or closed development input changed")
    return book


def projector(feature):
    from empty_bootstrap import load_definitions

    # Load only the three exact candidate-only arithmetic functions. The
    # development tool's installed-carrier and cross-case scorer stays offline.
    namespace = dict(np=np, EPS=np.finfo(float).eps, legder=legder, legval=legval, legvander=legvander,
        Counter=Counter, fsum=fsum, residual=SimpleNamespace(BIN_HZ=feature.BIN_HZ,
            finite_hz=lambda value:type(value) in (int,float) and isfinite(value), digest=signed.canonical))
    load_definitions(PROJECTION.read_bytes(), str(PROJECTION), ("basis", "project", "project_tracks"), namespace)
    return namespace["project_tracks"]


def formed_features(native, config, feature, ordinary_graph, report):
    book = development()
    expected = book["cases"][CASE]
    if signed.canonical(native) != expected["binding"]["ordinary_native_sha256"]:
        raise ValueError("The projected development trial requires its original saved native packet")
    project = projector(feature)
    start = graph_overlay.clock()
    proposals = feature.derive(native,config)
    masked_clock = graph_overlay.elapsed(start)
    if signed.canonical(proposals.edits) != expected["binding"]["edits_sha256"]:
        raise ValueError("The released held-odd half-blend admission changed")
    start = graph_overlay.clock()
    ordinary = ordinary_graph(native,config)
    ordinary_clock = graph_overlay.elapsed(start)
    graph = dict(tracks=len(ordinary["tracks"]),assigned=ordinary["graph_points"])
    if graph != expected["graph"]:
        raise ValueError("The ordinary Graph regrouped the projection's frozen support")
    start = graph_overlay.clock()
    revised, proof = project(ordinary,proposals.edits)
    projection_clock = graph_overlay.elapsed(start)
    if (set(revised) != set(proposals.edits) or signed.canonical(revised) != expected["projected_cfo_sha256"]
            or any(proof[key] != expected[key] for key in ("projected_cfo_sha256", "membership_sha256",
                    "track_moment_ledger_sha256", "surviving_edits", "original_edits", "exact_mask_sha256"))):
        raise ValueError("The projected CFO values, edit support or moment certificate differ from the sealed development result")
    report.update(projection_source_sha256=PROJECTION_PIN, development_sha256=DEVELOPMENT, ordinary_graph=graph,
        projection=proof, clocks=dict(held_odd_proposals=masked_clock, ordinary_graph=ordinary_clock,
                                       projection=projection_clock))
    return replace(proposals,edits={oid:dict(edit,updated_hz=revised[oid]) for oid,edit in proposals.edits.items()})


def attach_projected(original, native, audit, *, probe=False):
    if probe:
        raise ValueError("The numerical treatment requires the normal whole saved Graph entry")
    original_bind = graph_overlay.bind_graph
    projection = audit.setdefault("moment_preserving",{})

    def bind(app, tracks, feature, config, document, graph_audit, **kwargs):
        ordinary_graph = tracks.prepare_tracks
        adapt = SimpleNamespace(identity=feature.identity, apply_to_winners=feature.apply_to_winners,
            derive=lambda current,approved: formed_features(current,approved,feature,ordinary_graph,projection))
        return original_bind(app,tracks,adapt,config,document,graph_audit,**kwargs)

    with patch.object(graph_overlay,"bind_graph",bind):
        return original(native,audit)


def experiment(*, probe):
    obj = replay.experiment(probe=probe)
    obj.stem = "ds30-0212-moment-preserving-publication"
    obj.source = WORKER.name
    obj.transfer_sources += ("moment_preserving_cfo.py", "moment-preserving-cfo-protocol.md",
                             "measurements/"+DEVELOPMENT_NAME)
    return obj


@contextmanager
def ports():
    with replay.ports(replay.cases()[CASE]), patch.object(held,"experiment",experiment), patch.multiple(
            capsule, WORKER=WORKER,TIMEOUT=LIMIT):
        yield


def readback(native):
    if 2 in os.sched_getaffinity(0):
        raise ValueError("The exact independent projection readback must exclude the benchmark core")
    sys.path.insert(0,str(replay.RELEASE_SRC))
    from leo.analysis.localization_v3 import tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from reports.ALGO08.v3 import held_cfo_features as feature

    book = development()
    for path,pin in ((Path(feature.__file__),graph_overlay.FEATURE_PIN),
                    (Path(tracks.__file__),"db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f"),
                    (replay.RELEASE_SRC/"leo/analysis/tracklet_fitting.py",book["tracklet_source_sha256"])):
        if saved.identifier(path) != pin:
            raise ValueError("Expected the unchanged released Graph sources")
    config = TrackConfig(**saved.document(replay.RELEASE_SRC.parent/"assets/tracks.json",graph_overlay.CONFIG_PIN)["config"])
    result = {}
    projected = formed_features(native,config,feature,tracks.prepare_tracks,result)
    handoff = saved.document(HANDOFF,HANDOFF_PIN)
    edits = handoff["edits"]
    if (handoff["case"] != CASE or handoff["development_receipt_sha256"] != DEVELOPMENT
            or handoff["rule_protocol_sha256"] != RULE_PIN or handoff["prior_native_sha256"] != signed.canonical(native)
            or handoff["projected_cfo_sha256"] != result["projection"]["projected_cfo_sha256"]
            or handoff["projected_winner_ledger_sha256"] != signed.canonical(edits)
            or {oid:{k:v for k,v in row.items() if k != "prior_updated_hz"} for oid,row in edits.items()} != projected.edits):
        raise ValueError("The independently sealed projected winner ledger differs from exact CPU3 formation")
    result["independent_edit_handoff_sha256"] = HANDOFF_PIN
    return result


def prepare(root):
    if root.parent != Path("/dev/shm") or root.resolve() != root or root.exists():
        raise ValueError("Use a fresh direct private tmpfs output")
    expected = development()["cases"][CASE]
    pins = saved.document(ORIGINAL/"verification-pins.json",ORIGINAL_CLOSURE)
    state = replay.status(replay.cases()[CASE])
    replay.field_authority(replay.cases()[CASE],state)
    gate = saved.document(ORIGINAL/"ordinary-gate.json",ORDINARY_GATE)
    if (gate["ordinary"] != pins["ordinary"] or gate["field_pair"] != state["pair_sha256"]
            or saved.document(ORIGINAL/"ordinary-parity.json",gate["parity"])["exact_ordinary_scientific_parity"] is not True):
        raise ValueError("The archived ordinary publication has not passed exact field parity")
    original = saved.document(ORIGINAL/"corrected/plan.json",pins["corrected"]["plan"])
    native = saved.document(ORIGINAL/"corrected/derived-native.json",expected["binding"]["ordinary_native_sha256"])
    cpu3 = readback(native)
    root.mkdir(mode=0o700)
    stage, cell, control = root/"stage", root/"corrected", root/"ordinary"
    cell.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    for name in ("plan.json", "clock.json", "masked-cfo-observation-witness.json", "receipt.json",
                 "worker-isolation.json", "owner-residuals.json", "owner-residual-export-clock.json", "worker-resource.txt"):
        os.link(ORIGINAL/"ordinary"/name,control/name)
    copytree(ORIGINAL/"ordinary/substituted",control/"substituted",copy_function=os.link,symlinks=True)
    for name in ("ordinary-gate.json", "ordinary-parity.json"):
        os.link(ORIGINAL/name,root/name)
    for name in ("derived-native.json", "admission.json"):
        os.link(ORIGINAL/"corrected"/name,cell/name)
    source = Path(original["stage"])
    copytree(source,stage,copy_function=os.link,symlinks=False)
    spec = experiment(probe=False)
    plan = saved.write(cell/"plan.json",dict(original,stage=str(stage),protocol=saved.protocol(spec),
        sources=saved.source_pins(spec),projection_development_sha256=DEVELOPMENT))
    with ports():
        ready = capsule.preflight(cell,plan,"corrected",replay.OBSERVER_PIN)
    return saved.write(root/"projection-ready.json",dict(plan=plan,ordinary_gate=ORDINARY_GATE,capsule_ready=ready,
        development_sha256=DEVELOPMENT,source_sha256=saved.identifier(WORKER),cpu3_exact_readback=cpu3))


def child(cell, pin, *, probe_only):
    original = graph_overlay.attach
    with ports(), patch.object(graph_overlay,"attach",lambda native,audit,probe=False:
            attach_projected(original,native,audit,probe=probe)):
        capsule.child(cell,pin,"corrected",probe_only=probe_only)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("prepare","watch","child","score"))
    cli.add_argument("root",type=Path)
    cli.add_argument("--pin")
    cli.add_argument("--cell",choices=("corrected",))
    cli.add_argument("--driver-pid",type=int)
    cli.add_argument("--probe-only",action="store_true")
    args = cli.parse_args()
    if args.mode == "child" and args.pin and args.cell:
        child(args.root,args.pin,probe_only=args.probe_only)
        return 0
    sys.addaudithook(saved.deny_backing)
    if args.mode == "prepare":
        output = prepare(args.root)
    elif args.mode == "watch" and args.pin and args.driver_pid:
        ready = saved.document(args.root/"projection-ready.json",args.pin)
        if ready["source_sha256"] != saved.identifier(WORKER) or ready["development_sha256"] != DEVELOPMENT:
            raise ValueError("Require the frozen inspected projection and isolated entry")
        with ports():
            output = capsule.watch(args.root,"corrected",args.driver_pid,ready["capsule_ready"],ready["ordinary_gate"])
    elif args.mode == "score" and args.pin:
        closed = saved.document(args.root/"pair-verified-before-survey.json",args.pin)
        pins = saved.document(args.root/"verification-pins.json",closed["closure_sha256"])
        if pins["ordinary"] != saved.document(ORIGINAL/"verification-pins.json",ORIGINAL_CLOSURE)["ordinary"]:
            raise ValueError("The matched archived ordinary control changed")
        with ports():
            return scoring.verify(args.root,pins)
    else:
        cli.error("Require a pinned readiness or scientific closure")
    if isinstance(output,int):
        return output
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
