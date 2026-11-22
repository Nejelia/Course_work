"""Plot measured comparisons. Missing or failed observations leave empty positions."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


COLORS = {"host": "#657387", "bubblewrap": "#1f6987", "podman": "#b55a30"}


def measured(folder, series):
    file = folder / f"{series}.json"
    return json.loads(file.read_text(encoding="utf-8")) if file.is_file() else None


def draw(ax, buckets, backends, labels, ylabel, caption):
    width = 0.7 / len(backends)
    for index, name in enumerate(backends):
        locations = []
        medians = []
        for position, key in enumerate(labels):
            values = buckets.get((name, key))
            if values:
                locations.append(position + (index - (len(backends) - 1) / 2) * width)
                medians.append(median(values))
        if medians:
            ax.bar(locations, medians, width, color=COLORS[name], label=name)
    ax.set_xticks(range(len(labels)), list(labels.values()))
    ax.set_ylabel(ylabel)
    ax.set_title(caption)
    ax.grid(axis="y", alpha=0.25)
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend(frameon=False)


def timing(folder, data):
    buckets = defaultdict(list)
    for row in data["rows"]:
        if row["status"] == "PASS" and row["repetition"] >= 1:
            buckets[row["backend"], row["case"]].append(row["elapsed_ms"])
    if not buckets:
        return
    fig, ax = plt.subplots(figsize=(7.5, 4), layout="constrained")
    backends = [name for name in COLORS if any(key[0] == name for key in buckets)]
    draw(ax, buckets, backends, {"hello": "Короткий запуск", "csv": "Обработка CSV"},
         "Медиана, мс", "Время от запуска команды до завершения")
    fig.savefig(folder / "timing.png", dpi=180)
    plt.close(fig)


def resources(folder, data):
    spec = (
        ("memory", "memory_mib", (64, 128, 256), "Пик группы, МиБ", "Лимит памяти, МиБ"),
        ("tasks", "pids", (16, 24, 64), "Дочерние процессы", "Лимит задач"),
        ("cpu", "cpu_pct", (25, 50, 100), "CPU / wall", "Квота CPU, %"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.9), layout="constrained")
    has_measurements = False
    for ax, (case, setting, levels, ylabel, title) in zip(axes, spec):
        buckets = defaultdict(list)
        for row in data["rows"]:
            if row["status"] != "PASS" or row["case"] != case:
                continue
            value = row.get("memory_peak_mib" if case == "memory" else "observation")
            if isinstance(value, (float, int)):
                buckets[row["backend"], row["limits"][setting]].append(value)
        has_measurements = has_measurements or bool(buckets)
        draw(ax, buckets, ("bubblewrap", "podman"), {key: str(key) for key in levels}, ylabel, title)
    if has_measurements:
        fig.savefig(folder / "resources.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    for series, plot in (("timing", timing), ("resources", resources)):
        data = measured(args.folder, series)
        if data:
            plot(args.folder, data)


if __name__ == "__main__":
    main()
