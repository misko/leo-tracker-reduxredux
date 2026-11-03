"""Metadata-only balanced temporal support; preserve the sparse70percent pilot."""

from pathlib import Path
import probe_ds23_historical_phase_consensus as engine
from ds23_historical_phase_consensus import balanced_temporal_split

OUT=engine.OUT/'balanced_boundary'
BULK=Path('/srv/bulk/leo/research/ds23-historical-phase-consensus-v2-20261021')


def main():
    engine.OUT=OUT;engine.BULK=BULK;engine.temporal_split=balanced_temporal_split
    engine.SPLIT_DESCRIPTION=('choose publication boundary maximizing minimum distinct training/held-future satellite support, '
        'then minimum row support; ties earliest; no phase outcomes; labels available by boundary and future issue times strictly after it')
    engine.main()


if __name__=='__main__':main()
