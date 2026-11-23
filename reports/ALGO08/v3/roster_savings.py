"""Apply the frozen timing model case by case and price a uniform saving on completed scans."""

from hashlib import sha256
import json
from statistics import median

from prospective_solver_budget import MODEL, MODEL_SHA, predictions
from solver_transfer_budget import DATA


def pinned(name, pin):
    raw = (DATA / name).read_bytes()
    if sha256(raw).hexdigest() != pin:
        raise ValueError(f"Timing source changed: {name}")
    return json.loads(raw)


def ratios(rows, saving):
    projected = [row["modeled_s"] - (saving if row["adjustable"] else 0.) for row in rows]
    stock = [row["v3_s"] for row in rows]
    return (median(candidate / baseline for candidate, baseline in zip(projected, stock, strict=True)),
            sum(projected) / sum(stock))


def gate_savings(rows):
    # Full candidate time includes retained products. Restrict the sweep to the
    # smallest complete time among cases to which the saving can be applied.
    upper = min((row["modeled_s"] for row in rows if row["adjustable"]), default=0.)
    def threshold(gate):
        if ratios(rows, 0.)[gate] <= .5:
            return 0.
        if ratios(rows, upper)[gate] > .5:
            return None
        lo, hi = 0., upper
        for _ in range(55):
            mid = (lo + hi) / 2
            if ratios(rows, mid)[gate] > .5:
                lo = mid
            else:
                hi = mid
        return hi
    return dict(median_s=threshold(0), summed_s=threshold(1))


def study():
    model = pinned(MODEL, MODEL_SHA)
    cases = pinned("regional-dense-budget.json", "20ca6db13e6294d34ae732635158aef332f622127d120d6f6ca1229082e78677")
    clocks = pinned("acquisition-throughput.json", "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a")
    source = {row["case"]: row for row in clocks["rows"]}
    panels = {}
    for size in ("4", "16"):
        rows = []
        for case in cases["panels"][size]["cases"]:
            row = source[case]
            acq, solve, tail = row["stages"]
            stock = sum(row["stages"])
            if acq:
                predicted = (row["compressed_MB"] / model["dense_zero_wait_MB_s"]
                             + predictions(model, solve)["three_sizes_s"] + model["common_charge_s"] + tail)
            else:
                predicted = stock
            rows.append(dict(case=case, windows=row["windows"], v3_s=stock, modeled_s=predicted,
                             adjustable=bool(acq), single_case_excess_s=predicted - stock / 2))
        panels[size] = dict(rows=rows, ratios_at_zero_wait=ratios(rows, 0.), minimum_saving=gate_savings(rows))
    return dict(dense_cpu_only_rate_MB_s=model["dense_zero_wait_MB_s"], panels=panels)


if __name__ == "__main__":
    print(json.dumps(study(), indent=2, sort_keys=True, allow_nan=False))
