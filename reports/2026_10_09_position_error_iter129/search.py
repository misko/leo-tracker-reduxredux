"""Fresh matched discovery queues sharing durable native fits and bootstrap seeds."""

import time
from pathlib import Path


def search_slice(
    plan, member, output, loader, driver, *, clock=time.monotonic, evaluator_factory=None
):
    digest = driver.canonical_digest(plan)
    directory = Path(output)
    terminal = directory / "result.json"
    if terminal.exists():
        value = driver.read(terminal)
        if value["protocol_sha256"] != digest:
            raise ValueError("foreign search terminal")
        return value
    starts = sorted((directory / "slices").glob("*.started.json"))
    elapsed = 0.0
    for path in starts:
        if driver.read(path)["protocol_sha256"] != digest:
            raise ValueError("foreign slice")
        finish = path.with_name(path.name.replace("started", "finished"))
        if not finish.exists():
            raise driver.ClaimedWithoutReceipt(str(path))
        row = driver.read(finish)
        if row["protocol_sha256"] != digest or not 0 <= row["elapsed_s"] < float("inf"):
            raise ValueError("invalid finished slice")
        elapsed += row["elapsed_s"]
    slot = len(starts) + 1
    if slot > 6 or elapsed >= 3000:
        value = dict(
            protocol_sha256=digest,
            label=member["label"],
            status="budget-exhausted",
            complete=False,
            slices=len(starts),
            elapsed_s=elapsed,
            searches={},
        )
        driver.append(terminal, value)
        return value
    begun = clock()
    prefix = directory / "slices" / f"{slot:02}"
    driver.append(str(prefix) + ".started.json", dict(protocol_sha256=digest, slot=slot))
    deadline = begun + min(500, 3000 - elapsed)
    cache = driver.DurableCache(directory / "points", digest, deadline, clock=clock)
    searches, failures = {}, {}
    status, reason = "pending", None
    try:
        case = loader(member["binding"])
        identity = driver.case_identity(case)
        path = directory / "case.json"
        binding = dict(protocol_sha256=digest, label=member["label"], identity=identity)
        if path.exists():
            if driver.read(path) != binding:
                raise ValueError("physical reconstruction changed")
        else:
            driver.append(path, binding)
        factory = evaluator_factory or driver.PointEvaluator
        evaluator = factory(case["observations"], case["bank"], case["prior"], case["tracks"])
        original_bootstrap = evaluator.bootstrap

        def bootstrap(*args, **kwargs):
            point = list(args[3])
            value = cache.fetch(
                ["bootstrap", point], lambda: original_bootstrap(*args, **kwargs), reserve_seconds=5
            )
            return driver.PositionBootstrap(
                tuple(value["satellite_indices"]),
                driver.np.asarray(value["vector"]),
                tuple(driver.BootstrapMatch(**m) for m in value["matches"]),
            )

        evaluator.bootstrap = bootstrap
        config = driver.Hard60Configuration()
        for mode in ("native", "fixed"):
            event_index = 0

            def observe(event, mode=mode):
                nonlocal event_index
                if clock() >= deadline:
                    raise driver.SliceExpired("trace replay")
                target = directory / "traces" / mode / f"{event_index:05}.json"
                value = dict(protocol_sha256=digest, event=event)
                if target.exists():
                    if driver.read(target) != value:
                        raise ValueError("resumed trace differs")
                else:
                    driver.append(target, value)
                event_index += 1

            def evaluate(e, n, mode=mode):
                if (e, n) not in evaluator.seeds:
                    evaluator.seeds[(e, n)] = bootstrap(
                        case["observations"],
                        case["bank"],
                        case["prior"],
                        (e, n),
                        case["tracks"],
                        maximum_seconds=5.0,
                        orbit_predictor=driver.predict_orbits,
                    )
                try:
                    row = cache.fetch(
                        ["point", e, n, "fitted-c"], lambda: evaluator(e, n, "fitted-c")
                    )
                except driver.CachedFailure as error:
                    failures[str((e, n))] = dict(point=[e, n], error=str(error))
                    observe(dict(event="fit-status", east=e, north=n, status="failed"))
                    return 1e100
                observe(
                    dict(
                        event="fit-status",
                        east=e,
                        north=n,
                        status="complete",
                        converged=row["fit"]["converged"],
                    )
                )
                return row["scores"][mode]["objective"]

            found = driver.hierarchical_search(
                evaluate,
                radius_km=case["prior"].radius_km,
                levels_km=config.levels_km,
                budget_points=400,
                edge_priority=config.edge_priority,
                observer=observe,
            )
            searches[mode] = dict(
                search=found,
                regions=driver.distinct_basins(found, count=3, minimum_separation_km=12.5),
            )
        status, reason = (
            ("incomplete", "point evaluation failures") if failures else ("complete", None)
        )
    except driver.SliceExpired:
        reason = "slice deadline"
    except Exception as error:
        status, reason = "failed", f"{type(error).__name__}: {error}"
    duration = clock() - begun
    if status == "pending" and slot == 6:
        status, reason = "budget-exhausted", "six-slice cap"
    row = dict(
        protocol_sha256=digest,
        label=member["label"],
        status=status,
        reason=reason,
        complete=status == "complete",
        slices=slot,
        elapsed_s=elapsed + duration,
        searches=driver.json_value(searches),
        point_failures=list(failures.values()),
    )
    driver.append(
        str(prefix) + ".finished.json",
        dict(protocol_sha256=digest, elapsed_s=duration, status=status, reason=reason),
    )
    if status != "pending":
        driver.append(terminal, row)
    return row
