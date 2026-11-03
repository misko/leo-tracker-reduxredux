# Residual-preserving position perturbation recovery

Use the three original balanced_0 N8 panels and zero-height selected endpoints. For each track, choose its highest training posterior satellite component conditional on signal at that endpoint. Hold that candidate choice only for generating the injected perturbation; the refitted model retains all original candidates and the background mixture.

Inject separately +1 km east and +1 km north. For each observation add the chosen candidate's predicted frequency difference between the shifted and original position, retaining original timing. Preserve observed residuals, track offsets, masks, timestamps and banks. This transforms all eligible tracks, including those with weak signal responsibility. It is a conditional stress test, not a simulation of known real transmitters or an independent validation of candidate identity.

For each dataset/direction, refit the full ambiguous model from two fixed starts: original endpoint and injected endpoint. Choose the highest training score among qualified fits; retain failures. Report recovered E/N displacement, deviation from the injected displacement, timing adjustment and candidate changes. No reference coordinate enters generation or selection. A zero-shift identity and exact preservation of chosen-candidate residuals are required. No new RF or production edits.
