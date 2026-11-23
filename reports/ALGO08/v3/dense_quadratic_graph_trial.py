"""Profile only the actual quadratic graph inside the installed saved solve."""

import argparse
from contextlib import contextmanager
import cProfile
from pathlib import Path
from time import process_time
from unittest.mock import patch

from aperture_trial import write
from dense_quadratic_proxy import GraphAudit
from live_inference_profile import attribution, replay


class GraphDone(Exception):
    pass


def profile(output):
    audit = GraphAudit()
    profiler = cProfile.Profile(timer=process_time)

    @contextmanager
    def configure(assets, route):
        from leo.application import localization_v3

        with audit.configure(assets, route):
            prepare = localization_v3.prepare_tracks

            def stop_after_graph(*args, **kwargs):
                profiler.runcall(prepare, *args, **kwargs)
                raise GraphDone

            with patch.object(localization_v3, "prepare_tracks", stop_after_graph):
                yield

    try:
        replay("control", output, configure_solve=configure)
    except GraphDone:
        write(output, dict(**audit.report(), profile=attribution(profiler)))
    else:
        raise ValueError("Expected to profile just the released quadratic graph")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    profile(parser.parse_args().output)
