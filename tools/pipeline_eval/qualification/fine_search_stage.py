"""Export a stage descriptor and case/window timing tables from the sealed fine CFO trial."""

from collections import defaultdict
from pathlib import Path

from ..__main__ import ROOT, save_json
from .capture_runtime import checked, decompress, read
from .fine_search_results import paired, spread
from .full_v5_check import _sha
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/pilot-search-and-region/fine-search"
MEASUREMENT_SEAL = "qualification-lock.json"
MEASUREMENT_SHA = "905317d53cb7b41a341bc6c121bc99bddf9caf4da1e666f1e3580111184c4895"
DESCRIPTOR = "stage-figure.json"
STAGE_SEAL = "stage-figure-lock.json"
MODES = ("row_wise", "pruned")


def export(folder=REPORT):
    measurement = read(checked(folder / MEASUREMENT_SEAL, MEASUREMENT_SHA))["files"]

    def source(name):
        return checked(folder / name, measurement[name])

    summary = read(source("summary.json"))
    timings = {(r["case"], r["visit"], r["repetition"]): r for r in summary["timing"]}
    audits = {(r["case"], r["visit"]): r for r in summary["audits"]}
    records = []
    groups = defaultdict(list)
    for case in summary["cases"]:
        receipt = decompress(source(f"{case}.json.gz"))
        edge = receipt["edge"]
        for sample in receipt["rows"]:
            visit = sample["visit"]
            audit = audits.pop((case, visit))
            context = dict(case=case, edge=edge, visit=visit, kind=sample["kind"])
            for mode in MODES:
                records.append(
                    dict(
                        stage="fine_cfo_scoring",
                        **context,
                        mode=mode,
                        repetition="",
                        first="",
                        cpu_ms=audit[f"{mode}_fine_cpu_ms"],
                        wall_ms="",
                    )
                )
            for call in sample["timings"]:
                rep, mode = call["repetition"], call["mode"]
                match = timings[case, visit, rep]
                cpu_ms, wall_ms = call["cpu_ns"] / 1e6, call["wall_ns"] / 1e6
                if (cpu_ms, wall_ms) != (match[f"{mode}_cpu_ms"], match[f"{mode}_wall_ms"]):
                    raise ValueError("summary timing differs from the sealed worker receipt")
                records.append(
                    dict(
                        stage="complete_detector",
                        **context,
                        mode=mode,
                        repetition=rep,
                        first=call["first"],
                        cpu_ms=cpu_ms,
                        wall_ms=wall_ms,
                    )
                )
            groups[(case, edge, visit, audit["kind"])] = [
                timings.pop((case, visit, rep)) for rep in range(audit["paired_repeats"])
            ]
        groups[(case, edge, "", "all")] = [
            row for keys, rows in groups.items() if keys[0] == case for row in rows
        ]
    if audits or timings:
        raise ValueError("stage export omitted sealed observations")
    summaries = []
    for (case, edge, visit, kind), group in groups.items():
        for clock in ("cpu", "wall"):
            gain = paired(group, clock)
            summaries.append(
                dict(
                    case=case,
                    edge=edge,
                    visit=visit,
                    kind=kind,
                    clock=clock,
                    pairs=gain["n"],
                    **{
                        f"{mode}_{field}_ms": value
                        for mode in MODES
                        for field, value in spread([r[f"{mode}_{clock}_ms"] for r in group]).items()
                        if field != "n"
                    },
                    paired_savings_min_ms=gain["min"],
                    paired_savings_median_ms=gain["median"],
                    paired_savings_max_ms=gain["max"],
                    paired_savings_median_pct=gain["median_percent"],
                )
            )

    descriptor = dict(
        version=1,
        id="pruned-fine-cfo-search",
        title="Prune the original fine CFO transform",
        sample="16 saved dual CI16 visits across four captures, five alternating repeats per arm",
        boundary="Resident dual CI16 IQ through complete prepared detector and factor projection",
        note=(
            "Both arms use row-wise coarse selection. Range bars show observed min and max. "
            "The fine scoring panel uses separate port timings. The CSV lists both scopes."
        ),
        seal=STAGE_SEAL,
        image=source("stage.png").name,
        pdf=source("stage.pdf").name,
        csv="stage.csv",
    )
    csv_file(folder / "stage.csv", records)
    csv_file(folder / "stage-summary.csv", summaries)
    save_json(folder / DESCRIPTOR, descriptor)
    files = (DESCRIPTOR, "stage.csv", "stage-summary.csv", "stage.png", "stage.pdf", "summary.json")
    save_json(
        folder / STAGE_SEAL,
        dict(
            files={name: _sha(folder / name) for name in files}
            | {MEASUREMENT_SEAL: MEASUREMENT_SHA},
            report_generator_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    export()
