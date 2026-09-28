"""Separately qualify bounded modulus in final GLRT; reject if gates change."""
import shutil
from build import HERE,build
from prepare_diff import replace
root=HERE/'work/goal40mag';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/goal40b/src',root/'src')
p=root/'src/native_presence/presence.c';s=p.read_text()
s=replace(s,'''                /* Keep libc magnitude in the final GLRT statistic. Tiny
                 * ceiling differences can be amplified by fractional peak
                 * interpolation on a nearly flat, non-pilot surface. */
                ceiling += cabs(w->input[k]);''',
    '''                /* Experimental bounded modulus: robust fallback remains
                 * for zero/subnormal/overflow/nonfinite squared magnitude.
                 * Flat-surface timing/CFO require separate full qualification. */
                ceiling += magnitude(w->input[k]);''')
p.write_text(s);build('goal40mag',root);build('goal40mag',root,host=True,sanitize=True)
