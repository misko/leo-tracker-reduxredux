"""Prepare all actually accepted phase-guided factors for the saved 0049 science path."""

import argparse
import gzip
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from matched_donor_0049 import bind_derived  # noqa: E402
import matched_donor_0049_trial as trial  # noqa: E402
from directed_donor import NATIVE_WINDOW_PERIOD  # noqa: E402


ARTIFACT = HERE/"measurements/directed-replay-0049-ram-waveforms.json.gz"
WAVEFORM_PIN = "567e033f2b0a6a44bc9fcf472d5870920a7123733478decf25e1c44109bcd599"
QUERY_PIN = "0075e0f970a4e5debd2d9398603bd600cd5df38573898324ce4019ae2c3c09e9"
QUERY = Path("/dev/shm/leo-v3-directed-replay-0049-ram06/plan.json")
ORDINARY_WITNESS = (trial.CAMPAIGN/"cases/DS30-0049/successor/attempt-000002/publication"
                    /"exact-named-raw-witness.json")
VERIFY_FLAG_MARGIN = .025
ABI = ("candidate_rank","integer_epoch_sample","fractional_epoch_offset_samples","fractional_tracking_cfo_hz",
       "fractional_exact_score","fractional_control_score")
FACTOR_FIELDS = {*ABI,"fractional_margin","passed_fractional_margin_gate"}
EXPERIMENT = SimpleNamespace(stem="ds30-0049-directed-insertion",ledger="inserted",ledger_digest="insertion_sha256",
                             label="inserted",source=Path(__file__).name,priority="idle",joint=True,
                             transfer_sources=("empty_lane_directed_replay.py",))
signed = trial.authority


def full_native_factor(values):
    rank, integer, offset, hz, exact, control = values
    if (type(rank) is not int or rank != 0 or type(integer) is not int or not 0 <= integer < NATIVE_WINDOW_PERIOD
            or not all(type(item) in (int,float) and isfinite(item) for item in (offset,hz,exact,control))
            or exact < 0 or control < 0 or exact-control < VERIFY_FLAG_MARGIN):
        raise ValueError("A saved directed acceptance does not carry a complete gated native factor")
    return dict(zip(ABI,values,strict=True),fractional_margin=exact-control,passed_fractional_margin_gate=True)


def insert(original, plan, wave):
    from . import empty_lane_directed_replay as replay

    if (not wave["admitted"] or not wave["qualification"]["resident_source"] or wave["plan_sha256"] != QUERY_PIN
            or wave["verified_windows"] != replay.prefix.WINDOWS or plan["directed_library_sha256"] != replay.LIBRARY_PIN
            or wave["ordered_iq_sha256"] != signed.canonical(plan["original_source"]["window_hashes"])):
        raise ValueError("Use only the qualified verifier run over the exact original signed windows")
    source = signed.opportunities(original)
    if any(set(factor) != FACTOR_FIELDS for row in original["source"]["probes"] for factor in row["candidates"]):
        raise ValueError("The directed ABI and measured factor schema no longer agree")
    additions, records = {}, []
    for query,record in zip(plan["queries"],wave["rows"],strict=True):
        oid, visit, radio = query["id"],query["visit"],query["radio"]
        if record["id"] != oid or oid not in source or not 0 <= visit < replay.prefix.WINDOWS:
            raise ValueError("Directed acceptance left the original ordered six-member queries")
        lane = source[oid]
        probe = lane["row"]
        binding = [lane["counter"],probe["edge"],probe["channel"],probe["actual_rf_hz"]]
        if (not lane["short"] or lane["factor"] is not None or probe["candidates"]
                or lane["radio"] != radio or probe["visit_index"] != visit or probe["payload_start_sample"] != 200_000*visit
                or probe["probe_start_ms"] != 0 or probe["probe_index"] != 0
                or binding != plan["admitted_visits"][str(visit)]):
            raise ValueError("A directed query collides with an existing native factor or a different lane/time")
        observed = record["paths"]["interpolated"]
        if observed["stages"]["gates"] != 1 or observed["stages"]["refine_ns"] or observed["stages"]["cancellations"]:
            raise ValueError("The original directed scope is no longer the one-seed, no-refinement path")
        if observed["factor"] is None:
            continue
        if oid in additions or observed["stages"]["verifies"] != 1:
            raise ValueError("Expected each accepted independent fractional check exactly once")
        factor = full_native_factor(observed["factor"])
        additions[oid] = factor
        records.append(dict(observation_id=oid,visit=visit,radio=radio,counter=lane["counter"],edge=probe["edge"],
                            channel=probe["channel"],actual_rf_hz=probe["actual_rf_hz"],factor=factor,
                            directed_abi=list(observed["factor"])))
    if len(records) != 10 or len(plan["queries"]) != 117:
        raise ValueError("All and only the ten original accepted rows are enrolled")
    probes = [dict(lane["row"],candidates=[additions[oid]]) if oid in additions else lane["row"]
              for oid,lane in source.items()]
    recipe = dict(schema="private-ds30-0049-directed-native-insertion-v1",scope="physical saved intervention",
                  sparse_native_sha256=signed.canonical(original),directed_replay_sha256=WAVEFORM_PIN,
                  directed_query_sha256=QUERY_PIN,directed_library_sha256=replay.LIBRARY_PIN,
                  admitted_phase="interpolated",scope_members=replay.prefix.COUNT,unchanged_anchor_schedule=True,
                  insertion_sha256=signed.canonical(records))
    derived,custody = bind_derived(original,probes,recipe)
    after = signed.opportunities(derived)
    signed.bind_pair(original,derived,source,after)
    if list(after) != list(source) or any(after[oid]["row"] != expected
                                        for oid,expected in zip(source,probes,strict=True)):
        raise ValueError("The detector insertion changed another lane")
    return derived,dict(custody,inserted=records,unchanged_lanes=len(source)-len(records))


