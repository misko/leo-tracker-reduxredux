"""Lock metadata-only original-detector dwell schedules and replay causal prefixes."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import monotonic

from .. import corpus, whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import capture_bursts, channel_dwell
from . import capture_bursts_trial, channel_dwell_worker, support_cross_trial
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, _sha
from .portable_gate_trials import compressed_rows

PARENT = capture_bursts_trial.REPORT
REPORT = PARENT.with_name("channel-dwell")
REPLAY = {"DS26-0164": 8, "DS29-0357": 9}
MODES = channel_dwell.MODES
SALT = "channel-dwell-roofs-v1"
read = whole_iq.read


def candidate(ident):
    case, request = whole_iq.binding(ident)
    native = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    document = read(native)
    ordinary = document["source"]
    if (
        ordinary["session_id"],
        ordinary["sample_rate_hz"],
        ordinary["probe_ms"],
        document["provenance"]["run_id"],
    ) != (case["session_id"], 10_000_000, 20, case["run_id"]):
        raise ValueError("original capture lacks the required physical geometry or lineage")
    metadata = capture_bursts.inventories(document)
    lane = channel_dwell.primary_channel(ident)
    schedules = {mode: channel_dwell.schedule(metadata, lane, mode) for mode in MODES}
    return case, request, native, document, metadata, lane, schedules


def choose(panel):
    ids = set(corpus._selection(panel)[0]) - REPLAY.keys() - capture_bursts_trial.EXCLUDED
    if panel == "roof16":
        ids = {i for i in ids if i.startswith("DS29-")}
    order = sorted(ids, key=lambda ident: sha256(f"{SALT}:{ident}".encode()).digest())
    rejects = []
    for ident in order:
        try:
            return candidate(ident), dict(ranking=order, rejections=rejects)
        except (KeyError, OSError, ValueError) as error:
            rejects.append(dict(id=ident, reason=str(error)))
    raise ValueError("no eligible additional archive recording")


def stage(work, cpu, order, receiver, source):
    case, parent, native, doc, metadata, lane, schedules = source
    ident = case["id"]
    files = []
    for name in order:
        workdir = work / ident / name
        folder = workdir / "recording"
        folder.mkdir(parents=True, exist_ok=False)
        factor, request = folder / "native.json", folder / "request.json"
        selected = schedules.get(name)
        if selected is None:
            write(factor, native.read_bytes())
            payload = doc
            picked = set(v for v, _ in metadata)
        else:
            lineage = whole_iq.recording.digest(
                ["channel-dwell/v1", name, case["native"]["sha256"], selected]
            )
            payload = channel_dwell.prefix(doc, selected, lineage)
            write(factor, encoded(payload) + b"\n")
            picked = set(selected)
        outcome = whole_iq.recording.bind_request(case, factor, request)["native_sha256"]
        verify_request(read(request), parent, native_path=factor, native_sha256=outcome)
        save_json(workdir / "plan.json", dict(receiver=str(Path(channel_dwell_worker.__file__))))
        save_json(workdir / "raw.json", dict(native_sha256=outcome, request_sha256=_sha(request)))
        write(workdir / "receiver-path.txt", (receiver + "\n").encode())
        files.append(
            dict(
                id=ident,
                condition=name,
                method="channel_dwell_" + name,
                mode="matched-tile",
                cohort="burst-replication" if ident in REPLAY else "additional-archive",
                cpu=cpu,
                native_sha256=outcome.removeprefix("sha256:"),
                prepared_request_sha256=_sha(request),
                paired_capture_sha256=case["native"]["sha256"],
                original_request_sha256=case["request"]["sha256"],
                catalog_sha256=case["catalog"]["sha256"],
                tile=dict(
                    center=parent["job"]["search_center"], screen=parent["job"]["screen_center"]
                ),
                calls=len(picked),
                by_channel=dict(Counter(c for v, c in metadata if v in picked)),
                final_sample_counter=payload["last_sample_counter"],
                frontier_visits=len(payload["delivery_clocks"]),
                original_valid_visits=len(metadata),
                primary_channel=lane,
            )
        )
    return files


def run(work):
    if (REPORT / "plan.json").is_file():
        raise FileExistsError("the dwell plan already exists")
    work.mkdir(exist_ok=False)
    preceding = read(support_cross_trial.checked(PARENT, "plan.json"))
    receiver = preceding["receiver"]
    if whole_iq.receiver_identity(Path(receiver)) != preceding["receiver_files"]:
        raise ValueError("installed phase release changed from original burst study")
    fixed = [candidate(ident) for ident in REPLAY]
    extra, ranking = zip(*(choose(p) for p in ("ds26-common127", "roof16")), strict=True)
    roster, tasks, schedules = {}, [], {}
    for i, cpu in enumerate((8, 9)):
        order = MODES if cpu == 8 else MODES[::-1]
        for values, replay in ((fixed[i], True), (extra[i], False)):
            ident = values[0]["id"]
            roster[ident] = cpu
            schedules[ident] = values[-1]
            tasks.extend(stage(work, cpu, order if replay else (*order, "full"), receiver, values))
    save_json(REPORT / "schedule.json", schedules)
    paths = (
        Path(__file__),
        Path(channel_dwell.__file__),
        Path(channel_dwell_worker.__file__),
        Path(support_cross_trial.__file__),
        PARENT / "prediction-lock.json",
        REPORT / "PROTOCOL.md",
        REPORT / "schedule.json",
    )
    save_json(
        REPORT / "plan.json",
        dict(
            cases=roster,
            tasks=tasks,
            receiver=receiver,
            receiver_files=preceding["receiver_files"],
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            cap_s=support_cross_trial.LIMIT,
            additional_ranking=list(ranking),
            files={str(p.relative_to(ROOT)): _sha(p) for p in paths},
        ),
    )
    print(
        "sealed",
        roster,
        [(r["id"], r["primary_channel"]) for r in tasks if r["condition"] == "dwell96"],
        flush=True,
    )

    def lane(cpu):
        output = []
        for row in tasks:
            if row["cpu"] != cpu:
                continue
            r = support_cross_trial.service(work, row)
            audit = work / row["id"] / row["condition"] / "geometry.json"
            r["geometry"] = read(audit) if audit.is_file() else None
            output.append(r)
        return output

    start = monotonic()
    with ThreadPoolExecutor(2) as pool:
        rows = [r for group in pool.map(lane, (8, 9)) for r in group]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(rows))
    names = ("plan.json", "schedule.json", "predictions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(roster),
            attempted=len(rows),
            elapsed_s=monotonic() - start,
            files={n: _sha(REPORT / n) for n in names},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
