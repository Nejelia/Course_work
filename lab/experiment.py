#!/usr/bin/env python3
"""Run bounded positive and negative controls and write raw JSON plus CSV."""

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import platform
import secrets
import select
import socket
from statistics import median
import subprocess
import sys
import tempfile

import sandbox

LAB = Path(__file__).resolve().parent
PROBE = LAB / "probe"
COMMON_CASES = ("hello", "files", "pid", "net")
RESOURCE_CASES = ("tasks", "memory16", "memory128", "cpu")


@contextmanager
def process_marker(name):
    marker = subprocess.Popen([str(PROBE), "sentinel", name],
                              stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
    try:
        readable, _, _ = select.select([marker.stdout], [], [], 3)
        if not readable or marker.stdout.readline().strip() != "ready":
            raise RuntimeError("The trusted PID control did not start")
        yield
    finally:
        marker.terminate()
        marker.communicate(timeout=3)


def collect(profile, arguments, input_file, net_backend):
    if net_backend == "unshare" and profile in (2, 4):
        inner = sandbox.run_command(profile - 1, PROBE, arguments, input_file)
        command = ["unshare", "--user", "--map-current-user", "--net", "--", *inner]
    else:
        command = sandbox.run_command(profile, PROBE, arguments, input_file)
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, errors="replace", timeout=15)
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    lines = [line.removeprefix(sandbox.CGROUP_PREFIX) for line in result.stderr.splitlines()
             if line.startswith(sandbox.CGROUP_PREFIX)]
    return {"returncode": result.returncode, "values": values,
            "stdout": result.stdout, "stderr": result.stderr,
            "cgroup": json.loads(lines[-1]) if lines else None}


def unavailable(row):
    return any((
        row["stderr"].startswith("bwrap:") and any(
            marker in row["stderr"] for marker in
            ("Operation not permitted", "Permission denied", "No permissions to create")),
        "Failed to connect to" in row["stderr"] and "bus" in row["stderr"],
        "A separate systemd cgroup v2 is required" in row["stderr"],
        "Kernel cgroup limits differ" in row["stderr"],
        "/sys/fs/cgroup/" in row["stderr"] and "No such file" in row["stderr"],
    ))


def counter_delta(data, file, key):
    before = dict(line.split() for line in data["before"][file].splitlines())
    after = dict(line.split() for line in data["after"][file].splitlines())
    return int(after[key]) - int(before[key])


def validate(row, host_ns, unix_control, net_backend):
    profile = row["profile"]
    case = row["test"]
    values = row["values"]
    success = row["returncode"] == 0
    limited = profile == 5
    if case == "memory128" and limited:
        return (not success and row["cgroup"] is not None
                and counter_delta(row["cgroup"], "memory.events", "oom_kill") > 0)
    if not success or (limited and row["cgroup"] is None):
        return False
    if case == "hello":
        return values.get("hello") == "1"
    if case == "files":
        return (values.get("input_read") == "1" and values.get("scratch_errno") == "0"
                and values.get("hidden_errno") == str(errno.ENOENT if profile else 0)
                and values.get("input_write_errno") == str(errno.EROFS if profile else 0))
    if case == "pid":
        return (values.get("sentinel_visible") == ("0" if profile else "1")
                and all(
                    values.get("ns_" + name) is not None
                    and (values["ns_" + name] != inode) == (
                        profile in (2, 4, 5) if name == "net" else profile > 0)
                    for name, inode in host_ns.items()
                )
                and (not profile or (int(values.get("CapEff", "1"), 16) == 0
                                     and values.get("NoNewPrivs") == "1")))
    if case == "net":
        if "socket_setup_errno" in values:
            return False
        filtered = profile in (3, 4, 5)
        if filtered:
            return (values.get("socket_errno") == str(errno.EPERM)
                    and values.get("ipv6_socket_errno") == str(errno.EPERM)
                    and values.get("unix_socket_errno") == unix_control
                    and "connect_errno" not in values)
        connect_error = 0
        if profile == 2:
            connect_error = errno.ENETUNREACH if net_backend == "unshare" else errno.ECONNREFUSED
        return values.get("socket_errno") == "0" and values.get("connect_errno") == str(connect_error)
    if case == "tasks":
        if not limited:
            return values.get("children") == "24" and values.get("fork_errno") == "0"
        return (0 <= int(values.get("children", "-1")) < 24
                and values.get("fork_errno") == str(errno.EAGAIN)
                and counter_delta(row["cgroup"], "pids.events", "max") > 0)
    if case == "memory16":
        return (values.get("touched_mib") == "16"
                and (not limited or counter_delta(row["cgroup"], "memory.events", "oom_kill") == 0))
    if case == "memory128":
        return values.get("touched_mib") == "128"
    if case == "cpu":
        ratio = int(values["cpu_us"]) / int(values["wall_us"])
        row["cpu_ratio"] = round(ratio, 4)
        return (0 < ratio <= 1.05 and (not limited or (
            ratio <= 0.65 and counter_delta(row["cgroup"], "cpu.stat", "nr_throttled") > 0)))
    raise ValueError(f"Unexpected test case: {case}")


