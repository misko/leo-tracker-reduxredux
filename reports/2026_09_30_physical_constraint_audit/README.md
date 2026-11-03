# Physical constraint evidence audit

The read-only [collection receipt](evidence.json) checks the current gauss host, its clock evidence and the expected DS10 pose companions. It does not establish historical capture UTC accuracy or calibrated antenna pose.

Current timedatectl reports NTP enabled and synchronized. The retained chrony journal has source-selection events, including one on September 26, but these are not regular offset measurements. Tracking/statistics logging is commented out in the inspected configuration and the current chrony log directory is empty. Current chronyc offsets cannot certify September 26–29 capture timestamps or the SDR sampling clock.

None of the 24 expected DS10 companions exists at the documented local pose-companion paths at audit time. This does not exclude historical copies or files elsewhere. The station authority documents an operator roof reference and nominal fixture geometry; receiver elevation, physical/software RX mapping and RF phase centers remain unverified. DS10 installation continuity needs independent evidence.

The positive [roof reception direction result](../2026_09_27_roof_direction_subset/REPORT.md) remains valid within its scope. These missing physical constraints explain why nominal cone tests are not a definitive test of calibrated compass and antenna geometry.

The collection script preserves exact commands, timestamps, return codes, outputs and source hashes. No service settings, recordings or archive paths were changed.
