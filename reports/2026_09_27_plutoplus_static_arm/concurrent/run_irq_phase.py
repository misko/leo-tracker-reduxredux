"""Temporarily move only the verified eth0 interrupt; always restore its mask."""
import json
import argparse
from pathlib import Path
import subprocess
import sys
from run_phase import remote, HERE


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--recorded-arrivals',action='store_true')
    args=parser.parse_args()
    name='combined-arrivals-irq1' if args.recorded_arrivals else 'combined-irq1'
    evidence=HERE/('ethernet-affinity-arrivals.json' if args.recorded_arrivals else 'ethernet-affinity.json')
    if evidence.exists(): raise ValueError('affinity experiment already exists')
    irq_line=remote("sed -n '/eth0/p' /proc/interrupts").decode()
    if len(irq_line.strip().splitlines())!=1 or not irq_line.lstrip().startswith('35:'):
        raise RuntimeError('eth0 IRQ identity changed')
    original=remote('cat /proc/irq/35/smp_affinity').decode().strip()
    if original not in ('1','2','3'): raise ValueError('unexpected affinity')
    state={'irq':35,'device':'eth0','original_mask':original,'original_interrupts':irq_line}
    evidence.write_text(json.dumps(state,indent=2)+'\n')
    try:
        remote("echo 2 > /proc/irq/35/smp_affinity")
        state['during_mask']=remote('cat /proc/irq/35/smp_affinity').decode().strip()
        state['during_effective_cpu']=remote('cat /proc/irq/35/effective_affinity_list').decode().strip()
        if state['during_mask']!='2' or state['during_effective_cpu']!='1': raise RuntimeError('IRQ pin failed')
        evidence.write_text(json.dumps(state,indent=2)+'\n')
        phase_args=['--recorded-arrivals','--jobs','330','--seconds','60'] if args.recorded_arrivals else ['--seconds','75']
        state['phase_exit']=subprocess.call([sys.executable,str(HERE/'run_phase.py'),name,'--capture','--core','0',*phase_args])
    finally:
        remote('echo '+original+' > /proc/irq/35/smp_affinity')
        state['restored_mask']=remote('cat /proc/irq/35/smp_affinity').decode().strip()
        state['restored_effective_cpu']=remote('cat /proc/irq/35/effective_affinity_list').decode().strip()
        evidence.write_text(json.dumps(state,indent=2)+'\n')
        if state['restored_mask']!=original: raise RuntimeError('IRQ restoration failed')
    if state['phase_exit']: raise RuntimeError('phase failed')


if __name__=='__main__': main()
