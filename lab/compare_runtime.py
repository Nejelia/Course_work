"""Build a common local filesystem and launch the two controlled sandboxes."""

from contextlib import contextmanager, ExitStack
import errno
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tarfile
import time

import sandbox

LAB = Path(__file__).resolve().parent
PROBE = LAB / "probe"
PYTHON = "/usr/bin/python3"
MODES = {
    "shared": (False, False),
    "net": (True, False),
    "filter": (False, True),
    "full": (True, True),
}
COMMAND_ENV = dict(os.environ, GOMAXPROCS="2")


def capture(command, *, timeout=25):
    return subprocess.run(
        command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        errors="replace", timeout=timeout, env=COMMAND_ENV,
    )


def checked(command, *, timeout=25):
    run = capture(command, timeout=timeout)
    if run.returncode:
        raise RuntimeError(f"{command[0]} exit {run.returncode}: {run.stderr.strip()}")
    return run.stdout


def prepare_root(working):
    root = working / "rootfs"
    for name in ("usr/bin", "dev", "proc", "tmp", "run", "etc", "sys", "data"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "input").touch()
    shutil.copy2(PROBE, root / "program")
    shutil.copy2(LAB / "csv_workload.py", root / "csv_workload.py")
    shutil.copy2(PYTHON, root / PYTHON.lstrip("/"))
    stdlib, csv_ext = checked([
        PYTHON, "-I", "-S", "-c",
        "import _csv, sysconfig; print(sysconfig.get_path('stdlib')); print(getattr(_csv, '__file__', 'built-in'))",
    ]).splitlines()
    shutil.copytree(stdlib, root / stdlib.lstrip("/"), symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "test", "tests", "config-*"))
    binaries = [PYTHON]
    if csv_ext != 'built-in':
        binaries.append(csv_ext)
    for binary in binaries:
        dependencies = checked(["ldd", binary])
        if "not found" in dependencies:
            raise RuntimeError(f"Missing local dependencies for {binary}")
        for name in re.findall(r"(?:=>\s+|^\s*)(/\S+)\s+\(0x", dependencies, flags=re.M):
            target = root / name.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(name, target)
    return root


def seccomp_json(path):
    rules = [
        {"names": list(sandbox.DENIED_CALLS), "action": "SCMP_ACT_ERRNO",
         "errnoRet": errno.EPERM, "args": []},
        {"names": ["socket"], "action": "SCMP_ACT_ERRNO", "errnoRet": errno.EPERM,
         "args": [{"index": 0, "value": 1, "valueTwo": 0, "op": "SCMP_CMP_NE"}]},
    ]
    path.write_text(json.dumps({
        "defaultAction": "SCMP_ACT_ALLOW", "architectures": ["SCMP_ARCH_X86_64"],
        "syscalls": rules,
    }, indent=2), encoding="utf-8")
    return path


@contextmanager
def podman_image(root, working):
    if not shutil.which("podman"):
        raise RuntimeError("Install the Ubuntu podman and uidmap packages")
    with tarfile.open(working / "rootfs.tar", "w") as archive:
        for item in sorted(root.iterdir()):
            archive.add(item, arcname=item.name, filter=root_owned)
    name = f"localhost/coursework-sandbox:run-{secrets.token_hex(6)}"
    try:
        checked(["podman", "import", str(working / "rootfs.tar"), name], timeout=150)
        yield name
    finally:
        capture(["podman", "rmi", name], timeout=20)


def root_owned(entry):
    entry.uid = entry.gid = 0
    entry.uname = entry.gname = "root"
    return entry


def process_group(pid):
    lines = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
    return next((line[3:] for line in lines if line.startswith("0::")), "")


def group_from_pidfile(proc, pidfile, start):
    while proc.poll() is None and time.monotonic() - start < 20:
        try:
            pid = int(pidfile.read_text().strip())
            return process_group(pid)
        except (ValueError, FileNotFoundError):
            time.sleep(0.02)
    return ""


def invoke(command, descriptors=(), pidfile=None):
    start = time.monotonic()
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, errors="replace",
                          env=COMMAND_ENV, pass_fds=descriptors) as proc:
        group = ""
        try:
            if pidfile:
                group = group_from_pidfile(proc, pidfile, start)
            out, err = proc.communicate(timeout=max(1, 24 - (time.monotonic() - start)))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
    return {
        "returncode": proc.returncode if proc.returncode >= 0 else 128 - proc.returncode,
        "stdout": out, "stderr": err, "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
        "child_group": group,
        "values": dict(line.split("=", 1) for line in out.splitlines() if "=" in line),
    }


def launch(backend, mode, root, image, policy, arguments, mount=None, resource=False):
    if backend == "host":
        return invoke(arguments)
    net, filtered = MODES[mode]
    with ExitStack() as stack:
        if backend == "bubblewrap":
            cmd = [
                sandbox.require_bwrap(), "--unshare-user", "--disable-userns", "--unshare-pid",
                "--unshare-ipc", "--unshare-uts", "--cap-drop", "ALL", "--new-session",
                "--die-with-parent", "--clearenv", "--setenv", "LANG", "C.UTF-8",
                "--ro-bind", str(root), "/", "--proc", "/proc", "--remount-ro", "/proc",
                "--size", str(sandbox.MAX_TMP), "--tmpfs", "/tmp", "--chdir", "/",
            ]
            if mount:
                source, target = mount
                cmd += ["--ro-bind", str(source), target]
            if net:
                cmd.append("--unshare-net")
            descriptors = ()
            if filtered:
                fd = stack.enter_context(sandbox.seccomp_fd())
                descriptors = (fd,)
                cmd += ["--seccomp", str(fd)]
            return invoke([*cmd, "--", *arguments], descriptors)

        name = f"cw-probe-{secrets.token_hex(6)}"
        cmd = [
            "podman", "run", "--rm", "--name", name, "--pull=never",
            "--read-only", "--read-only-tmpfs=false", "--tmpfs", "/tmp:rw,nodev,nosuid,size=16m",
            "--pid=private", "--ipc=private", "--uts=private", "--workdir=/",
            "--cap-drop=all", "--security-opt=no-new-privileges", "--http-proxy=false",
            "--env", "LANG=C.UTF-8", "--network", "none" if net else "host",
            "--security-opt", f"seccomp={policy}" if filtered else "seccomp=unconfined",
        ]
        if mount:
            source, target = mount
            cmd += ["--volume", f"{source}:{target}:ro"]
        pidfile = None
        if resource:
            pidfile = policy.parent / f"{name}.pid"
            cmd += ["--cgroups=disabled", "--pidfile", str(pidfile)]
        try:
            return invoke([*cmd, image, *arguments], pidfile=pidfile)
        except (OSError, subprocess.TimeoutExpired):
            capture(["podman", "rm", "-f", "--ignore", name])
            raise
        finally:
            if pidfile:
                pidfile.unlink(missing_ok=True)
