"""Price one quality repair or one perfect early routing decision on the enrolled rosters."""

import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"


def ratios(stock, fast):
    return median(a / b for a, b in zip(fast, stock, strict=True)), sum(fast) / sum(stock)


def price(rows, dense_solve, ordinary_dense, rate, startup):
    stock = [sum(row["stages"]) for row in rows]
    fast = [
        startup
        + row["compressed_MB"] / rate
        + row["stages"][1] * (dense_solve / ordinary_dense)
        + row["stages"][2]
        if row["stages"][0]
        else before
        for row, before in zip(rows, stock, strict=True)
    ]
    base = ratios(stock, fast)
    slack = sum(stock) / 2 - sum(fast)
    cases = {}
    for index, row in enumerate(rows):
        if row["stages"][0] == 0:
            continue

        def charge(extra, index=index):
            billed = fast.copy()
            billed[index] += extra
            return ratios(stock, billed)

        allowed = None
        if max(base) <= 0.5:
            low, high = 0.0, max(0.0, slack)
            for _ in range(52):
                mid = (low + high) / 2
                if max(charge(mid)) <= 0.5:
                    low = mid
                else:
                    high = mid
            allowed = low
        full = charge(stock[index] - fast[index])
        solver = charge(row["stages"][1] * (1 - dense_solve / ordinary_dense))
        cases[row["case"]] = dict(
            stock_s=stock[index],
            fast_s=fast[index],
            allowed_repair_s=allowed,
            perfect_early_stock=full,
            perfect_early_stock_solver=solver,
        )
    return dict(
        baseline=base,
        summed_slack_s=slack,
        cases=cases,
        routes_to_stock_passing=sum(max(c["perfect_early_stock"]) <= 0.5 for c in cases.values()),
        routes_to_stock_solver_passing=sum(
            max(c["perfect_early_stock_solver"]) <= 0.5 for c in cases.values()
        ),
    )


def report():
    from acquisition_throughput import gates
    from regional_dense_budget import select

    inventory = json.loads((DATA / "acquisition-throughput.json").read_bytes())["rows"]
    inputs = json.loads((DATA / "regional-dense-budget.json").read_bytes())
    original = inputs["historical_installed_solve_cpu_s"]
    result = {}
    for n in ("4", "16"):
        rows = select(inventory, inputs["panels"][n]["cases"])
        entry = price(rows, 16, original, 250, inputs["common_charge_s"])
        if entry["baseline"] != gates(
            rows, 250, 16 / original, startup_s=inputs["common_charge_s"]
        ):
            raise ValueError("The retry calculation must reproduce the original two timing gates")
        result[n] = entry
    return dict(model_dense_solve_s=16, model_acquisition_MB_s=250, panels=result)


if __name__ == "__main__":
    import sys

    with Path(sys.argv[1]).open("x") as stream:
        json.dump(report(), stream, indent=2, allow_nan=False)
        stream.write("\n")
