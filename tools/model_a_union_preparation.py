"""Shared exact prepared-input port for prospective union-bank experiments."""

from pathlib import Path

import ds21_model_a_pipeline_cached_v2 as cached
from model_a_union_transport import union_bank


def combine_cases(before, after):
    """Keep recorded observations, partition, clock nodes and native input unchanged."""
    for key in ("source", "split", "prepared", "nodes", "prior"):
        cached.prepared_cache.exact_equal(before[key], after[key])
    return {**after, "bank": union_bank(before["bank"], after["bank"])}


def prepare(before_directory, after_directory):
    """Read qualified frozen parents and return genuine saved initializers verbatim.

    The C receiver lifts and derivations are part of each original initializer.
    This port never regenerates them or chooses a branch for the union bank.
    Callers must qualify any model-specific transport before numerical fitting.
    """
    parents = {}
    for name, directory in (("before", before_directory), ("after", after_directory)):
        directory = Path(directory).resolve()
        frozen = cached.read_control(directory)
        cached.qualification(directory)
        with cached.original.discovery.slice_bound(5):
            case = cached.prepare_case(frozen)
        parents[name] = dict(
            directory=directory,
            frozen=frozen,
            case=case,
            initialization=cached.initialization(directory, frozen),
        )
    if parents["before"]["frozen"]["label"] != parents["after"]["frozen"]["label"]:
        raise ValueError("Union requires the same case")
    return dict(
        label=parents["after"]["frozen"]["label"],
        parents=parents,
        union_case=combine_cases(parents["before"]["case"], parents["after"]["case"]),
    )


def saved_seeds(preparation, model, view):
    """Twelve genuine original initializers, after first; no endpoint or truth seed."""
    if model not in ("A", "B", "C") or view not in ("all", "low", "high"):
        raise ValueError("Explicit original model/view required")
    return [
        dict(
            origin=origin,
            start=index,
            row=row,
            receiver_lift=parent["initialization"]["receiver_lifts"][index],
            initialization=cached.binding(parent["directory"] / "initialization.json")
            if parent["frozen"]["reused_initialization"] is None
            else parent["frozen"]["reused_initialization"],
        )
        for origin in ("after", "before")
        for parent in [preparation["parents"][origin]]
        for index, row in enumerate(parent["initialization"]["starts"][model][view])
    ]
