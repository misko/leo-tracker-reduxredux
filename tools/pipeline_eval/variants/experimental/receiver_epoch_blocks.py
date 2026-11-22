"""Use local invalidation to rank the original scout's timing scores."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import receiver_build
from .receiver_build import replace


def timing(source):
    source = replace(source, "static void find_times(TimingFirst *w, int *epochs) {",
                     '#include "receiver_epoch_blocks.inc"\n\n'
                     "static void find_times(TimingFirst *w, int *epochs) {")
    original = """    for (int k = 0; k < clocks; ++k) {
        int best = 0;
        for (int i = 1; i < w->epochs; ++i)
            if (w->time_score[i] > w->time_score[best])
                best = i;
        epochs[k] = best;
        for (int j = -radius; j <= radius; ++j)
            w->time_score[(best + j + w->epochs) % w->epochs] = -1.;
    }"""
    exact = "    experimental_epoch_peaks(w->time_score, w->epochs, radius, clocks, 1, epochs);"
    return replace(source, original, exact)


def overlay(build):
    def composed(output, **recipe):
        compile_source = receiver_build.subprocess.run

        def compile_blocked(command, **kwargs):
            if "-c" in command:
                path = Path(command[command.index("-c") + 1])
                if path.name == "timing_first_receiver.c":
                    path.write_text(timing(path.read_text()))
            return compile_source(command, **kwargs)

        with patch.object(receiver_build, "subprocess", SimpleNamespace(run=compile_blocked)):
            return build(output, **recipe)

    return composed
