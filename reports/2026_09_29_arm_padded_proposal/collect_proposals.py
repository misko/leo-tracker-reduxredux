"""Apply the frozen proposal validator to an explicitly selected experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_29_arm_float_proposal/validate_host.py'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--full',action='store_true')
    parser.add_argument('--omit',choices=('lag1','lag3','lag5','power'))
    args=parser.parse_args()
    binary=args.binary.resolve();out=args.output.resolve()
    text=SOURCE.read_text()
    text=text.replace('output = HERE / ("host704-v1" if args.full else "host32-v1")','output = Path('+repr(str(out))+')')
    text=text.replace('binary = HERE / "builds/host-v1/proposal_probe"','binary = Path('+repr(str(binary))+')')
    if args.omit:
        text=text.replace('"--combined-only"]','"--combined-only",'+repr('--omit='+args.omit)+']')
    if (binary.parent/'build-receipt.json').is_file():
        text=text.replace('binary.parent / "build.json"','binary.parent / "build-receipt.json"')
        text=text.replace('receipt["binary_sha256"]','receipt["binaries"][binary.name]')
    sys.argv=[str(SOURCE)]+(['--full'] if args.full else [])
    exec(compile(text,str(SOURCE),'exec'),{'__name__':'__main__','__file__':str(SOURCE)})
    (out/'collector.json').write_text(json.dumps({'validator':str(SOURCE),'validator_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'binary':str(binary),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'full':args.full,'omit':args.omit},indent=2)+'\n')

if __name__=='__main__':main()
