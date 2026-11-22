#!/usr/bin/env bash
# Run from the lab directory in an ordinary Ubuntu desktop session.
set -euo pipefail

if [[ $(id -u) == 0 ]]; then
    printf 'Run preflight as an ordinary user.\n' >&2
    exit 1
fi

. /etc/os-release
printf 'Distribution: %s\n' "$PRETTY_NAME"
printf 'Kernel: %s\n' "$(uname -r)"
printf 'Architecture: %s\n' "$(uname -m)"
bwrap --version
printf 'Cgroup filesystem: '
stat -fc %T /sys/fs/cgroup
printf 'User systemd: '
systemctl --user is-active default.target

for profile in 2 4; do
    printf 'P%s: ' "$profile"
    hello=$(python3 sandbox.py _worker --program ./probe "$profile" -- hello)
    [[ "$hello" == 'hello=1' ]]
    printf '%s\n' "$hello"
done

systemd-run --user --wait --pipe --collect --quiet \
    -p MemoryMax=64M -p MemorySwapMax=0 -p TasksMax=16 \
    -p CPUQuota=50% -p CPUQuotaPeriodSec=100ms \
    -- /bin/sh -eu -c '
        group=$(cut -d: -f3 /proc/self/cgroup)
        test "${group#/}" != "$group" && test "$group" != /
        base="/sys/fs/cgroup$group"
        for pair in "memory.max:67108864" "memory.swap.max:0" "pids.max:16" "cpu.max:50000 100000"; do
            file=${pair%%:*}
            expected=${pair#*:}
            value=$(cat "$base/$file")
            printf "%s = %s\n" "$file" "$value"
            test "$value" = "$expected" || exit 1
        done
        for file in memory.events pids.events cpu.stat; do
            test -r "$base/$file"
        done
    '

printf 'P5: '
hello=$(python3 sandbox.py run ./probe hello)
[[ "$hello" == 'hello=1' ]]
printf '%s\n' "$hello"
printf 'Preflight OK\n'
