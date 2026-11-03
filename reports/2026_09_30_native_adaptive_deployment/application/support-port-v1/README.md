# Optional support port application release

Release `4f4389d74a3aed2b` is installed on PLUTO+ `192.168.1.15` at
`/mnt/glrtbench/native-adaptive/live-current`. The prior release remains
available at `applications/3f3c1badd6e740ec`. Activation ran the no-capture
capability command; it did not start RF collection or an automatic service.

The application can now accept an optional neutral support derivation port.
It copies the profile metadata, rejects incomplete bindings, and reports
deferred support failures before cancelling acquisition. Session owns deferred
processing through its existing bounded queue and analysis owner. The CLI
continues to select the portable implementation and retains its v4 contract.
No concrete server math profile is linked into this release.

Host Analysis and fake-provider CLI tests pass, including ASan/UBSan with
halt-on-error. Physical ARM unit and fake-provider CLI tests pass in 0.744 s
and 0.063 s respectively. Full saved-event host replay with two analysis
workers accepts 11,747 observations, reconstructs 64 tracks, drops none, and
exactly reproduces weighted MSE 64906.771460780015.

Review caught and corrected a temporary string-view lifetime error in a test,
a missing default aggregate initializer, and an attempted change that made
portable duplicate rejection fatal. The final implementation uses the existing
Session consume wrapper and preserves portable rejection accounting.

The generic deferred profile separately passes full physical DS9 replay; see
the [receipt](../../runtime/session-deferred-physical-v1/receipt.json). This
release does not qualify continuous real-time performance, full strict server
parity, or a Pi/USB capture device. The five-second freshness gate remains open.