def winning_input(before,after,records):
    from leo.analysis.localization_v3 import tracks

    if Path(tracks.__file__).resolve() != signed.RELEASE/"src/leo/analysis/localization_v3/tracks.py":
        raise ValueError("The winning-observation check must use the installed released Graph module")
    ordinary,_ = tracks.winning_observations(before)
    updated,metadata = tracks.winning_observations(after)
    prior = {r["observation_id"]:r for r in ordinary}
    expected = {r["observation_id"]:r for r in records}
    corrected = {r["observation_id"]:r for r in updated}
    if (prior.keys() & expected.keys() or corrected.keys()-prior.keys() != expected.keys()
            or [r for r in updated if r["observation_id"] not in expected] != ordinary
            or len(ordinary) != 600 or len(updated) != 610):
        raise ValueError("The released Graph port did not preserve every ordinary observation row")
    source = before["source"]
    receivers = sorted({p["receiver_id"] for p in source["probes"]})
    for oid,r in expected.items():
        c = r["factor"]
        time = (r["counter"]-before["clock_anchor"]["sample_counter"])/source["sample_rate_hz"]+source["probe_ms"]*.0005
        row = dict(observation_id=oid,receiver=receivers.index(r["radio"])+1,native_receiver_id=r["radio"],
                   channel=r["channel"],time_s=time,measured_cfo_hz=c["fractional_tracking_cfo_hz"],
                   actual_rf_hz=r["actual_rf_hz"],fractional_margin=c["fractional_margin"])
        if corrected[oid] != row:
            raise ValueError("The released Graph signs, time, RF or mark differ from the directed admission")
    return dict(original_rows=len(ordinary),corrected_rows=len(updated),original_rows_sha256=signed.canonical(ordinary),
                corrected_rows_sha256=signed.canonical(updated),archive_cutoff_ns=metadata["causal_cutoff_utc_ns"])


def prepare(root):
    from . import empty_lane_directed_replay as replay

    if root.exists() or root.parent != Path("/dev/shm"):
        raise ValueError("Expect one new private tmpfs preparation")
    def needs_candidate_only(event,params):
        is_ordinary_successor = (event == "open" and isinstance(params[0],(str,bytes))
                                 and Path(os.fsdecode(params[0])).resolve() == ORDINARY_WITNESS)
        replay.forbid_source(event,params,prediction=not is_ordinary_successor)

    sys.addaudithook(needs_candidate_only)
    capture,result,_ = replay.candidate_inputs()
    if capture["native_sha256"] != signed.canonical(result):
        raise ValueError("Require the signed whole candidate native packet")
    plan = replay.prefix.read(QUERY,QUERY_PIN)
    if (capture["raw_identity"] != plan["original_source"]["authority"]
            or plan["arrival_proof"]["candidate_sha256"] != capture["native_sha256"]):
        raise ValueError("The original replay was on another capture or detector packet")
    body = gzip.decompress(ARTIFACT.read_bytes())
    if sha256(body).hexdigest() != WAVEFORM_PIN:
        raise ValueError("The exact physical directed replay receipt is required")
    derived,change = insert(result,plan,json.loads(body))
    graph = winning_input(result,derived,change["inserted"])
    if graph["archive_cutoff_ns"] != capture["raw_identity"]["causal_cutoff_utc_ns"]:
        raise ValueError("The Graph boundary changed the enrolled causal cutoff")
    original = trial.ordinary(trial.STAGE)
    stage = trial.document(trial.STAGE/"native.json",original["admission"]["native_pin"])
    if capture["native_sha256"] != original["terminal"]["native_sha256"] or stage != result:
        raise ValueError("The comparator must be the exact archived ordinary whole-packet publication")
    root.mkdir(mode=0o700)
    detector = root/"derived-native.json"
    detector.write_text(json.dumps(derived,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":")))
    detector.chmod(0o400)
    if "sha256:"+trial.identifier(detector) != change["derived_native_sha256"]:
        raise ValueError("Corrected detector differs from its canonical registered bytes")
    print(trial.write(root/"plan.json",dict(case=trial.CASE,protocol=trial.protocol(EXPERIMENT),
          worker=trial.identifier(Path(trial.__file__)),sources=trial.source_pins(EXPERIMENT),
          archived_parity=original["parity"],original_native_sha256=capture["native_sha256"],
          installed_native_sha256=None,original_archive=capture["raw_identity"]["archive_sha256"],
          original_offer=capture["raw_identity"]["region_sha256"],
          original_terminal=original["witness"]["evidence"]["detail"]["terminal_sha256"],
          original_saved_clock=original["timed_saved_clock"],change=change,graph_input=graph,
          survey_reads=0,installed_detector_reads=0,waveform_reads=0,numerical_runs=0)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action",choices=("prepare","preflight","worker"))
    cli.add_argument("root",type=Path)
    cli.add_argument("--pin")
    cli.add_argument("--lease-fd",type=int)
    args = cli.parse_args()
    if args.action == "prepare":
        prepare(args.root)
    elif args.pin is None:
        cli.error("A sealed plan pin is required")
    elif args.action == "preflight":
        trial.worker(args.root,args.pin,EXPERIMENT,smoke=True)
    elif args.lease_fd is None:
        cli.error("Use the separately authorized shared lease")
    else:
        trial.worker(args.root,args.pin,EXPERIMENT,lease_fd=args.lease_fd)
