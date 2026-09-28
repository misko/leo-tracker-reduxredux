"""Evaluate measured FFTW plans without changing sample support or FFT sizes."""
import shutil
from build import HERE,build
from prepare_diff import replace
root=HERE/'work/fftmeasure';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/coarsev2/src',root/'src')
p=root/'src/native_presence/fft32_fftw.c';s=p.read_text()
s=replace(s,'FFTW_FORWARD,FFTW_ESTIMATE','FFTW_FORWARD,FFTW_MEASURE')
p.write_text(s);build('fftmeasure',root)
