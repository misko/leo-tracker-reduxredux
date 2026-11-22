"""Deterministic acceleration inside one full-data native variational solve."""

from pathlib import Path
import subprocess

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_bound_statistics import SOURCE_SHA256, replace


def build(output):
    source = native_bound.SOURCE
    if native_bound.digest(source) != SOURCE_SHA256:
        raise ValueError("Incompatible native bound source")
    text = replace(source.read_text(), "/* All work belongs",
                   Path(__file__).with_suffix(".h").read_text() + "\n/* All work belongs")
    text = replace(text, "3*sz+(l->qmax?l->qmax:1);", "3*sz+(l->qmax?l->qmax:1)+3*(k+t);")
    text = replace(text, "    /* Current group Gram/RHS", """
    double *first=row_f+sz,*proposal=first+k+t,*ordinary=proposal+k+t;
    int have_first=0,verify=0;
    double ordinary_change=0.;
    /* Current group Gram/RHS""")
    text = replace(text, "if(z>change)change=z;rate[g]=next_rate[g];}", "if(z>change)change=z;}")
    text = replace(text, "if(z>change)change=z;prate[j]=next_prate[j];}", "if(z>change)change=z;}")
    text = replace(text, "        performed++;", """
        performed++;
        if (verify && change>ordinary_change) {
            /* Resume the ordinary map after rejecting the farther initialization. */
            memcpy(rate,ordinary,k*sizeof(double));
            memcpy(prate,ordinary+k,t*sizeof(double));
            change=INFINITY;
            verify=0;
            accel_rejected++;
            continue;
        }
        verify=0;
        if (change>=1e-5 && iteration+2<budget) {
            if (!have_first) {
                for (int g=0;g<k;g++) first[g]=log(next_rate[g]/rate[g]);
                for (int j=0;j<t;j++) first[k+j]=log(next_prate[j]/prate[j]);
                have_first=1;
            } else {
                have_first=0;
                if (extrapolate_rates(k,t,rate,prate,next_rate,next_prate,first,beta0,pb0,proposal)) {
                    memcpy(ordinary,next_rate,k*sizeof(double));
                    memcpy(ordinary+k,next_prate,t*sizeof(double));
                    memcpy(rate,proposal,k*sizeof(double));
                    memcpy(prate,proposal+k,t*sizeof(double));
                    ordinary_change=change;
                    change=INFINITY;
                    verify=1;
                    accel_attempted++;
                    continue;
                }
            }
        }
        memcpy(rate,next_rate,k*sizeof(double));
        memcpy(prate,next_prate,t*sizeof(double));
    """)
    output = Path(output)
    generated = output.with_suffix(".c")
    generated.write_text(text)
    subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror", str(generated),
                    "-lm", "-o", str(output)], check=True, timeout=30)
