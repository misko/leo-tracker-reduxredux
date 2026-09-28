# Interrupted process

The execution tool returned exit code 143 (SIGTERM) during repeat one at 10 MS/s. No final runner traceback or terminal receipt was produced. The original `run.json` therefore remains incomplete; it is not an admitted complete result.

The cause of the SIGTERM is unknown. The experiment's own 2400-second watchdog raises `ReplayDeadline`, not SIGTERM. No scientific failure prompted this interruption. Completed raw rows are preserved unchanged. Recovery uses a separate, explicitly composite run with a verified predecessor hash and executes only missing evaluations; a new process has fresh runtime caches. This restart is disclosed rather than treated as an uninterrupted run or used to select favorable timings.

Independent audit found exactly 526 successful rows forming the declared rotated execution prefix, with zero failed rows. All 36 initial source hashes still matched. The prefix ends with repeat 1, original, 10 MS/s, visit 1106. Its SHA-256 is `104fc2d0e47c2dd993d3d8a30a0f66d8e2e840bb71cc5260acfad9f1b8a7d240`; 34 evaluations remain.
