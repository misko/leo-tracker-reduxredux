"""Compose the 96-iteration worker with unchanged optimized acquisition."""
import time
START=time.monotonic()
import run_seed_limit_96
from acquire_blas import acquire_blas


if __name__=='__main__':
    run_seed_limit_96.START=START
    run_seed_limit_96.acquire=acquire_blas
    run_seed_limit_96.main()
