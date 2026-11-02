"""Use eight released slots for no-refit audit while four supplement workers run."""
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent

if __name__=='__main__':
    os.setpriority(os.PRIO_PROCESS,0,10)
    while not (ROOT/'completion.json').exists():time.sleep(5)
    from audit import main
    main(8,'initial_audit_summary.json')
