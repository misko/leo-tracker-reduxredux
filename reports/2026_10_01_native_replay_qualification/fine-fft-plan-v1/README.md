# Rejected measured fine FFT plan

This isolated ARM benchmark uses the detector's static FP32 FFTW library and
5,000-point transform size. It creates the ordinary ESTIMATE plan first, then
a MEASURE plan with a one-second planning limit. It initializes identical
inputs after planning and executes 1,024 transforms per control/new/new/control
trial. Plans, wisdom, binary hash and timings are retained.

The measured plan is about 40% slower (1.601327 versus 1.148250 CPU seconds
per 1,024 transforms). Its maximum FFT-component difference is 3.05176e-5
on the deterministic synthetic input (control maximum magnitude 160.979).
Planning costs 0.132 CPU seconds. Reject this plan: it is neither faster nor
bit-identical. No detector source or production planning policy changed.
These isolated FFT results are not detector recovery or full-pipeline timing.
