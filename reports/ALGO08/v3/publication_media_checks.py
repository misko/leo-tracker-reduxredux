"""Verify media content addresses without loading the research run controller."""


def image_comparison_fields(images):
    return {name: {key: image[key] for key in ("sha256", "size", "rgba_sha256")} for name, image in images.items()}


def verify_position_sidecars(before, current, run, original_figures, current_figures):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    comparison = {}
    for name in ("grid", "path"):
        items, positions = [], []
        for folder, figures in ((before, original_figures), (current, current_figures)):
            store = FastStandardAnalysisStore(folder)
            precise = getattr(store, "position_" + name)(run)
            binding = dict(precise["binding"])
            image = binding.pop("position_png_sha256")
            if image != figures["position"]["sha256"]:
                raise ValueError(f"{name} does not bind the currently published position PNG")
            value = dict(precise, binding=binding)
            value.pop("elapsed_seconds", None)
            items.append(canonical_digest(value))
            positions.append(image)
        if items[0] != items[1]:
            raise ValueError(f"Numerical {name} or its scientific binding changed")
        comparison[name] = dict(unchanged_numerical_sha256=items[0], old_position=positions[0], direct_position=positions[1])
    return comparison