def measure(repetitions, smoke, working, host_ns, net_backend):
    hidden = working / "hidden.txt"
    public = working / "public.txt"
    hidden.write_text("PRIVATE DEMO DATA\n")
    public.write_text("PUBLIC DEMO DATA\n")
    marker = "sb" + secrets.token_hex(5)
    rows = []

    with socket.socket() as server, process_marker(marker):
        server.bind(("127.0.0.1", 0))
        server.listen(256)
        port = str(server.getsockname()[1])
        blocked = {}
        for repetition in range(1, repetitions + 1):
            unix_control = None
            for profile in range(5 if smoke else 6):
                cases = COMMON_CASES
                if profile in (4, 5) or (smoke and profile == 3):
                    cases += RESOURCE_CASES
                for case in cases:
                    row = {"repetition": repetition, "profile": profile, "test": case}
                    if profile in blocked:
                        row.update(status="UNAVAILABLE", reason=blocked[profile])
                        rows.append(row)
                        continue
                    if case == "files":
                        arguments = [case, str(hidden), "/input" if profile else str(public),
                                     "/tmp/probe-write" if profile else str(working / "probe-write")]
                    elif case == "pid":
                        arguments = [case, marker]
                    elif case == "net":
                        arguments = [case, port]
                    elif case.startswith("memory"):
                        arguments = ["memory", case.removeprefix("memory")]
                    else:
                        arguments = [case]
                    try:
                        input_file = public if case == "files" else None
                        row.update(collect(profile, arguments, input_file, net_backend))
                        if case == "hello" and not row["values"] and unavailable(row):
                            blocked[profile] = row["stderr"].strip()
                            row.update(status="UNAVAILABLE", reason=blocked[profile])
                        else:
                            if case == "net" and profile == 1:
                                unix_control = row["values"].get("unix_socket_errno")
                            valid = validate(row, host_ns, unix_control, net_backend)
                            row["status"] = "PASS" if valid else "FAIL"
                    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                        row.update(status="FAIL", reason=str(error))
                    rows.append(row)
    return rows


def version(*command):
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False,
                              timeout=3).stdout.splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return None


def save(output, metadata, rows):
    (output / "results.json").write_text(
        json.dumps({"environment": metadata, "rows": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    columns = ["repetition", "profile", "test", "status", "returncode", "cpu_ratio", "values",
               "cgroup", "reason"]
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, columns, extrasaction="ignore")
        writer.writeheader()
        for original in rows:
            row = original.copy()
            for name in ("values", "cgroup"):
                if row.get(name) is not None:
                    row[name] = json.dumps(row[name], ensure_ascii=False, separators=(",", ":"))
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=5, choices=range(1, 21),
                        metavar="N")
    parser.add_argument("--smoke", action="store_true",
                        help="permit environmental blocks and omit the systemd profile")
    parser.add_argument("--net-backend", choices=("bwrap", "unshare"), default="bwrap",
                        help="network namespace setup, unshare is available only for smoke")
    parser.add_argument("--output", type=Path, required=True, help="new results directory")
    args = parser.parse_args()
    if args.net_backend == "unshare" and not args.smoke:
        parser.error("--net-backend unshare requires --smoke")
    sandbox.validate_program(PROBE)
    binary = sandbox.require_bwrap()
    host_ns = {name: os.readlink(f"/proc/self/ns/{name}") for name in sandbox.NAMESPACES}
    metadata = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "os": platform.freedesktop_os_release().get("PRETTY_NAME"),
        "kernel": platform.release(), "architecture": platform.machine(),
        "python": platform.python_version(), "bubblewrap": version(binary, "--version"),
        "systemd": version("systemd-run", "--version"), "net_backend": args.net_backend,
        "unshare": version("unshare", "--version"),
        "cgroup_mount_present": Path("/sys/fs/cgroup/cgroup.controllers").exists(),
        "host_namespaces": host_ns, "repetitions": args.repetitions, "smoke": args.smoke,
    }
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="sandbox-coursework-") as directory:
        rows = measure(args.repetitions, args.smoke, Path(directory), host_ns, args.net_backend)
    save(args.output, metadata, rows)
    print(f"Results in {args.output}")
    for profile in sorted({row["profile"] for row in rows}):
        subset = [row for row in rows if row["profile"] == profile]
        totals = {state: sum(row["status"] == state for row in subset)
                  for state in ("PASS", "FAIL", "UNAVAILABLE")}
        print(f"P{profile}: " + ", ".join(f"{key}={value}" for key, value in totals.items()))
        ratios = [row["cpu_ratio"] for row in subset if "cpu_ratio" in row]
        if ratios:
            print(f"  CPU ratio: median={median(ratios):.3f}, min={min(ratios):.3f}, max={max(ratios):.3f}")
        reasons = sorted({row["reason"].splitlines()[0] for row in subset if row.get("reason")})
        for reason in reasons:
            print(f"  {reason}")
    return int(any(row["status"] == "FAIL" or (row["status"] == "UNAVAILABLE" and not args.smoke)
                   for row in rows))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as error:
        print(f"experiment: {error}", file=sys.stderr)
        sys.exit(2)
