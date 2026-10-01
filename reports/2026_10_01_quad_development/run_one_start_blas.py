"""Compose the unchanged start-count worker with the existing BLAS acquisition."""
import time
START=time.monotonic()
import run_seed_limit
from acquire_blas import acquire_blas


if __name__=='__main__':
    run_seed_limit.START=START
    run_seed_limit.acquire=acquire_blas
    run_seed_limit.main()
