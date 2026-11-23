"""Materialize each new causal SGP4 row without a one-entry catalogue."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from sys import getsizeof
from unittest.mock import patch

from empty_bootstrap import PAYLOAD, RELEASE


PARSER = "tools/pipeline_eval/variants/algo08_causal_reuse.py"
PARSER_PIN = "3146dcb19ec88ef5e03f0b29c04fa6773c3fd575aa2c22ccbbca6ddc6ca48143"
PROPAGATION = "src/leo/sky/propagation.py"
PROPAGATION_PIN = "dd3624c137991752fc38df84cb236384932d3437f621d701ccd91e24940617c3"
TUPLE_BYTES = getsizeof((None, None)) + getsizeof((None, None, None))


def materializer(make_satellite, error_type, epoch_day, ns_per_day):
    def element(self, record):
        key = record.first_line, record.second_line
        hit = self.elements.get(key)
        if hit is not None:
            self.stats["element_hits"] += 1
            return hit
        self.stats["element_misses"] += 1
        try:
            satellite = make_satellite(*key)
        except (ValueError, RuntimeError) as error:
            raise error_type(f"unparsable element set for catalog object {record.satellite_number}") from error
        number = int(satellite.satnum)
        # Preserve the exact parenthesization and scalar rounding used by the
        # installed ElementSetCatalogue.element_epoch_utc_ns().
        epoch = int(round(((satellite.jdsatepoch - epoch_day) + satellite.jdsatepochF) * ns_per_day))
        value = number, satellite, epoch
        size = (TUPLE_BYTES + getsizeof(key[0]) + getsizeof(key[1])
                + getsizeof(number) + getsizeof(satellite) + getsizeof(epoch))
        self._remember(self.elements, key, value, size)
        return value

    return element


def eligible(module, expected, pin):
    actual = Path(module.__file__).resolve()
    return actual == expected and sha256(actual.read_bytes()).hexdigest() == pin


@contextmanager
def scalar_causal_elements(audit):
    from leo.sky import propagation
    from tools.pipeline_eval.variants import algo08_causal_reuse as runtime

    if (not runtime.accelerated or not eligible(runtime, PAYLOAD/PARSER, PARSER_PIN)
            or not eligible(propagation, RELEASE/PROPAGATION, PROPAGATION_PIN)):
        audit["source_guard"] = False
        yield
        return
    audit.update(source_guard=True, parser_sha256=PARSER_PIN, propagation_sha256=PROPAGATION_PIN)
    element = materializer(runtime.Satrec.twoline2rv, runtime.ElementSetError,
                           propagation._UNIX_EPOCH_JULIAN_DAY, propagation._NS_PER_DAY)
    with patch.object(runtime.CausalPreparationParser, "_element", element):
        yield
