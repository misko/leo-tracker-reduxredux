"""Hash-bound fused evaluator adapter for the sealed DS8/DS9 panel."""
from pathlib import Path
import hashlib

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_29_arm_subsecond/evaluate.py'
EXPECTED='ea0e027f0d5b2cabd57224a6ad6497b8e2cc6a8ed062cab039ea242135efc8d7'

def adapted_source():
    raw=SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==EXPECTED
    source=raw.decode()
    replacements={
        'for path in [*paths, raw, region]:':'for path in [*paths, raw]:',
        'str(raw), str(region)]':'str(raw)]',
        "args = parser.parse_args()":"args = parser.parse_args()\n    assert args.top == 4 and args.radius == 2, 'Transfer panel uses fused top4/radius2'",
        'search only, proposal/capture excluded; compare standard-hit audit for detection recovery':'fused proposal plus search; saved-IQ read and initial setup excluded',
    }
    for old,new in replacements.items():
        assert source.count(old)==1,old
        source=source.replace(old,new)
    return source

if __name__=='__main__':
    exec(compile(adapted_source(),str(SOURCE),'exec'),{'__name__':'__main__','__file__':str(Path(__file__).resolve())})
