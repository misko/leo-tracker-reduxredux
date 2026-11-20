"""Lock metadata-only detector assignments and replay complete mixed factors."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, process_time_ns

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import mixed_duty, selective_capture
from . import margin_admission_inputs as wide_inputs
from . import support_cross, support_cross_trial
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, _sha
from .portable_gate_trials import compressed_rows

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-frontier/mixed-duty"
CASES = ("DS26-0036", "DS29-0082", "DS26-0014", "DS29-0127")
LANES = {6: ("DS26-0014", "DS26-0036"), 7: ("DS29-0127", "DS29-0082")}
METHODS = mixed_duty.METHODS
read = wide_inputs.read


def visit_metadata(document):
    pairs = selective_capture.visit_pairs(document["source"]["probes"])
    output = []
    for visit, (left, right) in pairs:
        if left["channel"] != right["channel"] or left["actual_rf_hz"] != right["actual_rf_hz"]:
            raise ValueError("routing requires a single physical RF lane per stereo visit")
        output.append((visit, left["channel"]))
    if len(output) != document["provenance"]["processed_windows"]:
        raise ValueError("native input lacks the complete admitted stereo inventory")
    return output


def freeze(work):
    if (REPORT / "selection-lock.json").exists():
        raise FileExistsError("assignments were already frozen")
    work.mkdir(exist_ok=False)
    source = read(support_cross_trial.checked(wide_inputs.WIDE, "source-lock.json"))
    receiver = source["receiver"]
    if whole_iq.receiver_identity(Path(receiver)) != source["receiver_files"]:
        raise ValueError("installed phase release differs from immutable wide source")
    bindings = {}
    for ident in CASES:
        raw, document, binding = wide_inputs.load(ident)
        target = work / (ident + "-wide.json")
        write(target, raw)
        inventory = visit_metadata(document)
        decisions, cpu_ms = {}, {}
        for mode in METHODS:
            start = process_time_ns()
            decisions[mode] = list(mixed_duty.route(inventory, mode))
            cpu_ms[mode] = (process_time_ns() - start) / 1e6
        bindings[ident] = dict(
            binding, visits=len(inventory), decisions=decisions, selector_cpu_ms=cpu_ms
        )
    dependencies = (
        Path(__file__),
        Path(mixed_duty.__file__),
        Path(selective_capture.__file__),
        Path(support_cross.__file__),
        Path(support_cross_trial.__file__),
        REPORT / "PROTOCOL.md",
        wide_inputs.WIDE / "prediction-lock.json",
    )
    lock = dict(
        cases=bindings,
        receiver=receiver,
        receiver_files=source["receiver_files"],
        sources={str(p.relative_to(ROOT)): _sha(p) for p in dependencies},
        period=mixed_duty.PERIOD,
        wait=mixed_duty.LAST_OFFSET,
    )
    save_json(REPORT / "selection-lock.json", lock)
    return lock


def treatment(work, cpu, ident, selection):
    entry = selection["cases"][ident]
    case, parent = whole_iq.binding(ident)
    if any(
        (
            case[x]["sha256"] != entry[y]
            for x, y in (
                ("request", "capture_request_sha256"),
                ("native", "capture_native_sha256"),
                ("catalog", "catalogue_sha256"),
            )
        )
    ):
        raise ValueError("capture-era request differs from the matched wide factor authority")
    wide = read(whole_iq.checked(work / (ident + "-wide.json"), entry["wide_native_sha256"]))
    capture = read(whole_iq.checked(BULK / case["native"]["path"], entry["capture_native_sha256"]))
    selective_capture.same_support(wide, capture)
    support_cross.join(wide, capture)
    left, right = (d["source"]["probes"] for d in (wide, capture))
    jobs = []
    for mode in METHODS:
        chosen = {row["visit"] for row in entry["decisions"][mode]}
        rows = selective_capture.mix_probes(left, right, chosen)
        identity = whole_iq.recording.digest(
            [
                "mixed-duty/v1",
                mode,
                sorted(chosen),
                entry["wide_native_sha256"],
                entry["capture_native_sha256"],
            ]
        )
        document = dict(
            wide, source=dict(wide["source"], probes=rows, analysis_manifest_sha256=identity)
        )
        document["provenance"] = dict(wide["provenance"], run_id="mixed-duty-" + identity[7:35])
        document["provenance"].pop("detector_sha256", None)
        folder = work / ident / mode
        (folder / "recording").mkdir(parents=True, exist_ok=False)
        native, request = (folder / "recording" / name for name in ("native.json", "request.json"))
        write(native, encoded(document) + b"\n")
        digest = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
        verify_request(read(request), parent, native_path=native, native_sha256=digest)
        save_json(folder / "plan.json", dict(receiver=selection["receiver"]))
        save_json(folder / "raw.json", dict(native_sha256=digest, request_sha256=_sha(request)))
        jobs.append(
            dict(
                id=ident,
                condition=mode,
                method="mixed_duty_" + mode,
                mode="matched-tile",
                cpu=cpu,
                cohort="new-roof-holdout" if ident in CASES[2:] else "original-roof-control",
                native_sha256=digest.removeprefix("sha256:"),
                prepared_request_sha256=_sha(request),
                parent_wide_sha256=entry["wide_native_sha256"],
                paired_capture_sha256=entry["capture_native_sha256"],
                catalog_sha256=entry["catalogue_sha256"],
                original_request_sha256=entry["capture_request_sha256"],
                tile=entry["tile"],
                original_probes=len(left),
                admitted_visits=entry["visits"],
                routed_visits=len(chosen),
                positive_probes=sum(support_cross.positive(p) for p in rows),
                positive_candidates=sum(
                    c[support_cross.GATE] is True for p in rows for c in p["candidates"]
                ),
            )
        )
    return jobs


def run(work):
    selection = freeze(work)
    print(
        "locked",
        {
            ident: [len(row["decisions"][m]) for m in METHODS]
            for ident, row in selection["cases"].items()
        },
        flush=True,
    )
    schedule = {}
    for cpu, cases in LANES.items():
        chosen = []
        for ident in cases:
            jobs = treatment(work, cpu, ident, selection)
            chosen.extend(jobs if cpu == 6 else jobs[::-1])
        schedule[cpu] = chosen
    save_json(
        REPORT / "plan.json",
        dict(
            schedule=schedule,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            cap_s=support_cross_trial.LIMIT,
            selection_sha256=_sha(REPORT / "selection-lock.json"),
        ),
    )

    def lane(cpu):
        return [support_cross_trial.service(work, row) for row in schedule[cpu]]

    start = monotonic()
    with ThreadPoolExecutor(2) as pool:
        results = [r for group in pool.map(lane, LANES) for r in group]
    predictions = REPORT / "predictions.jsonl.gz"
    write(predictions, compressed_rows(results))
    files = ("plan.json", "selection-lock.json", predictions.name)
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            attempted=len(results),
            elapsed_s=monotonic() - start,
            files={name: _sha(REPORT / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
