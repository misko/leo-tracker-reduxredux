"""Share the exact pre-screen causal catalogue with a research inference route."""

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import patch


@dataclass
class PreparedExterior:
    root: object
    tracks: object = None
    cutoff: object = None
    catalogue: object = None

    def match(self, tracks, reader):
        return (self.catalogue if self.catalogue is not None and self.tracks is tracks and reader.root == self.root
                and tracks["metadata"]["causal_cutoff_utc_ns"] == self.cutoff else None)


@contextmanager
def handoff(reader):
    """Expose only the catalogue from the exact normalized preparation in scope."""
    from sgp4.api import accelerated

    from leo.operations import localization_v3_inputs as inputs
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    prepared_from = algo08_position.prepare_native_scan
    normalize = algo08_position._prepared_values
    original_probe = regional_bound_guard.causal_probes
    live, counts = PreparedExterior(reader.root), Counter()
    pending = None

    def prepare(native, supplied, *args, **kwargs):
        nonlocal pending
        pending = None
        live.tracks = live.cutoff = live.catalogue = None
        if not accelerated or type(supplied) is not TleArchiveReader or supplied.root != live.root:
            return prepared_from(native, supplied, *args, **kwargs)
        base = inputs.causal_catalogue
        captured = None

        def identify(recent, cutoff, **options):
            nonlocal captured
            result = base(recent, cutoff, **options)
            if options.keys() <= {"element_parser"}:
                captured = cutoff, result
            return result

        with patch.object(inputs, "causal_catalogue", identify):
            supplied_data = prepared_from(native, supplied, *args, **kwargs)
        if (captured is not None and supplied_data["status"] == "inputs_prepared"
                and captured[0] == supplied_data["tracks"]["metadata"]["causal_cutoff_utc_ns"]):
            pending = supplied_data, *captured
            counts["prepared_catalogues"] += 1
        return supplied_data

    def normalized(original):
        nonlocal pending
        capture, pending = pending, None
        ready = normalize(original)
        if capture is not None and capture[0] is original:
            live.tracks, live.cutoff, live.catalogue = ready["tracks"], capture[1], capture[2]
        return ready

    def probe(tracks, source, region, *, catalogue=None, terminal_only=False):
        if catalogue is None:
            catalogue = live.match(tracks, source)
            counts["catalogue_handoff" if catalogue is not None else "fresh_catalogue"] += 1
        else:
            counts["existing_catalogue"] += 1
        return original_probe(tracks, source, region, catalogue=catalogue, terminal_only=terminal_only)

    with (patch.object(algo08_position, "prepare_native_scan", prepare),
          patch.object(algo08_position, "_prepared_values", normalized),
          patch.object(regional_bound_guard, "causal_probes", probe)):
        yield live, counts, original_probe
