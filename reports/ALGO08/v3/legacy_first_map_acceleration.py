"""Opt-in exact first-use ports shared across eligible original publications."""

from contextlib import contextmanager
from functools import partial, wraps
from importlib import import_module
import json
from pathlib import Path
from unittest.mock import patch

ARTIFACTS = ("hasher", "projection", "template")
SCHEMA = "private-algo08-first-map-exact-acceleration-v1"


def checked_artifacts(path, pin):
    from exact_named_raw import staged_path
    from reports.ALGO08.v3.legacy_block_input import checked_file

    spec = json.loads(checked_file(staged_path(path), pin, 16_384))
    if set(spec) != {"schema", *ARTIFACTS} or spec["schema"] != SCHEMA:
        raise ValueError("Expected the exact first-use artifact roster")
    for name in ARTIFACTS:
        item = spec[name]
        if set(item) != {"path", "sha256"}:
            raise ValueError("Each first-use artifact requires its own checked path and pin")
        checked_file(staged_path(Path(item["path"])), item["sha256"], 2_000_000)
    return spec


@contextmanager
def solver_ports(spec, audit):
    import exact_named_raw as raw

    publish = raw.publish_active

    @wraps(publish)
    def accelerated(*args, **kwargs):
        # Match the ordinary publisher's import order before research
        # adapters make the checkout visible for auxiliary tools.
        import_module("tools.algo08_position")
        import_module("tools.algo08_scan")
        from causal_body_election import binding as election
        import exact_named_route as route
        from grid_design_template import Designs, bind_projected_design
        from grid_feature_projection import Native, supported_cpu
        import grid_phase_state_reuse as phase

        original_ports, original_grid = route.exact_ports, phase.cached_predictive_grid

        @contextmanager
        def grid(*, bind=None):
            if bind is not None or not supported_cpu():
                audit["grid"] = {"fallback": "existing_binding" if bind is not None else "unsupported_cpu"}
                with original_grid(bind=bind) as counters:
                    yield counters
                return
            native, designs = Native(spec["projection"]["path"]), Designs(spec["template"]["path"])
            with original_grid(bind=partial(bind_projected_design, native, designs)) as counters:
                yield counters
            audit["grid"] = dict(projection=dict(native.counts), assembly=dict(designs.counts), phase=dict(counters))

        @contextmanager
        def ports(*values, **options):
            with (patch.object(phase, "cached_predictive_grid", grid),
                  original_ports(*values, **options), election(audit.setdefault("election", {}))):
                yield

        with patch.object(route, "exact_ports", ports):
            return publish(*args, **kwargs)

    with patch.object(raw, "publish_active", accelerated):
        yield
