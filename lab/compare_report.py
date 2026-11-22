"""Convert raw comparison records to Russian Markdown tables."""

import argparse
from collections import Counter, defaultdict
import errno
import json
from pathlib import Path
from statistics import median, quantiles

SERIES = ("check", "functional", "resources", "timing")


def shown(value):
    return "—" if value is None else str(value)


def error_name(result):
    if result and result.isdigit() and result != "0":
        return errno.errorcode.get(int(result), result)
    return shown(result)


def table(head, lines):
    output = ["| " + " | ".join(head) + " |", "| " + " | ".join(["---"] * len(head)) + " |"]
    output.extend("| " + " | ".join(map(shown, line)) + " |" for line in lines)
    return output


def first_observations(data):
    sections = {
        "net": ("net_ns", "socket_errno", "connect_errno", "ipv6_socket_errno"),
        "files": ("hidden_errno", "input_read", "input_write_errno", "scratch_errno"),
        "pid": ("sentinel_visible", "ns_pid", "NoNewPrivs"),
    }
    for row in data["rows"]:
        if row["repetition"] != 1:
            continue
        values, case = row.get("values", {}), row["case"]
        keys = sections.get(case, ())
        detail = [
            f"`{key}={error_name(values.get(key)) if key.endswith('_errno') else shown(values.get(key))}`"
            for key in keys
        ]
        if row["status"] == "PASS" and case == "csv":
            detail = ["`books=120` и `services=75`"]
        if row["status"] == "PASS" and case == "csv_missing":
            detail = ["`FileNotFoundError`"]
        yield row["backend"], row["mode"], case, row["status"], ", ".join(detail)


def resource_observations(data):
    for row in data["rows"]:
        limits = row["limits"]
        scope = f"{limits['memory_mib']} МиБ / {limits['pids']} задач / {limits['cpu_pct']}%"
        yield (row["backend"], row["repetition"], row["case"], scope, row["status"],
               row.get("observation"), row.get("event_delta"), row.get("memory_peak_mib"))


def timing_observations(data):
    buckets = defaultdict(list)
    counted = Counter()
    for row in data["rows"]:
        if row["repetition"] < 1:
            continue
        key = row["backend"], row["case"]
        counted[key] += 1
        if row["status"] == "PASS":
            buckets[key].append(row["elapsed_ms"])
    for (backend, case), count in sorted(counted.items()):
        times = buckets[(backend, case)]
        q1, _, q3 = quantiles(times, n=4, method="inclusive") if len(times) > 1 else (None,) * 3
        spread = f"{q1:.2f}–{q3:.2f}" if q1 is not None else "—"
        yield backend, case, f"{len(times)}/{count}", round(median(times), 2) if times else None, spread


def generate(folder, chosen=None, case=None):
    out = ["# Результаты сравнительного исследования", ""]
    found = False
    for series in ((chosen,) if chosen else SERIES):
        path = folder / f"{series}.json"
        if not path.is_file():
            continue
        found = True
        data = json.loads(path.read_text(encoding="utf-8"))
        if case:
            data["rows"] = [row for row in data["rows"] if row["case"] == case]
        env = data["environment"]
        out.extend([
            f"## Серия {series}", "",
            f"{env['os']}, ядро {env['kernel']}, {env['arch']}, CPU {env['cpus']}. "
            f"{shown(env['bubblewrap'])}, {shown(env['podman'])}.",
            "",
        ])
        if env["shared_only"]:
            out.extend(["Диагностический запуск с общей сетью.", ""])
        counts = Counter((row["backend"], row["status"]) for row in data["rows"])
        for backend in sorted({key[0] for key in counts}):
            out.append(f"- {backend}: PASS {counts[(backend, 'PASS')]}, "
                       f"FAIL {counts[(backend, 'FAIL')]}, UNAVAILABLE {counts[(backend, 'UNAVAILABLE')]}.")
        out.append("")
        if series == "functional":
            out.extend(table(("Среда", "Режим", "Тест", "Статус", "Первый повтор"),
                             first_observations(data)))
        if series == "resources":
            out.extend(["Δ счётчика относится к oom_kill, pids.events:max или nr_throttled "
                        "соответственно. Пик относится ко всей группе.", ""])
            out.extend(table(("Среда", "Повтор", "Тест", "Лимиты", "Статус", "Исход",
                              "Δ счётчика", "Пик МиБ"), resource_observations(data)))
        if series == "timing":
            out.extend(["Два прогревочных запуска пропущены. Таблица учитывает успешные измерения.", ""])
            out.extend(table(("Среда", "Нагрузка", "Успехов / запусков", "Медиана мс", "Q1–Q3 мс"),
                             timing_observations(data)))
        issues = {}
        for row in data["rows"]:
            if row["status"] != "PASS":
                key = row["backend"], row["mode"], row["case"], json.dumps(row.get("limits"))
                issues.setdefault(key, row)
        if issues:
            out.extend(["", "Первые отклонения по сценариям.", ""])
            for row in issues.values():
                details = (row.get("reason") or row.get("stderr") or "см. исходную запись").splitlines()
                out.append(f"- {row['backend']}/{row['mode']}/{row['case']}, "
                           f"повтор {row['repetition']}, {row['status']} — {details[0]}")
        out.append("")
    if not found:
        raise SystemExit("No comparison JSON files found")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--series", choices=SERIES)
    parser.add_argument("--case", help="filter rows for a terminal screenshot")
    args = parser.parse_args()
    print(generate(args.folder, args.series, args.case))


if __name__ == "__main__":
    main()
