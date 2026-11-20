#!/bin/sh
set -eu

serial=104000b29905000e17000800065934759d
binary_sha=7a53b4f8a0c14c1b78557702c72d7cfca16aa628b9d89cbe6c3ae0a0cd09de74

fail() { printf '%s\n' "$*" >&2; exit 1; }

mode=${1:-}
case "$mode" in preflight|replay) ;; *) fail 'Expected preflight or replay';; esac
case "$(uname -m)" in armv7l) ;; *) fail 'Expected the ARMv7 development board';; esac

identity=''
for path in /sys/kernel/config/usb_gadget/*/strings/*/serialnumber \
    /sys/firmware/devicetree/base/serial-number /proc/device-tree/serial-number; do
    if [ -r "$path" ] && [ "$(tr -d '\000\r\n' < "$path")" = "$serial" ]; then
        identity=$path
        break
    fi
done
[ -n "$identity" ] || fail 'Could not authenticate the expected development serial from local sysfs'
printf 'development_serial=%s\nidentity_path=%s\n' "$serial" "$identity"

tmpfs=''
for directory in /tmp /dev/shm; do
    candidate=$(readlink -f "$directory") || continue
    if awk -v p="$candidate" '$2==p && $3=="tmpfs" && $4 !~ /(^|,)noexec(,|$)/ {
        usable=1
    } END {exit !usable}' /proc/mounts; then
        tmpfs=$candidate
        break
    fi
done
[ -n "$tmpfs" ] || fail 'No approved executable tmpfs at /tmp or /dev/shm'

uname -a
uptime
cat /proc/loadavg
sed -n '/^MemTotal:/p; /^MemFree:/p; /^MemAvailable:/p; /^SwapTotal:/p' /proc/meminfo
df -k "$tmpfs"
procs=$(ps -o pid,comm) || fail 'Could not inspect board processes'
printf '%s\n' "$procs"
ls -ld /etc/crontabs /etc/cron* /var/spool/cron /etc/systemd/system 2>/dev/null || :
if command -v systemctl >/dev/null; then systemctl list-timers --all --no-pager; fi
for tool in head tar sha256sum nice timeout taskset mktemp wc; do
    command -v "$tool" >/dev/null || fail "Unavailable board command $tool"
done
if [ "$mode" = preflight ]; then exit 0; fi

if printf '%s\n' "$procs" | grep -Ei 'readscan|fast.?scan|continuous.?scan|capture|streamer' \
    >/dev/null; then
    fail 'A possible acquisition process is active'
fi
for tcp in /proc/net/tcp /proc/net/tcp6; do
    [ -r "$tcp" ] || continue
    if awk '($2 ~ /:76DF$/ || $3 ~ /:76DF$/) && $4=="01" {active=1}
        END {exit !active}' "$tcp"; then
        fail 'An established IIO transport was visible'
    fi
done
awk '/^MemAvailable:/{ok=($2>=32768)} END{exit !ok}' /proc/meminfo \
    || fail 'Below 32 MiB available RAM'
df -k "$tmpfs" | awk 'NR>1 {ok=($4>=16384)} END{exit !ok}' \
    || fail 'Below 16 MiB free in the executable tmpfs'
for digest in "${2:-}" "${3:-}"; do
    [ "${#digest}" -eq 64 ] || fail 'Both prepared SHA-256 values are required'
    case "$digest" in *[!0-9a-f]*) fail 'Malformed SHA-256';; esac
done

umask 077
scratch=$(mktemp -d "$tmpfs/leo-board-replay.XXXXXX")
cleanup() {
    rm -f "$scratch/payload.tgz" "$scratch/capture-board-folded" "$scratch/folded.input" \
        "$scratch/scores.bin" "$scratch/timing.json"
    rmdir "$scratch"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
head -c 4194305 > "$scratch/payload.tgz"
[ "$(wc -c < "$scratch/payload.tgz")" -le 4194304 ] || fail 'Capsule exceeds 4 MiB'
printf '%s  %s\n' "$2" "$scratch/payload.tgz" | sha256sum -c - >&2
# Send only the authenticated fixed members to predetermined paths.
tar -xzOf "$scratch/payload.tgz" capture-board-folded > "$scratch/capture-board-folded"
tar -xzOf "$scratch/payload.tgz" folded.input > "$scratch/folded.input"
printf '%s  %s\n' "$binary_sha" "$scratch/capture-board-folded" | sha256sum -c - >&2
printf '%s  %s\n' "$3" "$scratch/folded.input" | sha256sum -c - >&2
chmod 0700 "$scratch/capture-board-folded"

status=0
timeout -s KILL 28 nice -n 19 taskset 0x1 "$scratch/capture-board-folded" "$scratch/folded.input" \
    > "$scratch/scores.bin" 2> "$scratch/timing.json" || status=$?
printf 'benchmark_exit=%s\n' "$status"
cat "$scratch/timing.json"
[ "$status" -eq 0 ] || fail 'Numerical worker failed or reached the 28 s limit'
[ "$(wc -c < "$scratch/scores.bin")" -eq 86016 ] || fail 'Unexpected score-grid length'
printf 'score_sha256='
sha256sum "$scratch/scores.bin" | awk '{print $1}'
