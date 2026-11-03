# DS10 conditional position and timing sensitivity

Use all tracks in the frozen DS10 N24 height-zero fit. Replay its training score and select each track's most probable candidate using the existing training-only conditional weights. Weight derivative observations by that candidate's conditional probability times signal responsibility. Do not drop weak tracks or use the exposed roof reference.

Differentiate predicted frequency at the fitted point with central steps 1 metre east/north and 10 microseconds timing. Repeat with half steps. Remove a separate training mean from every track's derivative columns, matching unconstrained constant-offset profiling. Then project out one shared timing derivative per scan by weighted least squares. Report training weighted RMS Hz per one-kilometre displacement, directional eigenvalues, information retention relative to fixed timing, and implied timing adjustments. Require unchanged visibility and less than 1% relative matrix change between derivative step sizes.

This is a conditional linearized design diagnostic, not the observed mixture Hessian, a 1 km nonlinear injection, a confidence bound or verified identity. It omits candidate uncertainty derivatives, noise correlations and systematic model error. Its scope is the failed DS10 transfer panel; earlier DS7–9 sensitivity tests remain separate.

One numerical thread, 120-second execution cap, existing derived banks only. No optimization, RF collection, raw IQ or location changes.
