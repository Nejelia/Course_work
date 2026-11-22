#!/usr/bin/env python3
"""Bubblewrap sandbox and repeatable measurements for the Linux coursework."""

import argparse
import contextlib
import ctypes
import errno
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import socket
import stat
import subprocess
import sys

MEMORY = 64 * 1024 * 1024
TASKS = 16
MAX_TMP = 16 * 1024 * 1024
CGROUP_FILES = ("memory.max", "memory.swap.max", "memory.events",
                "pids.max", "pids.events", "cpu.max", "cpu.stat")
CGROUP_PREFIX = "LAB_CGROUP "
NAMESPACES = ("mnt", "pid", "user", "net", "ipc", "uts")
SERVICE_PROPERTIES = (
    "MemoryMax=64M", "MemorySwapMax=0", "TasksMax=16",
    "CPUQuota=50%", "CPUQuotaPeriodSec=100ms",
    "MemoryAccounting=yes", "CPUAccounting=yes", "TasksAccounting=yes",
    "OOMPolicy=continue", "RuntimeMaxSec=8s", "TimeoutStopSec=1s",
    "LimitFSIZE=1M",
)
DENIED_CALLS = (
    "mount", "umount2", "pivot_root", "setns", "unshare", "open_by_handle_at",
    "ptrace", "process_vm_readv", "process_vm_writev", "bpf", "perf_event_open",
    "userfaultfd", "add_key", "request_key", "keyctl",
    "io_uring_setup", "io_uring_enter", "io_uring_register",
)


class ArgumentComparison(ctypes.Structure):
    _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]


@contextlib.contextmanager
def seccomp_fd():
    allow = 0x7FFF0000
    deny = 0x00050000 | errno.EPERM
    compare_ne = 1
    library = ctypes.CDLL("libseccomp.so.2")
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_release.restype = None
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
        ctypes.c_uint, ctypes.POINTER(ArgumentComparison),
    ]
    library.seccomp_rule_add_array.restype = ctypes.c_int
    library.seccomp_export_bpf.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.seccomp_export_bpf.restype = ctypes.c_int

    context = library.seccomp_init(allow)
    if not context:
        raise RuntimeError("Cannot initialize libseccomp")
    with contextlib.ExitStack() as cleanup:
        cleanup.callback(library.seccomp_release, context)
        fd = os.memfd_create("coursework-seccomp", os.MFD_CLOEXEC)
        cleanup.callback(os.close, fd)
        for name in (*DENIED_CALLS, "socket"):
            number = library.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number < 0:
                raise RuntimeError(f"Unknown syscall in policy: {name}")
            comparison = ArgumentComparison(0, compare_ne, socket.AF_UNIX, 0)
            rule = ctypes.byref(comparison) if name == "socket" else None
            status = library.seccomp_rule_add_array(context, deny, number, int(rule is not None), rule)
            if status < 0:
                raise OSError(-status, f"Cannot add seccomp rule for {name}")
        status = library.seccomp_export_bpf(context, fd)
        if status < 0:
            raise OSError(-status, "Cannot export seccomp BPF")
        os.lseek(fd, 0, os.SEEK_SET)
        yield fd


def require_bwrap():
    if os.geteuid() == 0:
        raise RuntimeError("Run from an ordinary user session")
    if platform.machine() != "x86_64":
        raise RuntimeError("The lab is configured for native x86-64")
    binary = shutil.which("bwrap")
    if not binary:
        raise RuntimeError("Install Bubblewrap")
    if Path(binary).stat().st_mode & stat.S_ISUID:
        raise RuntimeError("The lab requires Bubblewrap without setuid")
    return binary


