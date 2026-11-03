"""Bounded transfer of previously available scalar scorer optimizations.

Reuse the sealed oracle-coordinate harness. No discovery performance claims.
"""
import importlib.util
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_29_arm_scoring_budget'
spec=importlib.util.spec_from_file_location('budget_runner',BASE/'run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.HERE=HERE
if not (HERE/'probe.c').exists():shutil.copyfile(BASE/'probe.c',HERE/'probe.c')
original_run=runner.subprocess.run

def build_and_run(command, *args, **kwargs):
    if isinstance(command,list) and command[0].endswith('arm-linux-gnueabihf-gcc'):
        if '--magnitude' in sys.argv:command.insert(1,'-DLEO_PRESENCE_BOUNDED_MAGNITUDE=1')
        if '--limited-complex' in sys.argv:
            command.insert(command.index('-fno-fast-math')+1,'-fcx-limited-range')
        if '--explicit-dot' in sys.argv:
            build=Path(command[command.index('-o')+1]).parent
            presence=build/'src/native_presence/presence.c'
            old='''                correlations[0][symbol-first_symbol] += received*w->glrt_exact_rotated[k];
                correlations[1][symbol-first_symbol] += received*w->glrt_control_rotated[k];'''
            new=(HERE/'explicit_dot.inc').read_text()
            text=presence.read_text(); assert text.count(old)==1
            presence.write_text(text.replace(old,new))
        if '--raw-ci16' in sys.argv:
            command.insert(1,'-DRAW_CI16')
            build=Path(command[command.index('-o')+1]).parent
            presence=build/'src/native_presence/presence.c'
            old='if (integer) received = w->samples[start+k+integer_offset];'
            new='''if (integer) {
                    size_t index=4*(size_t)(start+k+integer_offset);
                    __real__ received=(double)diagnostic_ci16[index];
                    __imag__ received=(double)diagnostic_ci16[index+1];
                }'''
            text=presence.read_text(); assert text.count(old)==1
            text=text.replace(old,new)
            signature='''    double cfo, double offset, int frame_limit, int final_scoring, double result[3])
{'''
            assert text.count(signature)==1
            text=text.replace(signature,signature+'''
    /* This CI16 diagnostic deliberately supports only the original final
     * scorer's zero fractional offset; never read an unpopulated FP64 view. */
    if (offset != 0.0) return -1;''')
            presence.write_text(text)
    return original_run(command,*args,**kwargs)

runner.subprocess.run=build_and_run
if __name__=='__main__':runner.main()
