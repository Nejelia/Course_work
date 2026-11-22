"""Measure one transient systemd group per trial for either launcher."""

import errno
import json
import os
from pathlib import Path
import secrets
import sys

from compare_runtime import capture, launch, process_group
from experiment import counter_delta

PREFIX = "COURSEWORK_RESOURCE "
FIELDS = (
    "memory.max", "memory.swap.max", "memory.events", "pids.max", "pids.events",
    "cpu.max", "cpu.stat",
)


def scenarios():
    regular = {"memory_mib": 256, "pids": 64, "cpu_pct": 100}
    for memory in (64, 128, 256):
        yield "memory", dict(regular, memory_mib=memory)
    for pids in (16, 24, 64):
        yield "tasks", dict(regular, pids=pids)
    for cpu in (25, 50, 100):
        yield "cpu", dict(regular, cpu_pct=cpu)


def read_group(path):
    snapshot = {name: (path / name).read_text().strip() for name in FIELDS}
    peak = path / "memory.peak"
    if peak.is_file():
        snapshot["memory.peak"] = peak.read_text().strip()
    return snapshot


def worker(spec):
    group = process_group("self")
    if not group or group == "/":
        raise RuntimeError("A dedicated systemd user cgroup is required")
    path = Path("/sys/fs/cgroup" + group)
    before = read_group(path)
    limits = spec["limits"]
    expected = {
        "memory.max": str(limits["memory_mib"] * 1024 * 1024), "memory.swap.max": "0",
        "pids.max": str(limits["pids"]), "cpu.max": f'{limits["cpu_pct"] * 1000} 100000',
    }
    if any(before[key] != value for key, value in expected.items()):
        raise RuntimeError(f"Unable to set requested cgroup limits: {before}")
    arguments = ["/program", "resource", spec["case"]]
    if spec["case"] == "memory":
        arguments.append("128")
    run = launch(spec["backend"], "full", Path(spec["root"]), spec["image"],
                 Path(spec["policy"]), arguments, resource=True)
    actual = run["child_group"] if spec["backend"] == "podman" else run["values"].get("lab_group")
    after = read_group(path)
    run["cgroup"] = {"before": before, "after": after}
    run["expected_group"] = group
    run["actual_group"] = actual
    run["in_expected_group"] = actual == group
    print(PREFIX + json.dumps(run))


def get_result(backend, case, limits, root, image, policy):
    properties = {
        "Type": "exec", "MemoryMax": f"{limits['memory_mib']}M", "MemorySwapMax": "0",
        "TasksMax": str(limits["pids"]), "CPUQuota": f"{limits['cpu_pct']}%",
        "CPUQuotaPeriodSec": "100ms", "OOMPolicy": "continue",
        "RuntimeMaxSec": "34s", "TimeoutStopSec": "2s", "LimitFSIZE": "8M",
    }
    spec = {"backend": backend, "case": case, "limits": limits, "root": str(root),
            "image": image, "policy": str(policy)}
    unit = "coursework-study-" + secrets.token_hex(6) + ".service"
    run = capture([
        "systemd-run", "--user", "--wait", "--pipe", "--collect", "--quiet", "--unit", unit,
        *[f"--property={key}={value}" for key, value in properties.items()],
        "--", sys.executable, str(Path(__file__).resolve()), json.dumps(spec),
    ], timeout=42)
    for line in run.stdout.splitlines():
        if line.startswith(PREFIX):
            result = json.loads(line.removeprefix(PREFIX))
            result["systemd_stderr"] = run.stderr
            return result
    return {"returncode": run.returncode, "stdout": run.stdout, "stderr": run.stderr,
            "reason": run.stderr.strip() or "Missing resource worker result", "status": "UNAVAILABLE"}


def verdict(row):
    if row.get("status") == "UNAVAILABLE":
        return "UNAVAILABLE"
    if not row["in_expected_group"]:
        row["reason"] = "The payload group could not be confirmed"
        return "UNAVAILABLE"
    values = row["values"]
    if values.get("payload_started") != "1":
        row["reason"] = "The resource probe did not start"
        return "FAIL"
    data = row["cgroup"]
    limits = row["limits"]
    rc = row["returncode"]
    case = row["case"]
    if case == "memory":
        row["event_delta"] = counter_delta(data, "memory.events", "oom_kill")
        peak = data["after"].get("memory.peak")
        if peak:
            row["memory_peak_mib"] = round(int(peak) / (1024 * 1024), 2)
        completed = rc == 0 and values.get("touched_mib") == "128" and row["event_delta"] == 0
        oom = rc != 0 and row["event_delta"] > 0
        row["observation"] = "128 MiB" if completed else "OOM" if oom else "other"
        valid = {64: oom, 128: completed or oom, 256: completed}[limits["memory_mib"]]
    elif case == "tasks":
        row["event_delta"] = counter_delta(data, "pids.events", "max")
        count = int(values.get("children", "-1"))
        row["observation"] = count
        hit = 0 <= count < 24 and values.get("fork_errno") == str(errno.EAGAIN) and row["event_delta"] > 0
        completed = count == 24 and values.get("fork_errno") == "0"
        valid = rc == 0 and (completed if limits["pids"] == 64 else hit)
    else:
        row["event_delta"] = counter_delta(data, "cpu.stat", "nr_throttled")
        elapsed = int(values.get("wall_us", "0"))
        ratio = int(values.get("cpu_us", "0")) / elapsed if elapsed > 0 else 0
        row["observation"] = round(ratio, 4)
        quota = limits["cpu_pct"]
        valid = rc == 0 and 0 < ratio <= (quota / 100) + 0.15
        if quota < 100:
            valid = valid and row["event_delta"] > 0
    return "PASS" if valid else "FAIL"


if __name__ == "__main__":
    try:
        worker(json.loads(sys.argv[1]))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"resource worker: {error}", file=sys.stderr)
        sys.exit(2)
