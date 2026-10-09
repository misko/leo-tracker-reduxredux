"""Uniform source and convergence decisions without reference-position inputs."""

from pathlib import Path


def source_stage(upstream):
    for name in ("drift-50", "post-200", "remove-5"):
        fit = upstream["stages"].get(name, {}).get("fitted-c")
        if fit is not None and fit["converged"]:
            return name
    raise ValueError("No qualified shared extension seed")


def regional_path(result, result_path, root):
    name = result["upstream"]["regional_sources"]["fitted-c"]
    if name == "baseline":
        return None
    if name not in ("sep25", "sep50"):
        raise ValueError(f"Unexpected region source: {name}")
    receipt = result["region_receipts"][name]
    if receipt["mode"] == "archived":
        return Path(root) / receipt["path"]
    if receipt["mode"] != "new_replay":
        raise ValueError("Unrecognized regional receipt")
    label = result["member"]["inventory_label"]
    return Path(result_path).parent.parent / "regions" / label / f"{name}.json"


def accepted(candidate, fallback):
    return candidate if candidate["converged"] else fallback
