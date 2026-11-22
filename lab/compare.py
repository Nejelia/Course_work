"""Run and record the controlled Bubblewrap and rootless Podman comparison."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
import csv
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import sys
import tempfile
from threading import Thread

import compare_resources as resources
from compare_runtime import (
    LAB, PROBE, PYTHON, capture, launch, podman_image, prepare_root, seccomp_json,
)
from experiment import process_marker, unavailable, version

EXPECTED_CSV = "category,total\nbooks,120\nservices,75\n"
FIXTURE_CSV = "category,amount\nservices,50\nbooks,100\nservices,25\nbooks,20\n"
FILES = ("hello", "files", "pid", "net", "csv")
SHARED = "shared"


def functional_cases(backend, shared_only):
    if backend == "host":
        return [(SHARED, test) for test in FILES]
    if shared_only:
        return [
            *((SHARED, test) for test in FILES),
            ("filter", "net"), (SHARED, "csv_missing"),
        ]
    return [
        *((mode, "net") for mode in (SHARED, "net", "filter", "full")),
        *(("full", test) for test in ("hello", "files", "pid", "csv", "csv_missing")),
    ]


def arguments_for(backend, test, controls):
    host = backend == "host"
    program = str(PROBE) if host else "/program"
    mount = None
    if test == "files":
        path = str(controls["public"]) if host else "/input"
        tmp = str(controls["scratch"]) if host else "/tmp/cw-scratch"
        args = [program, test, str(controls["hidden"]), path, tmp]
        if not host:
            mount = (controls["public"], "/input")
    elif test in ("csv", "csv_missing"):
        source = str(controls["data"]) if host else "/data/input.csv"
        if test == "csv" and not host:
            mount = (controls["data"].parent, "/data")
        script = str(LAB / "csv_workload.py") if host else "/csv_workload.py"
        output = str(controls["result"]) if host else "/tmp/report.csv"
        args = [PYTHON, "-I", "-S", "-B", script, source, output]
    elif test in ("pid", "net"):
        args = [program, test, str(controls["marker"] if test == "pid" else controls["port"])]
    else:
        args = [program, test]
    return args, mount


def functional_valid(row, controls):
    backend, mode, test = row["backend"], row["mode"], row["case"]
    host = backend == "host"
    values = row["values"]
    if test == "csv_missing":
        return row["returncode"] != 0 and "csv_error=FileNotFoundError" in row["stderr"]
    if row["returncode"]:
        return False
    if test == "hello":
        return values.get("hello") == "1"
    if test == "files":
        expected = {
            "hidden_errno": "0" if host else str(errno.ENOENT), "input_read": "1",
            "input_write_errno": "0" if host else str(errno.EROFS), "scratch_errno": "0",
        }
        return all(values.get(key) == expected[key] for key in expected)
    if test == "pid":
        same_pid = values.get("ns_pid") == controls["host_pid_ns"]
        return (values.get("sentinel_visible") == ("1" if host else "0")
                and values.get("ns_pid") is not None and same_pid == host
                and (host or values.get("CapEff") == "0000000000000000")
                and (host or values.get("NoNewPrivs") == "1"))
    if test == "net":
        same_net = values.get("net_ns") == controls["host_net_ns"]
        if values.get("net_ns") is None or same_net != (mode in ("shared", "filter")):
            return False
        if "socket_setup_errno" in values:
            return False
        if mode in ("filter", "full"):
            return (values.get("socket_errno") == str(errno.EPERM)
                    and values.get("ipv6_socket_errno") == str(errno.EPERM)
                    and "connect_errno" not in values)
        if mode == "net":
            refusals = {str(errno.ECONNREFUSED), str(errno.ENETUNREACH), str(errno.EHOSTUNREACH)}
            return values.get("socket_errno") == "0" and values.get("connect_errno") in refusals
        return values.get("socket_errno") == "0" and values.get("connect_errno") == "0"
    if test == "csv":
        return row["stdout"] == EXPECTED_CSV
    raise ValueError(test)


def add_measurement(rows, backend, mode, case, repetition, root, image, policy, controls, limits=None):
    row = {"backend": backend, "mode": mode, "case": case, "repetition": repetition}
    if limits:
        row["limits"] = limits
    try:
        if limits:
            row.update(resources.get_result(backend, case, limits, root, image, policy))
            row["status"] = resources.verdict(row)
        else:
            args, mounts = arguments_for(backend, case, controls)
            row.update(launch(backend, mode, root, image, policy, args, mounts))
            if not row["stdout"] and unavailable(row):
                row["status"] = "UNAVAILABLE"
            else:
                row["status"] = "PASS" if functional_valid(row, controls) else "FAIL"
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        row.update(status="UNAVAILABLE", reason=str(error))
    rows.append(row)


def make_controls(fixture, marker, port):
    fixture.mkdir()
    paths = {key: fixture / name for key, name in (
        ("hidden", "hidden.txt"), ("public", "public.txt"), ("data", "csv_input/input.csv"),
        ("scratch", "scratch"), ("result", "report.csv"),
    )}
    paths["hidden"].write_text("SYNTHETIC PRIVATE\n")
    paths["public"].write_text("PUBLIC\n")
    paths["data"].parent.mkdir()
    paths["data"].write_text(FIXTURE_CSV)
    return dict(paths, marker=marker, port=port, host_pid_ns=os.readlink("/proc/self/ns/pid"),
                host_net_ns=os.readlink("/proc/self/ns/net"))


@contextmanager
def local_server():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(32)
        listener.settimeout(0.2)

        def accept_and_close():
            while listener.fileno() != -1:
                try:
                    client, _ = listener.accept()
                    client.close()
                except TimeoutError:
                    continue
                except OSError:
                    break

        worker = Thread(target=accept_and_close, daemon=True)
        worker.start()
        try:
            yield listener.getsockname()[1]
        finally:
            listener.close()
            worker.join(timeout=1)


def experiment(args, working, stack):
    selected = {"both": ["bubblewrap", "podman"], "host": []}.get(args.backend, [args.backend])
    root = prepare_root(working) if selected else None
    policy = seccomp_json(working / "seccomp.json")
    image = stack.enter_context(podman_image(root, working)) if "podman" in selected else None
    rows = []
    marker = "cw" + secrets.token_hex(5)
    port = stack.enter_context(local_server())
    stack.enter_context(process_marker(marker))
    controls = make_controls(working / "fixtures", marker, port)

    if args.series == "check":
        for backend in selected:
            add_measurement(rows, backend, "full", "hello", 1, root, image, policy, controls)
            add_measurement(rows, backend, "full", "csv", 1, root, image, policy, controls)
            limits = {"memory_mib": 256, "pids": 64, "cpu_pct": 100}
            add_measurement(rows, backend, "full", "tasks", 1, root, image, policy, controls, limits)
    elif args.series == "resources":
        for repetition in range(1, args.repetitions + 1):
            for case, limits in resources.scenarios():
                for backend in selected:
                    add_measurement(rows, backend, "full", case, repetition,
                                    root, image, policy, controls, limits)
            print(f"Resource repetition {repetition}/{args.repetitions}", flush=True)
    elif args.series == "functional":
        for repetition in range(1, args.repetitions + 1):
            for backend in ("host", *selected):
                for mode, case in functional_cases(backend, args.shared_only):
                    add_measurement(rows, backend, mode, case, repetition, root, image, policy, controls)
    else:
        order = ["host", *selected]
        for repetition in range(-1, args.repetitions + 1):
            steps = order[repetition % len(order):] + order[:repetition % len(order)]
            for case in ("hello", "csv"):
                for backend in steps:
                    add_measurement(rows, backend, SHARED if args.shared_only else "full",
                                    case, repetition, root, image, policy, controls)
    return rows


def save(output, args, rows):
    env = {
        "os": platform.freedesktop_os_release().get("PRETTY_NAME"),
        "kernel": platform.release(), "arch": platform.machine(), "cpus": os.cpu_count(),
        "bubblewrap": version("bwrap", "--version"), "podman": version("podman", "--version"),
        "systemd": version("systemd-run", "--version"), "python": version(PYTHON, "--version"),
        "series": args.series, "backend": args.backend, "repetitions": args.repetitions,
        "shared_only": args.shared_only, "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output / f"{args.series}.json").write_text(
        json.dumps({"environment": env, "rows": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    columns = [
        "backend", "mode", "case", "repetition", "status", "returncode", "elapsed_ms", "limits",
        "observation", "event_delta", "memory_peak_mib", "in_expected_group", "reason", "values",
    ]
    with (output / f"{args.series}.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for original in rows:
            row = dict(original)
            for name in ("limits", "values"):
                if name in row:
                    row[name] = json.dumps(row[name], ensure_ascii=False)
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", required=True, choices=("check", "functional", "resources", "timing"))
    parser.add_argument("--backend", choices=("both", "bubblewrap", "podman", "host"), default="both")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shared-only", action="store_true", help="diagnostic run without network namespace")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Use the ordinary Ubuntu user")
    if not 1 <= args.repetitions <= 100:
        parser.error("Use 1 to 100 repetitions")
    if args.series in ("resources", "check") and (args.backend == "host" or args.shared_only):
        parser.error("Use a sandbox backend and the full mode for resource checks")
    if not PROBE.is_file():
        parser.error("Run make first")
    args.output.mkdir(parents=True, exist_ok=True)
    if any((args.output / f"{args.series}.{suffix}").exists() for suffix in ("csv", "json")):
        parser.error("This series already has records in the directory. Use a fresh directory.")
    with tempfile.TemporaryDirectory(prefix="coursework-study-") as tmp, ExitStack() as stack:
        working = Path(tmp)
        rows = experiment(args, working, stack)
        save(args.output, args, rows)
    for backend in sorted({row["backend"] for row in rows}):
        subset = [row for row in rows if row["backend"] == backend]
        print(f"{backend}: {dict(Counter(row['status'] for row in subset))}")
        for row in subset:
            if row["status"] != "PASS":
                first_line = (row.get("reason") or row.get("stderr") or "").splitlines()
                print(f"  {row['mode']}/{row['case']} #{row['repetition']}: "
                      f"{row['status']} {first_line[0] if first_line else ''}")
                break
    print(f"Results: {args.output.resolve()}")
    return int(any(row["status"] != "PASS" for row in rows))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"compare: {error}", file=sys.stderr)
        sys.exit(2)
