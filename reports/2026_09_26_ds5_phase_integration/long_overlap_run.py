"""Reuse the frozen extractor in an isolated longer-overlap artifact directory."""
from pathlib import Path
import run

if __name__=='__main__':
    run.HERE=Path(__file__).resolve().parent/'long-overlap'
    run.main()