def execute(profile, program, arguments, input_file):
    with contextlib.ExitStack() as cleanup:
        command = [str(program), *arguments]
        descriptors = ()
        if profile:
            command = [
                require_bwrap(), "--unshare-user", "--disable-userns",
                "--unshare-pid", "--unshare-ipc", "--unshare-uts",
                "--cap-drop", "ALL", "--die-with-parent", "--new-session",
                "--clearenv", "--hostname", "sandbox-lab",
                "--ro-bind", str(program), "/program",
                "--size", str(MAX_TMP), "--tmpfs", "/tmp",
                "--proc", "/proc", "--remount-ro", "/proc",
                "--remount-ro", "/", "--chdir", "/tmp",
            ]
            if input_file is not None:
                # Bind the fixture before the root is remounted read-only.
                command[1:1] = ["--ro-bind", str(input_file), "/input"]
            if profile in (2, 4):
                command.append("--unshare-net")
            if profile in (3, 4):
                fd = cleanup.enter_context(seccomp_fd())
                command.extend(("--seccomp", str(fd)))
                descriptors = (fd,)
            command.extend(("--", "/program", *arguments))
        finished = subprocess.run(command, stdin=subprocess.DEVNULL, close_fds=True,
                                  pass_fds=descriptors, timeout=5)
        return finished.returncode if finished.returncode >= 0 else 128 - finished.returncode


def cgroup_snapshot():
    hierarchy = Path("/proc/self/cgroup").read_text().splitlines()
    group = next((line.removeprefix("0::") for line in hierarchy if line.startswith("0::")), "")
    if not group.startswith("/") or group == "/":
        raise RuntimeError("A separate systemd cgroup v2 is required")
    base = Path("/sys/fs/cgroup") / group.lstrip("/")
    return {name: (base / name).read_text().strip() for name in CGROUP_FILES}


def confirm_limits(snapshot):
    if (snapshot["memory.max"] != str(MEMORY) or snapshot["memory.swap.max"] != "0"
            or snapshot["pids.max"] != str(TASKS)
            or snapshot["cpu.max"] != "50000 100000"):
        raise RuntimeError(f"Kernel cgroup limits differ from the lab settings: {snapshot}")


def resource_worker(program, arguments, input_file):
    before = cgroup_snapshot()
    confirm_limits(before)
    try:
        return execute(4, program, arguments, input_file)
    finally:
        after = cgroup_snapshot()
        print(CGROUP_PREFIX + json.dumps({"before": before, "after": after}), file=sys.stderr)


def run_command(profile, program, arguments, input_file):
    modes = ["_worker", "--program", str(program)]
    if input_file is not None:
        modes.extend(("--input", str(input_file)))
    child = [sys.executable, str(Path(__file__).resolve()), *modes, str(profile), "--", *arguments]
    if profile < 5:
        return child
    unit = f"sandbox-lab-{secrets.token_hex(6)}.service"
    settings = [f"--property={entry}" for entry in SERVICE_PROPERTIES]
    return ["systemd-run", "--user", "--wait", "--pipe", "--collect", "--quiet",
            f"--unit={unit}", *settings, "--", *child]


def validate_program(value):
    path = Path(value).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f"A regular executable file is required: {path}")
    return path


def argument_values(values):
    return values[1:] if values and values[0] == "--" else values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action", required=True)
    public = subcommands.add_parser("run", help="run a static binary with all layers")
    public.add_argument("--input", type=Path)
    public.add_argument("program")
    public.add_argument("arguments", nargs=argparse.REMAINDER)
    worker = subcommands.add_parser("_worker")
    worker.add_argument("profile", type=int, choices=range(6))
    worker.add_argument("--input", type=Path)
    worker.add_argument("--program", required=True)
    worker.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    program = validate_program(args.program)
    input_file = args.input.resolve(strict=True) if args.input else None
    if input_file is not None and not input_file.is_file():
        raise RuntimeError("The input mount requires one regular file")
    arguments = argument_values(args.arguments)
    if args.action == "run":
        require_bwrap()
        command = run_command(5, program, arguments, input_file)
        return subprocess.run(command, stdin=subprocess.DEVNULL, timeout=15).returncode
    if args.profile == 5:
        return resource_worker(program, arguments, input_file)
    return execute(args.profile, program, arguments, input_file)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"sandbox: {error}", file=sys.stderr)
        sys.exit(125)
