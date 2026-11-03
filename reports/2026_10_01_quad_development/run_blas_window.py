"""Cold baseline runner with only the numerically equivalent acquisition replaced."""
import time
START=time.monotonic()
import run_window
from acquire_blas import acquire_blas


if __name__=='__main__':
    run_window.START=START
    run_window.acquire=acquire_blas
    run_window.main()
