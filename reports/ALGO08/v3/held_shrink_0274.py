"""Prepare both DS30-0274 cells from authenticated, resident saved sources."""

import argparse
from collections import Counter
from functools import partial
import json
import os
from pathlib import Path
from shutil import copyfile
import sys
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import held_shrink_0019_ram as ram  # noqa: E402
from held_shrink_0019 import FORECAST, SOURCE, ready_runtime, signed, splice, trial  # noqa: E402


CASE = "DS30-0274"
BLOCK = Path("/dev/shm/leo-v3-held-shrink-0274-stage02")
STAGE = BLOCK/"stage"
BASE = trial.CAMPAIGN/"cases"/CASE
PAIR = "7e2e78392701820e6a2667adc6ba6f2dfbfec1f7eb1ee5017d50a775b773c28c"
AUTHORITY = "f000df68f800788d0552aa05c8893b29610f6788ffc15dd72f4f32daf8ec42b3"
WITNESS = "9627f7d701ae182ba8df387692963f1e91b9f6683cd6e6e7ec58d7cfa6810499"
NATIVE = "e0dace78ca3e31c9329ead12eea3c62853de3a7c6c44dff3c70802764adf76b5"
DONORS = tuple(Path("/dev/shm")/name for name in (
    "leo-v3-unseen-saved-0255-result01", "leo-v3-nomination-handoff-0289-local01",
    "leo-v3-saved-0402-pair-01",
))
OFFER = Path("/dev/shm/leo-v3-cfo-epoch-0019-saved01/offer.json")
REFS = 48
CELLS = ("ordinary", "half-blend")
EXPERIMENT = SimpleNamespace(
    stem="held-shrink-0274", source=Path(__file__).name, joint=True,
    ledger="edits", ledger_digest="edit_sha256", priority="idle",
    transfer_sources=("held_shrink_0019.py", "held_short_cfo_shrink.py", "odd_short_interpolation.py"),
)


def archived():
    pair = trial.document(BASE/"pair.json", PAIR)
    authority = trial.document(BASE/"authority.json", AUTHORITY)
    if pair["authority_sha256"].removeprefix("sha256:") != AUTHORITY or not pair["verified_pair"]:
        raise ValueError("The ordinary scientific publication must be a verified original pair")
    root = BASE/"successor"/f"attempt-{pair['generation']:06d}"
    result = trial.document(root/"result.json", pair["attempt_result_sha256"]["successor"])
    witness = trial.document(root/"publication/exact-named-raw-witness.json", WITNESS)
    if (result["native_sha256"] != "sha256:"+NATIVE or result["raw_identity"] != authority
            or result["outcome"] != "complete" or result["process"]["exit_code"]
            or witness["evidence"]["detail"]["input_sha256"] != "sha256:"+NATIVE):
        raise ValueError("The original successor science and input custody differ")
    return pair, authority, root/"publication", result, witness


def resident_catalogue(required, cutoff, pin):
    """Resolve a unique full signed contiguous view from the sealed local inventories."""
    local = {}
    fsid = os.statvfs("/dev/shm").f_fsid
    for donor in DONORS:
        root = donor/"tle/archive/space-track"
        if root.resolve(strict=True) != root or os.statvfs(root).f_fsid != fsid:
            raise ValueError("A catalogue donor is outside the enrolled tmpfs")
        for source in sorted(root.iterdir()):
            if source.suffix == ".tle" and int(source.name.split("-", 1)[0]) < cutoff:
                if source.is_symlink() or not source.is_file():
                    raise ValueError("Resident body metadata contains an indirect source")
                local.setdefault(source.name, source)
    names = sorted(local)
    views = []
    for start in range(len(names)-REFS+1):
        window = names[start:start+REFS]
        if not required <= set(window):
            continue
        digest = {name:name.split("-", 1)[1].removesuffix(".tle") for name in window}
        if signed.canonical(digest) == pin:
            views.append(digest)
    if len(views) != 1:
        raise ValueError("The exact complete original causal view is absent or ambiguous")
    view, = views
    trial.require_resident([local[name] for name in view])
    if any(trial.identifier(local[name]) != digest for name,digest in view.items()):
        raise ValueError("The staged bytes differ from their signed causal names")
    return view, {name:local[name] for name in view}


def copy_checked(source, target, pin):
    if trial.identifier(source) != pin.removeprefix("sha256:"):
        raise ValueError(f"Original source digest mismatch at {source.name}")
    copyfile(source, target)
    target.chmod(0o400)
    trial.document(target, pin)


