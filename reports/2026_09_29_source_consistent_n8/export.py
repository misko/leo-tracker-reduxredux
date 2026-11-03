import importlib.util
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
path=HERE.parent/'2026_09_29_quality_metadata_corrected/export.py'
spec=importlib.util.spec_from_file_location('verified_export',path)
obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
obj.HERE=HERE
obj.main(sys.argv[1])
