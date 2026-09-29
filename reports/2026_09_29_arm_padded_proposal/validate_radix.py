"""Run the unchanged all-rate proposal validator with explicit binary/output."""
import importlib.util
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_29_arm_float_proposal/validate_host.py'
text=SOURCE.read_text().replace('HERE = Path(__file__).resolve().parent', 'HERE = Path('+repr(str(HERE))+')')
text=text.replace('"host704-v1" if args.full else "host32-v1"', '"host704-radix-v1" if args.full else "host32-radix-v1"')
text=text.replace('"builds/host-v1/proposal_probe"', '"builds/host-radix-v1/proposal_probe"')
exec(compile(text,str(SOURCE),'exec'),{'__name__':'__main__','__file__':str(SOURCE)})
