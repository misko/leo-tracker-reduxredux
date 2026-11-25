"""Opt into the complete released Graph path in a separate rank-68 capsule."""

from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import patch


WORKER = Path(__file__).resolve()
sys.path.insert(0, str(WORKER.parent))

import ds30_0280_moment_position_extended as extended  # noqa: E402
import moment_preserving_fast_graph as fast  # noqa: E402


STEM = "ds30-0280-moment-fast-publication"
PROTOCOL = "b066ca07e31d042bbbefdfe2ab5322595f76f3fec059d4223375a58bb44b0161"
COMPARISON = "measurements/moment-fast-graph-full-comparison.json"
COMPARISON_PIN = "b757315415ae137956362453b1329fde5047e5d1337861480e69dc433b662f84"
FROZEN_SOURCE = extended.WORKER.name
FROZEN_REGISTRATION = extended.check_registration
FROZEN_PROJECTION = extended.transfer.optional_projection


def experiment(*, probe):
    spec = extended.transfer.experiment(probe=probe)
    spec.stem = STEM
    spec.source = WORKER.name
    spec.transfer_sources += (FROZEN_SOURCE, extended.transfer.WORKER.name, extended.REFUSAL, COMPARISON,
                              "moment_preserving_fast_graph.py", fast.PORT, "vector_graph_edges.py",
                              "polynomial_fit_cache.py")
    return spec


def registration():
    if extended.saved.identifier(WORKER.parent / COMPARISON) != COMPARISON_PIN:
        raise ValueError("The complete-port equality and cost comparison changed")
    return FROZEN_REGISTRATION()


@contextmanager
def correction(mode):
    if mode == "ordinary":
        with FROZEN_PROJECTION(mode):
            yield
    else:
        with fast.enabled(extended.transfer.moment), FROZEN_PROJECTION(mode):
            yield


def main():
    with patch.multiple(extended, WORKER=WORKER, STEM=STEM, PROTOCOL_PIN=PROTOCOL,
                        experiment=experiment, check_registration=registration, __doc__=__doc__), patch.object(
                            extended.transfer, "optional_projection", correction):
        return extended.main()


if __name__ == "__main__":
    raise SystemExit(main())
