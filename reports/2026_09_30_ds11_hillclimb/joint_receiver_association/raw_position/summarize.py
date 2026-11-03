"""Reuse the identical frozen two-record geographic advancement gate."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('raw_position_summary',HERE.parent/'epoch_position/summarize.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.HERE=HERE
if __name__=='__main__':module.main()
