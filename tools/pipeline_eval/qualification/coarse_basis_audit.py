"""Inspect capture-era pilot rank and relative rotations in an installed producer."""

import argparse
from pathlib import Path

import numpy as np

from ..__main__ import save_json
from ..variants import coarse_basis
from .full_v5_check import _sha

RATE = 10_000_000
BINS = np.arange(-800_000, 800_001, 80_000)
FALLBACK = tuple(range(2, 302, 14))


def audit():
    from leo.analysis.starlink import acquisition, templates

    blocks = []
    for edge in templates.StarlinkEdge:
        frame = templates.qin_edge_pilot_frame(RATE, edge)
        states = templates.qin_edge_pilot_states(edge)
        for symbols in (acquisition.DEFAULT_ANCHOR_SYMBOLS, FALLBACK):
            width = RATE * templates.OFDM_SYMBOL_DURATION_S
            starts = [round(s * width) for s in symbols]
            taps = round(width)
            bank = coarse_basis.filters(frame, starts, taps, BINS, RATE)
            central = bank[:, len(BINS) // 2 : len(BINS) // 2 + 1]
            relative = (states[np.asarray(symbols) - 2] - states[np.asarray(symbols) - 2, :1]) % 4
            blocks.append(
                dict(
                    edge=edge.value,
                    symbols=symbols,
                    taps=taps,
                    states_relative_to_first_tone=relative.tolist(),
                    distinct_relative_states=len(set(map(tuple, relative))),
                    single_cfo=coarse_basis.singular_diagnostics(central),
                    complete_bank=coarse_basis.singular_diagnostics(bank),
                    rotations=coarse_basis.rotational_diagnostics(bank),
                )
            )
    paths = [Path(m.__file__) for m in (acquisition, templates, coarse_basis)]
    return dict(
        rate=RATE,
        frequencies=BINS.tolist(),
        sources={str(p): _sha(p) for p in paths},
        geometries=blocks,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    save_json(parser.parse_args().out, audit())
