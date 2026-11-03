"""Bounded31-refit uncertainty run; preserve the terminal63-refit timeout."""

from pathlib import Path
import probe_ds23_phase_clock_uncertainty as engine

OUT=engine.SOURCE_OUT/'bootstrap_v2'
BULK=Path('/srv/bulk/leo/research/ds23-phase-clock-uncertainty-v2-20261021')


def main():
    engine.OUT=OUT;engine.BULK=BULK;engine.REPLICATES=31;engine.WARM_STEPS=30
    engine.main()


if __name__=='__main__':main()
