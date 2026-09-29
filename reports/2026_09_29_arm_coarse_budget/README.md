# Coarse budget prototype

This snapshot derives from `limited-complex-v2`.  Its `fastscale-*` builds use
the fixed divisor 32768 for the coarse FP32 input conversion.  That path is
qualified only for known finite CI16 inputs, whose components are integral in
`[-32768,32767]`; it does not claim equivalence for arbitrary floating input.
The conversion and FP32 accumulation order are otherwise preserved.

The frame variants use 2, 4, 8, or 16 evenly spaced coarse frames, including
both endpoints.  They change coarse candidate selection and require separate
recovery auditing.  The final GLRT, conditioned CZT and their frame settings
are unchanged.  `build.py` creates host, sanitizer and ARM cross-build
snapshots; it does not run an ARM job.
