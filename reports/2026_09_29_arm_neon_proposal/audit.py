#!/usr/bin/env python3
"""Verify NEON proposal build receipts and generated ARM instructions."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=[]
for receipt_path in sorted((ROOT/'builds').glob('*/build-receipt.json')):
    receipt=json.loads(receipt_path.read_text());base=receipt_path.parent
    for name,digest in receipt['binaries'].items():checks.append((f'binary:{receipt["target"]}:{name}',sha(base/name)==digest))
    for name,digest in receipt['sources'].items():checks.append((f'source:{receipt["target"]}:{name}',sha(base/name)==digest))
    text=' '.join(' '.join(x['command']) for x in receipt['commands'])
    checks.append((f'strict-fp:{receipt["target"]}','-fno-fast-math' in text and '-ffast-math' not in text))
arm=ROOT/'builds/arm/proposal_probe_arm'
objdump=subprocess.run(['/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-objdump','-d',str(arm)],capture_output=True,text=True,check=True).stdout
checks += [('arm-vld4-deinterleave','vld4.16' in objdump),('arm-vst2-interleaved','vst2.32' in objdump),('arm-no-fma','vfma.' not in objdump)]
source=(ROOT/'sources/proposal_probe.c').read_text()
checks += [('source-explicit-products','vmulq_f32' in source and 'vaddq_f32' in source and 'vsubq_f32' in source),
           ('source-no-neon-mla','vmlaq_' not in source and 'vmlsq_' not in source),
           ('source-scalar-tail','fold_scalar(time+k,support+k' in source)]
result={'schema':'arm-neon-proposal-audit/v1','passed':all(v for _,v in checks),'checks':[{'name':k,'passed':v} for k,v in checks]}
(ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['passed']:raise SystemExit('audit failed')
