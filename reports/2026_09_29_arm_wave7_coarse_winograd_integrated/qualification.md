# Qualification decision

Reject integrated Winograd F(4,3) for the Wave7 regional coarse stage.

The fair standalone explicit-NEON microkernel was promising at a 0.5993 ratio,
but that benchmark covered one transformed chunk. Integrated V1 measured
974.934986 ms total and 257.883603 ms coarse. The bounded V2 fix used live
four-epoch accumulators and the baseline vector magnitude path, yet measured
1004.373795 ms total and 287.538837 ms coarse. The float-final V2 control was
856.661454 ms total and about 134 ms coarse. Both integrated variants are clear
regressions.

Scientific behavior remained stable. Host32 recovered 834/843. The fresh V2
host704 audit recovered 19,217/19,581, and `hit-identity-diff-v2.json` reports
zero lost and zero gained identities relative to float-final V2. The matched
physical V2 panel retained 119 hits and emitted 182 objects.

The negative result is explained by generated-code and structural evidence:
the integrated kernel pays transforms and inverse transforms for every
three-tap chunk, creates high register pressure and stack traffic, and must
accumulate full-symbol outputs before the vector magnitude. Halving pointwise
complex multiplies alone did not reduce total coarse cost. No further variants
are authorized from this experiment.

V1 evidence remains under `builds/`, `host32/`, `host704/`, and `arm4/`. V2
evidence remains under `builds-v2/`, `host704-v2/`, and root's physical result
files. These artifacts are preserved independently.
