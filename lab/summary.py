#!/usr/bin/env python3
"""Read an experiment log and print a Markdown table of observed outcomes."""

import argparse
from collections import Counter
import errno
import json
from pathlib import Path
from statistics import median

from experiment import counter_delta


def value(row, key):
    return row.get("values", {}).get(key, "—")


def error_name(result):
    if result == "0":
        return "0"
    return errno.errorcode.get(int(result), result) if result.isdigit() else result


def show_delta(row, file, counter):
    if row.get("cgroup") is None:
        return "—"
    return str(counter_delta(row["cgroup"], file, counter))


def markdown(data):
    env = data["environment"]
    rows = data["rows"]
    output = [
        "# Результаты эксперимента",
        "",
        f"- Окружение: {env['os']}, ядро {env['kernel']}, {env['bubblewrap']}.",
        f"- Сеть: `{env['net_backend']}`. Число повторов: {env['repetitions']}.",
        "",
        "| Профиль | PASS | FAIL | UNAVAILABLE |",
        "|---|---:|---:|---:|",
    ]
    for profile in sorted({row["profile"] for row in rows}):
        counts = Counter(row["status"] for row in rows if row["profile"] == profile)
        output.append(f"| P{profile} | {counts['PASS']} | {counts['FAIL']} | {counts['UNAVAILABLE']} |")

    output.extend([
        "",
        "## Файлы процессы и сеть",
        "",
        "Наблюдения первого повтора. Прочерк обозначает отсутствие значения в журнале.",
        "",
        "| Профиль | Тест | Статус | Наблюдение |",
        "|---|---|---|---|",
    ])
    for row in rows:
        case = row["test"]
        if row["repetition"] != 1 or case not in ("files", "pid", "net"):
            continue
        keys = {
            "files": ("hidden_errno", "input_read", "input_write_errno", "scratch_errno"),
            "pid": ("sentinel_visible", "ns_pid", "ns_net", "Seccomp_filters"),
            "net": ("socket_errno", "socket_setup_errno", "connect_errno",
                    "ipv6_socket_errno", "unix_socket_errno"),
        }[case]
        observed = ", ".join(
            f"`{key}={error_name(value(row, key)) if key.endswith('_errno') else value(row, key)}`"
            for key in keys if value(row, key) != "—"
        )
        output.append(f"| P{row['profile']} | {case} | {row['status']} | {observed or '—'} |")

    output.extend([
        "",
        "## Ресурсы",
        "",
        "Δ обозначает разность между показаниями после и до теста. "
        "Прочерк означает отсутствие измерения, в том числе в профиле без квот.",
        "",
        "| Профиль | Повтор | Тест | Статус | Наблюдение | Δ счётчика |",
        "|---|---:|---|---|---|---|",
    ])
    for row in rows:
        case = row["test"]
        if case == "tasks":
            observed = f"children={value(row, 'children')}, fork={error_name(value(row, 'fork_errno'))}"
            delta = show_delta(row, "pids.events", "max")
        elif case in ("memory16", "memory128"):
            observed = f"МиБ={value(row, 'touched_mib')}, код={row.get('returncode', '—')}"
            delta = show_delta(row, "memory.events", "oom_kill")
        elif case == "cpu":
            observed = f"CPU / wall = {row.get('cpu_ratio', '—')}"
            delta = show_delta(row, "cpu.stat", "nr_throttled")
        else:
            continue
        output.append(
            f"| P{row['profile']} | {row['repetition']} | {case} | {row['status']} | {observed} | {delta} |"
        )

    output.extend(["", "## Доля процессорного времени", ""])
    for profile in (3, 4, 5):
        ratios = [
            row["cpu_ratio"] for row in rows
            if row["profile"] == profile and row["status"] == "PASS" and "cpu_ratio" in row
        ]
        if ratios:
            output.append(
                f"- P{profile}: n = {len(ratios)}, медиана {median(ratios):.3f}, "
                f"минимум {min(ratios):.3f}, максимум {max(ratios):.3f}."
            )
    issues = sorted({
        (row["profile"], row["test"], row.get("reason") or row.get("stderr", "").strip())
        for row in rows if row["status"] != "PASS"
    })
    if issues:
        output.extend(["", "## Проверки требующие разбора", ""])
        for profile, case, reason in issues:
            detail = reason.splitlines()[0] if reason else "подробности в results.json"
            output.append(f"- P{profile} / {case} — {detail}")
    return "\n".join(output) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="path to results.json")
    args = parser.parse_args()
    data = json.loads(args.results.read_text(encoding="utf-8"))
    print(markdown(data), end="")


if __name__ == "__main__":
    main()
