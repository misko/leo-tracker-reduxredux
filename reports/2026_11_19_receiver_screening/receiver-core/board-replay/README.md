# Physical development-board replay

Both current SSH routes rejected the stored host key before login. There is no physical Cortex-A9 timing from this check. The prepared replay uses the same static ARMv7 executable and genuine saved-IQ fixture as the earlier offline acquisition benchmark, with the epoch range reduced to make one short board call. [Access receipt](access.json) · [Earlier offline benchmark](../../detector-origins/embedded/README.md)

| Route checked on 2026-11-19 UTC | Read-only preflight result |
| --- | --- |
| Development LAN `root@192.168.1.15`, 15:48:29 | Endpoint responded to SSH. Strict checking rejected the existing ED25519 host pin. Exit 255, before user authentication. |
| Attached USB Ethernet `root@192.168.2.1`, 15:49:02 | `enx00e022698b24` and the unopened `ttyACM0` link shared the USB parent with the expected development serial ending `4759d`. Strict checking rejected this route’s existing ED25519 host pin. Exit 255, before user authentication. |

The documented project pin for the historical LAN deployment is root-owned and unreadable to the current account. The checks used the existing account pins. Neither preflight reached the remote shell, so Linux status, idle state and tmpfs capacity could not be established. The production timer remained active on the host and the production scanner identified the separate serial ending `a5d4d`. No serial, radio, or IIO operation took place, and no benchmark input was sent. [Development device record](../../../../docs/operations/continuous-scanner-implementation.md) · [Documented SSH account and pin](../../../../tools/run_arm_cadence.py)

## Short authenticated capsule

The stream contains the unchanged static Cortex-A9 executable and a derived input for DS26-0036 visit 1 RX0. The input bytes differ from the original capsule only in the epoch count, 13,333 to 512. This retains all 21 CFO bins, 12 anchors, 15 frame offsets and authentic samples. A local rerun of the portable x86 executable reproduced the archived full-grid digest. Its shorter output was byte-identical to the first 512 epochs of each original CFO row. QEMU agreed on all 10,752 cells within `5.56e-17` and produced SHA-256 `4d308ac11a0d4341d3ed70c2c51778253656177fcbf38f98a38d86a01bf6f848`. [Payload](payload.json) · [Verification](offline-verification.json)

One x86 call took 43.3 ms process CPU, including 32.8 ms in the folded grid. One Cortex-A9 **QEMU** call took 1.748 s process CPU and 1.782 s monotonic time, including 1.715 s grid CPU. These are the reduced capture-era coarse stage and its file input/output. They do not measure the full detector, localization, or physical board timing.

## Running the offline stream after authentication

Build from the repository root. This reads the existing authenticated offline package and writes a new file exclusively in local scratch. Keep the generated receipt with its stream.

```sh
python -m tools.pipeline_eval.qualification.capture_board_replay \
    prepare "$scratch/folded-first-512-armv7.tar.gz" > "$scratch/payload.json"
```

Use an existing verified host pin and credentials for the development device. These commands use a Bash array for the SSH flags. Set `development_host` to the authenticated route and `approved_pin` to its readable verified host-key file. The preflight inspects the ARM architecture, expected serial, system load and processes, timers where available, memory, tmpfs and installed tools. Inspect the returned schedule and idle state before submitting the benchmark.

```bash
board_ssh=(-T -o ConnectTimeout=5 -o ConnectionAttempts=1 -o BatchMode=yes
           -o StrictHostKeyChecking=yes -o UpdateHostKeys=no
           -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no
           -o ForwardAgent=no -o ClearAllForwardings=yes -o ControlMaster=no
           -o "UserKnownHostsFile=$approved_pin")
replay_module=tools.pipeline_eval.qualification.capture_board_replay
board_cmd=$(python -m "$replay_module" preflight-command) || exit 1
timeout 10s ssh "${board_ssh[@]}" "$development_host" \
    "$board_cmd" </dev/null
```

After a successful read-only preflight confirms the correct idle development board, stream one capsule through stdin.

```bash
board_cmd=$(python -m "$replay_module" replay-command "$scratch/payload.json" \
    "$scratch/folded-first-512-armv7.tar.gz") || exit 1
timeout 42s ssh "${board_ssh[@]}" "$development_host" \
    "$board_cmd" \
    < "$scratch/folded-first-512-armv7.tar.gz" > "$scratch/board-receipt.txt"
```

The replay rechecks identity and active-process indicators before making a private directory on executable tmpfs. It caps the stream at 4 MiB and verifies the archive, executable and input hashes. The process uses `nice -n 19`, CPU 0 and a board-local 28-second hard limit. The shell emits worker timings and the completed grid digest, then removes the files it created. Timing is accepted only after exit 0, exactly 86,016 output bytes and a matching numerical digest. A timeout yields an incomplete attempt. [Artifact hashes](SHA256SUMS)
