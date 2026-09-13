"""Exact short-profile/binary qualification on the authorized .20 radio."""
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,'/home/mouse9911/gits/plutosdr-fw-radio20-tracking/scripts')
import qualify_glrt_cpu_live20 as live

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('output directory required')
    binary=live.EVIDENCE/'glrt-cpu-live-observer3-v2'
    if hashlib.sha256(binary.read_bytes()).hexdigest()!='ecc236de41dac2b85c7ed44916bff679ffdda318e680345e907df44720954f29':
        raise SystemExit('unreviewed binary')
    output=Path(sys.argv[1])
    sys.argv=[__file__,'--deployment',str(live.EVIDENCE/'deploy60-revisits-v1/receipts/0afb2dfe-42c4-43f7-84eb-0d5d29dfd6cb.json'),
              '--rate','60000000','--binary',str(binary),'--blocks','1536','--observer-spacing','3',
              '--lo-hz','1690312500','--output',str(output)]
    live.main()
