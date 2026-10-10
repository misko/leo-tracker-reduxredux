"""Bounded branch continuation through the unchanged123/105 narrow ports."""

import time
from pathlib import Path


def continue_slice(
    plan, member, branch, output, search_directory, loader, driver, adapter, *, clock=time.monotonic
):
    digest = driver.canonical_digest(plan)
    directory = Path(output)
    terminal = directory / "result.json"
    if terminal.exists():
        row = driver.read(terminal)
        if row["protocol_sha256"] != digest:
            raise ValueError("foreign continuation")
        return row
    discovery = driver.read(Path(search_directory) / "result.json")
    if discovery["protocol_sha256"] != digest or discovery["label"] != member["label"]:
        raise ValueError("foreign discovery")
    if discovery["status"] != "complete":
        row = dict(
            protocol_sha256=digest,
            label=member["label"],
            branch=branch,
            status="not-run-search-failed",
            reason=discovery["status"],
            operational={},
            fallback_available=False,
        )
        driver.append(terminal, row)
        return row
    backend = loader.load_case.__globals__
    core = backend["core"]
    phase = "baseline" if branch == "native" else "candidate"
    slot = backend["claim_slice"](directory / "slices", phase, digest, maximum=2)
    if slot is None:
        raise ValueError("continuation slice budget exhausted without receipt")
    begun = clock()
    deadline = begun + 500
    row = dict(
        protocol_sha256=digest,
        label=member["label"],
        branch=branch,
        slice=slot,
        fallback_available=False,
    )
    try:
        case = loader(member["binding"])
        expected = driver.read(Path(search_directory) / "case.json")
        if (
            expected["protocol_sha256"] != digest
            or driver.case_identity(case) != expected["identity"]
        ):
            raise ValueError("continuation physical identity differs")
        identity = dict(
            input_digest=case["identity"]["input_manifest_sha256"],
            score_signature=driver.canonical_digest(
                dict(
                    prior=driver.json_value(case["prior"]),
                    score=driver.json_value(core.HARD60_SCORE),
                )
            ),
            bank_signature=driver.canonical_digest(case["bank"].numbers.tolist()),
        )

        def fetched(key):
            path = Path(search_directory) / "points" / (driver.canonical_digest(key)[7:] + ".json")
            value = driver.read(path)
            if (
                value["protocol_sha256"] != digest
                or value["key"] != key
                or value["status"] != "complete"
            ):
                raise ValueError("invalid retained coarse receipt")
            return value["value"]

        triggers = []
        for region in discovery["searches"][branch]["regions"]:
            point = [region["east_km"], region["north_km"]]
            seed = fetched(["bootstrap", point])
            fitted = fetched(["point", *point, "fitted-c"])["fit"]
            original = adapter.admitted_original(point, seed, fitted, len(case["bank"].numbers))
            key = "point:" + ":".join(str(x) for x in point)
            triggers.append(
                dict(
                    key=key,
                    original=original,
                    identity=dict(
                        identity,
                        basin=key,
                        original_sha256=driver.canonical_digest(original),
                        local_radius_km=25.0,
                    ),
                )
            )

        def stage(key, budget, operation):
            path = directory / "stages" / (driver.canonical_digest({"key": key})[7:] + ".json")
            if path.exists():
                receipt = driver.read(path)
                if receipt["protocol_sha256"] != digest or receipt["key"] != key:
                    raise ValueError("foreign stage")
                return receipt["value"]
            claim = path.with_suffix(".claim.json")
            if claim.exists():
                raise ValueError("claimed stage without receipt; no silent retry")
            if clock() + budget >= deadline:
                raise core.RegionalSliceExpired(key)
            driver.append(claim, dict(protocol_sha256=digest, key=key, budget_s=budget))
            started = clock()
            try:
                value = dict(result=driver.json_value(operation()), reason=None)
            except (ValueError, TimeoutError, AssertionError) as error:
                value = dict(result=None, reason=f"{type(error).__name__}: {error}")
            driver.append(
                path,
                dict(protocol_sha256=digest, key=key, value=value, elapsed_s=clock() - started),
            )
            return value

        row.update(
            adapter.continue_branch(
                case,
                triggers,
                stage,
                recover=backend["recovered_region"],
                joint=backend["run_joint_stages"],
            ),
            status="complete",
        )
    except core.RegionalSliceExpired as error:
        row.update(status="budget-exhausted" if slot == 2 else "pending", reason=str(error))
    except Exception as error:
        row.update(status="failed", reason=f"{type(error).__name__}: {error}")
    row["elapsed_s"] = clock() - begun
    driver.append(directory / "slices" / f"{phase}-{slot:02}.done.json", row)
    if row["status"] != "pending":
        driver.append(terminal, row)
    return row
