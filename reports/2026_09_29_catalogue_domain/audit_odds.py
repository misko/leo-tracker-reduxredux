import math

from study import HERE, read, save

checked = 0
maximum = 0.0
for ds in ("DS7", "DS8", "DS9"):
    for row in read(HERE / f"{ds}.json")["rows"]:
        for key in ("training", "full"):
            r = row[key]
            a = r["retained_signal_probability"]
            b = r["full_signal_probability"]
            if min(a, b) <= 1e-6 or max(a, b) >= 1 - 1e-6:
                continue
            observed = math.log(a / (1 - a)) - math.log(b / (1 - b))
            expected = math.log(r["retained_mass"] * row["visible"] / row["retained_visible"])
            error = abs(observed - expected)
            assert error < 1e-7
            maximum = max(maximum, error)
            checked += 1
assert checked > 0
save(
    HERE / "odds-audit.json", dict(checked=checked, maximum_log_odds_error=maximum, tolerance=1e-7)
)
print(checked, "odds-ratio checks; maximum error", maximum)
