"""Inspect the exact causal earlier-orbit inputs before either winner is chosen."""

from hashlib import sha256
from time import perf_counter_ns, process_time_ns


def census(sky, modes):
    import numpy as np

    from named_history_once import ALIGNMENT_S

    origin = int(sky["metadata"]["origin_utc_ns"])
    cutoff = int(sky["metadata"]["cutoff_utc_ns"])
    current = {int(number) for number in sky["bank"]["norad"]}
    if len(current) != len(sky["bank"]["norad"]) or set(map(int, sky["nominal_elements"])) != current:
        raise ValueError("The prepared current orbit roster must have unique element identities")
    results = {}
    for policy in ("previous", "genuine_previous"):
        start = process_time_ns(), perf_counter_ns()
        original = sky[policy + "_receipt"]
        text = sky[policy + "_tle"]
        digest = sha256(text.encode()).hexdigest()
        if digest != original["catalogue_sha256"]:
            raise ValueError("The earlier-orbit catalogue differs from its causal receipt")
        parsed = modes.parse_element_sets(text)
        numbers = parsed.satellite_numbers
        if (len(set(numbers)) != len(numbers) or set(numbers) != set(map(int, original["sources"]))
                or not set(numbers) <= current or any(source["epoch_utc_ns"] > cutoff
                    or source["collected_utc_ns"] > cutoff for source in original["sources"].values())):
            raise ValueError("The earlier roster or provenance differs from the prepared causal view")
        if numbers:
            _, _, good = modes.ecef_states(parsed, origin, np.asarray(ALIGNMENT_S))
            if good.shape != (len(numbers),) or good.dtype != bool:
                raise ValueError("The installed propagation status needs one boolean per earlier element")
            unavailable = {str(number): original["sources"][str(number)]
                           for number, usable in zip(numbers, good, strict=True) if not usable}
        else:
            unavailable = {}
        results[policy] = dict(earlier_rows=len(numbers), absent=len(current) - len(numbers),
                               unusable=unavailable, catalogue_sha256=digest,
                               cpu_ns=process_time_ns() - start[0], elapsed_ns=perf_counter_ns() - start[1])
    return dict(current_rows=len(current), origin_utc_ns=origin, cutoff_utc_ns=cutoff,
                alignment_seconds=ALIGNMENT_S, prior=results)
