"""Reuse the frozen numerical runner with only its input preparation port replaced.

The process is fresh for each scan. The unchanged runner owns acquisition,
initialization, budgets, solver, mode selection, and receipt/source sealing.
Its external supervisor counts startup as part of the 90-second limit.
"""
import run_fast_pipeline as pipeline
from heldout_adapter import prepare_heldout

if __name__ == '__main__':
    pipeline.prepare = prepare_heldout
    pipeline.main()
