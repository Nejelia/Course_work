"""Aggregate a synthetic CSV with fixed columns and integer amounts."""

import csv
import sys


def main():
    try:
        with open(sys.argv[1], encoding="utf-8", newline="") as source:
            rows = csv.DictReader(source)
            if rows.fieldnames != ["category", "amount"]:
                raise ValueError("expected columns category,amount")
            totals = {}
            for row in rows:
                name = row["category"]
                totals[name] = totals.get(name, 0) + int(row["amount"])
        with open(sys.argv[2], "w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target, lineterminator="\n")
            writer.writerow(("category", "total"))
            writer.writerows(sorted(totals.items()))
        with open(sys.argv[2], encoding="utf-8") as report:
            print(report.read(), end="")
        return 0
    except (OSError, ValueError) as error:
        print(f"csv_error={error.__class__.__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