def prepare():
    from reports.ALGO08.v3 import held_short_cfo_shrink as frozen

    sys.addaudithook(trial.deny_backing)
    pair, authority, original, raw, witness = archived()
    if BLOCK.exists() or trial.identifier(Path(frozen.__file__)) != SOURCE:
        raise ValueError("Expect one exact frozen forecast and fresh private stage")
    view, bodies = resident_catalogue(set(witness["ports"]["verified_tle"]), authority["causal_cutoff_utc_ns"],
                                      authority["archive_sha256"])
    request = trial.document(BASE/"input.json")
    offer = trial.document(OFFER, authority["region_sha256"])
    if request["offered_region"] != offer:
        raise ValueError("Expected the authentic signed offered region")
    native = signed.read_native(original, raw["native_sha256"])
    forecast = signed.document(HERE/"measurements/held-short-cfo-shrink-prediction.json.gz", FORECAST)["cases"][CASE]
    masked, held, modes = frozen.odd.mask(native)
    if (forecast["native_sha256"] != raw["native_sha256"] or forecast["original_pair"] != signed.canonical(pair)
            or forecast["masked_sha256"] != signed.canonical(masked) or forecast["native_calls"] != modes
            or forecast["held_order_sha256"] != signed.canonical(list(held))):
        raise ValueError("The raw publication differs from the sealed masked input")
    eligible, gates = frozen.nominate_changes(held, signed.opportunities(native), forecast["forecasts"])
    if (eligible != forecast["eligible"] or gates != forecast["residual_gates"] or len(eligible) != 499
            or any(edit["updated_hz"] == edit["original_hz"] for edit in eligible.values())):
        raise ValueError("The exact 499 nonzero changes did not reproduce")
    derived, change = splice(native, eligible, schema="private-0274-held-cfo-shrink-v1")
    rows = signed.opportunities(derived)
    if any(frozen.arrival_phase(rows[key]["counter"], rows[key]["factor"]) != edit["arrival"]
           for key,edit in eligible.items()):
        raise ValueError("The saved perturbation changed original arrival")
    BLOCK.mkdir(mode=0o700)
    STAGE.mkdir()
    archive = STAGE/"tle/archive/space-track"
    archive.mkdir(parents=True)
    for name, source in bodies.items():
        os.link(source, archive/name)
    catalogue_pin = trial.write(STAGE/"catalogue.json", view)
    copy_checked(BASE/"authority.json", STAGE/"authority.json", AUTHORITY)
    copy_checked(OFFER, STAGE/"offer.json", authority["region_sha256"])
    inventory = authority["session_id"]+".json"
    copy_checked(original/"fast-scan-inputs"/inventory, STAGE/"inventory.json", authority["inventory_sha256"])
    admission_pin = trial.write(STAGE/"admission.json", dict(case=CASE, native_pin=NATIVE, authority_pin=AUTHORITY))
    original_recipe = dict(sparse_native_sha256=raw["native_sha256"], edit_sha256=signed.canonical([]))
    original_change = dict(recipe_sha256=native["provenance"]["detector_sha256"], recipe=original_recipe, edits=[],
                           derived_native_sha256=raw["native_sha256"])
    for cell, packet, delta in zip(CELLS, (native, derived), (original_change, change), strict=True):
        root = BLOCK/cell
        root.mkdir(mode=0o700)
        native_file = root/"derived-native.json"
        native_file.write_bytes(json.dumps(packet, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                           separators=(",", ":")).encode())
        native_file.chmod(0o400)
        trial.document(native_file, delta["derived_native_sha256"])
        copy_checked(STAGE/"admission.json", root/"admission.json", admission_pin)
        pin = trial.write(root/"plan.json", dict(case=CASE, cell=cell, protocol=trial.protocol(EXPERIMENT),
            worker=trial.identifier(Path(trial.__file__)), sources=trial.source_pins(EXPERIMENT), change=delta,
            original_native_sha256=raw["native_sha256"], installed_native_sha256=None,
            original_archive=authority["archive_sha256"], catalogue_pin=catalogue_pin, admission_sha256=admission_pin))
        print(cell, trial.write(root/"ready.json", dict(plan_sha256=pin, input=delta["derived_native_sha256"])))
    trial.write(BLOCK/"custody.json", dict(
        native_sha256=raw["native_sha256"], archive=authority["archive_sha256"], catalogue_pin=catalogue_pin,
        cutoff=authority["causal_cutoff_utc_ns"], donor_counts=dict(Counter(str(p.parents[3]) for p in bodies.values())),
        refs=REFS, frozen_edits=len(eligible), edited_radios=change["changed_by_radio"], masks_verified=True,
        verification_scope="original published control and exact local stage metadata",
    ))


def run_worker(cell, pin, *, smoke=False, fd=None):
    root = BLOCK/cell
    plan = trial.document(root/"plan.json", pin)
    trial.worker(root, pin, EXPERIMENT, smoke=smoke, lease_fd=fd,
                 enrollment=(CASE, STAGE, plan["admission_sha256"], REFS),
                 admission_path=root/"admission.json", original_control=cell == "ordinary")


def capsule(cell, mode):
    root = BLOCK/cell
    ready_body = root/"ready.json"
    ready = trial.document(ready_body)
    plan = trial.document(root/"plan.json", ready["plan_sha256"])
    output_root = BLOCK/f"{cell}-capsule"
    ports = SimpleNamespace(trial=trial, CASE=CASE, ROOT=root, STAGE=STAGE, AUTHORITY=AUTHORITY,
                            CATALOGUE=plan["catalogue_pin"], ready_runtime=ready_runtime,
                            run_worker=partial(run_worker, cell), EXPERIMENT=EXPERIMENT)
    with patch.multiple(ram, ROOT=output_root, OUTPUT=output_root/"output", PROOF=output_root/"verified-isolation.json",
                        PLAN=ready["plan_sha256"], READY=trial.identifier(ready_body), saved=ports,
                        __file__=__file__, MODE_ARGS=("--cell",cell), EXTRA_FILE_NAMES=("ready.json",)):
        if mode == "capsule-prepare":
            ram.prepare()
            copy_checked(ready_body, output_root/"output/ready.json", trial.identifier(ready_body))
        elif mode == "preflight":
            ram.preflight(changed=0 if cell == "ordinary" else 499, refs=REFS)
        else:
            ram.isolated(mode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "capsule-prepare", "preflight", "sandbox-preflight", "sandbox-worker"))
    parser.add_argument("--cell", choices=CELLS)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.cell:
        capsule(args.cell, args.action)
    else:
        parser.error("A capsule requires the enrolled cell")
