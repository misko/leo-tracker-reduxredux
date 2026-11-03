# Correlated conditional receiver states

The independent-state geometry model passed six development scans but failed
the separate compatible recording (5972.7 to 6136.0 m). Do not promote it.
Freeze this distinct follow-up before calibration. No DS11 errors choose its
parameters: reuse donor 0 training visits, validate donor 1 held visits and
retain all earlier failures.

Given source detection, model receiver states 1/2/3 as a continuous-time refresh
process. Between successive detected opportunities separated by dt, transition
is rho*I+(1-rho)*p(t), rho=exp(-dt/tau), where p(t) is the normalized conditional
receiver distribution. This limits repeated evidence from persistent reception
states. It does not model source absence, discovery or absolute missed detection.
Unknown/held states are marginalized by filtering, never plugged in as known.
The times and source membership are conditioned design variables. Candidate LOS
and source labels retain the original conditional calibration limitations.

Fit receiver-only, elevation and signed arms with the previous offset/slope
priors/bounds plus log(tau) in log(.01)..log(60), normal prior scale 3 centered
at zero. Start from each independently fitted arm's frozen offsets/slope with
tau .1, 1, 10 seconds. Choose training objective only; 90 seconds per arm.
Check analytic derivatives and require convergence. Validate signed versus
temporal receiver-only/elevation, frozen swap and seeded same-RF source-geometry
permutation. Require held score wins against all four and >half supported source
wins versus temporal receiver-only. Also report against independent signed score
on identical held conditioning. Only a passing transfer screen justifies DS11
integration. Time dependence is inferred, not assumed proven by this protocol.
