"""Isolated production-wave8 build with a narrow fine-frequency cache."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import ROOT, local_output
from . import ordinary_front_build as stock
from .full_v5_check import _sha

HEADER = ROOT / "tools/pipeline_eval/variants/ordinary_glrt_fine.h"


def overlay(source):
    edits = (
        ("#include <fftw3.h>", '#include <fftw3.h>\n#include "ordinary_glrt_fine.h"'),
        (
            "    int count, transforms, hits, calls;",
            "    int count, transforms, hits, calls;\n    size_t band_radius;\n"
            "    double template_energy;",
        ),
        (
            "    ++cache->calls;",
            "    ++cache->calls;\n"
            "    cache->band_radius=leo_fine_band_radius(cache->workspace->size,w->fine_step_hz);",
        ),
        (
            "        double template_energy=0;\n        memset(w->base,0,w->n*sizeof(*w->base));",
            "        const int prepared=w->coarse_input_prepared &&\n"
            "            w->coarse_prepared_count>=sample_count;",
        ),
        (
            "        for(int symbol=2;symbol<302;symbol+=symbol_step) {\n"
            "            int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);\n"
            "            for(int k=begin;k<end;++k) "
            "{template_energy+=power(w->exact[k]);w->base[k]=conj(w->exact[k]);}\n"
            "        }",
            "        if (!entry) for(int symbol=2;symbol<302;symbol+=symbol_step) {\n"
            "            int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);\n"
            "            for(int k=begin;k<end;++k) cache->template_energy+=power(w->exact[k]);\n"
            "        }",
        ),
        (
            "                for(int k=begin;k<end;++k) {\n"
            "                    energy+=power(w->samples[start+k]);",
            "                if (prepared) "
            "energy+=leo_fine_span_energy(w->prefix,start+begin,start+end);\n"
            "                for(int k=begin;k<end;++k) {\n"
            "                    if (!prepared) energy+=power(w->samples[start+k]);",
        ),
        (
            "const double br=creal(w->base[k]);\n"
            "                    const double bi=cimag(w->base[k]);",
            "const double br=creal(w->exact[k]);\n"
            "                    const double bi=-cimag(w->exact[k]);",
        ),
        (
            "workspace->size*sizeof(float complex));\n            if(!item->spectra",
            "(2*cache->band_radius+1)*sizeof(float complex));\n            if(!item->spectra",
        ),
        (
            "            memcpy(item->spectra[item->frames],workspace->output,\n"
            "                workspace->size*sizeof(float complex));",
            "            leo_fine_band_copy(item->spectra[item->frames],workspace->output,\n"
            "                workspace->size,cache->band_radius);",
        ),
        ("sqrt(template_energy*energy);", "sqrt(cache->template_energy*energy);"),
        (
            "    memset(scores,0,(size_t)frequency_count*sizeof(*scores));",
            "    const size_t size=cache->workspace->size, radius=cache->band_radius;\n"
            "    if ((size_t)first_bin>radius && (size_t)first_bin<size-radius) return -1;\n"
            "    const size_t cell=leo_fine_band_index((size_t)first_bin,size,radius);\n"
            "    if ((size_t)frequency_count>2*radius+1-cell) return -1;\n"
            "    memset(scores,0,(size_t)frequency_count*sizeof(*scores));",
        ),
        (
            "        int bin=first_bin;\n",
            "",
        ),
        (
            "                score_out[f]+="
            "leo_fine_precision_magnitude(spectrum[bin])*reciprocal;\n"
            "                if(++bin==(int)cache->workspace->size) bin=0;",
            "                score_out[f]+="
            "leo_fine_precision_magnitude(spectrum[cell+f])*reciprocal;",
        ),
    )
    for before, after in edits:
        source = stock.replace(source, before, after)
    return source


def build(work, target):
    host = target == "host"
    control = stock.CONTROL_BUILD if host else stock.ARM_CONTROL / "build-receipt.json"
    receipt = json.loads(control.read_bytes())
    if any(_sha(stock.SOURCE / item) != sha for item, sha in receipt["sources"].items()):
        raise ValueError("The native source differs from the measured ordinary control")
    source = work / f"{target}-source"
    shutil.copytree(stock.SOURCE, source, ignore=shutil.ignore_patterns("__pycache__"))
    fine = source / "kernel/private/fine_precision.h"
    fine.write_text(overlay(fine.read_text()), encoding="utf-8")
    shutil.copyfile(HEADER, fine.with_name(HEADER.name))
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(stock.HOST_FFTW if host else stock.ARM_FFTW),
            "--target",
            receipt["target"],
            "--output-dir",
            str(work / target),
            "--work-dir",
            str(work / f"{target}-build"),
        ],
        check=True,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("target", choices=("host", "arm"))
    cli.add_argument("--work", required=True, type=Path)
    args = cli.parse_args()
    build(local_output(args.work), args.target)
