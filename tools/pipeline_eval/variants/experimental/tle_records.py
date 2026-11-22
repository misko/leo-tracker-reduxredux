"""Batch validation of canonical orbit rows during one isolated solver run."""
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import patch

from leo.sky import propagation
from tools.pipeline_eval.variants import algo08_causal_reuse


@contextmanager
def batch_records(library):
    spec = spec_from_file_location("_leo_tle_records", library)
    native = module_from_spec(spec)
    spec.loader.exec_module(native)
    original = propagation.parse_element_set_records
    counts = dict(catalogues=0, records=0, fallback=0)

    def parse(text):
        result = native.records(text, propagation.ElementSetRecord)
        if result is None:
            counts["fallback"] += 1
            return original(text)
        counts["catalogues"] += 1
        counts["records"] += len(result)
        return result

    with (patch.object(propagation, "parse_element_set_records", parse),
          patch.object(algo08_causal_reuse, "parse_element_set_records", parse)):
        yield counts
