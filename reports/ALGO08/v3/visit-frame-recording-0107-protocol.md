# Physical DS30-0107 conventional visit-frame writer protocol

Use the private standard-format writer and the unchanged visit-frame codec and readback from the complete DS30-0016 result. Freeze the signed resident source with the input configuration SHA-256 `9fa1679995324bce268933961903b54cba742c21fbe151f716fe348572c029cb` and admission SHA-256 `81a5aa37a01356e56619945b194c831314fdf856175c55a1f90492b2585d6260`. They bind the complete 29-visit recording, the 33,519,983-byte compressed member, its signed index, original ordinary inventory and raw authority. Require 27 full visits, one 136,857-sample cancelled visit and one zero-sample capacity skip. The frozen qualification receipt from DS30-0016 covers actual sidecar and compressed suffix corruption for this codec. [Configuration](visit-frame-recording-0107-input.json) · [Preceding physical writer and qualification](visit-frame-recording-0016.md) · [Original resident stage](continued-cfo-small-raw.md)

Admit only the exact existing tmpfs source and verify full page residency before creating output. Run as `leo` in one common Gauss lock slot on CPU 2 at nice 15 and best-effort I/O priority 7, with one numerical thread. Set a 180 s lock wait, a 20 s worker deadline with a 2 s termination grace, and a 100,000,000-byte owned-buffer plus retained archive bound. Emit one archive in `/dev/shm/leo-v3-frame-visit-0107-recording01` with a new UUID. Keep the source untouched. No backing waveform reads, cache eviction, RF work, receiver run, or scientific solve are in the writer trial.

Record wall and CPU separately for passive source admission, signed original member authentication and hydration, installed writer constructor/appends/finish, seek-table write and sync, installed full independent readback with reference prefix hashes, separate full-authenticated seek readback, and detached authority write and sync. Record charged input blocks, major faults, original and emitted extents, and retained bytes. Report whole process elapsed/user/system separately from worker scopes. The clock for prepared archive writing includes writer, seek-table and detached-authority work. First use of a converted legacy archive adds charged authentication and hydration. Keep independent validation separately itemized. The sync boundary is tmpfs.

Require exact original index and whole decoded member hashes, full ordered per-window IQ hashes, and independently verified prefix byte counts and digests, including zero and partially filled visits. Compare capture metadata plus status, stop reason and failure. Keep original lifecycle timestamps in the detached authority while the new ordinary manifest carries its own writer timestamps. Publish new standard-format manifest and inventory digests with their own raw authority. Bind each optional table to that fresh member and publish its digest in the detached recording authority after independent verification. The follow-on paired analysis is a separate task using the same candidate implementation and options as the DS30-0016 pair if its gate passes.

```sh
repo=/dev/shm/leo-v3-frame-visit-0107-recording
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=/dev/shm/leo-v3-frame-visit-0107-recording01
plan="$repo/reports/ALGO08/v3/visit-frame-recording-0107-input.json"
pin=9fa1679995324bce268933961903b54cba742c21fbe151f716fe348572c029cb

sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  /usr/bin/flock -x -w 180 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  /usr/bin/env PYTHONPATH="$repo:$repo/reports/ALGO08/v3:$release/src:$release:$payload" \
  PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /usr/bin/time -f 'process wall_s=%e user_s=%U system_s=%S input_blocks=%I major_faults=%F' \
  /usr/bin/timeout -k 2s 20s "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.visit_frame_recording_0016 "$out" --input "$plan" --input-sha256 "$pin"
```
