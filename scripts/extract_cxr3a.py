from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Record:
    patient_id: str
    filename: str
    label: str
    source: str


def parse_label_file(path: Path) -> list[Record]:
    records: list[Record] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) != 4:
                raise ValueError(
                    f"Expected 4 columns in {path} at line {line_number}, "
                    f"but found {len(parts)}: {line!r}"
                )

            patient_id, filename, label, source = parts
            records.append(
                Record(
                    patient_id=patient_id,
                    filename=filename,
                    label=label,
                    source=source,
                )
            )
    return records


def materialize_file(source: Path, destination: Path, use_hardlinks: bool) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        return "exists"

    if use_hardlinks:
        try:
            os.link(source, destination)
            return "hardlink"
        except OSError:
            pass

    shutil.copy2(source, destination)
    return "copy"


def process_split(
    records: list[Record],
    source_dir: Path,
    destination_dir: Path,
    use_hardlinks: bool,
) -> dict[str, int]:
    stats = {
        "expected": len(records),
        "found": 0,
        "missing": 0,
        "hardlink": 0,
        "copy": 0,
        "exists": 0,
    }

    missing_files: list[str] = []

    for record in records:
        source_path = source_dir / record.filename
        destination_path = destination_dir / record.filename

        if not source_path.is_file():
            stats["missing"] += 1
            missing_files.append(record.filename)
            continue

        stats["found"] += 1
        mode = materialize_file(source_path, destination_path, use_hardlinks)
        stats[mode] += 1

    if missing_files:
        missing_path = destination_dir.parent / f"missing_{destination_dir.name}.txt"
        missing_path.write_text("\n".join(missing_files) + "\n", encoding="utf-8")

    return stats


def print_class_distribution(records: list[Record], split_name: str) -> None:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.label] = counts.get(record.label, 0) + 1

    print(f"\n{split_name} class distribution:")
    for label, count in sorted(counts.items()):
        print(f"  {label:<12} {count:>7,}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a COVIDx CXR-3A dataset view from an existing COVIDx image collection."
        )
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Existing COVIDx root containing train/ and test/ image directories.",
    )
    parser.add_argument(
        "--labels-root",
        type=Path,
        required=True,
        help="COVID-Net labels directory containing CXR-3A metadata files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Destination directory for the extracted CXR-3A dataset.",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files instead of trying NTFS hardlinks first.",
    )
    args = parser.parse_args()

    train_labels = args.labels_root / "train_COVIDx_CXR-3A.txt"
    test_labels = args.labels_root / "test_COVIDx_CXR-3A.txt"

    train_records = parse_label_file(train_labels)
    test_records = parse_label_file(test_labels)

    print(f"Loaded {len(train_records):,} train records")
    print(f"Loaded {len(test_records):,} test records")

    print_class_distribution(train_records, "Train")
    print_class_distribution(test_records, "Test")

    args.output_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(train_labels, args.output_root / train_labels.name)
    shutil.copy2(test_labels, args.output_root / test_labels.name)

    use_hardlinks = not args.copy

    train_stats = process_split(
        records=train_records,
        source_dir=args.source_root / "train",
        destination_dir=args.output_root / "train",
        use_hardlinks=use_hardlinks,
    )
    test_stats = process_split(
        records=test_records,
        source_dir=args.source_root / "test",
        destination_dir=args.output_root / "test",
        use_hardlinks=use_hardlinks,
    )

    print("\nExtraction summary")
    for split_name, stats in (("Train", train_stats), ("Test", test_stats)):
        print(f"\n{split_name}:")
        for key, value in stats.items():
            print(f"  {key:<10} {value:>7,}")

    total_missing = train_stats["missing"] + test_stats["missing"]

    if total_missing:
        raise SystemExit(
            f"\nCompleted with {total_missing:,} missing image(s). "
            "Inspect missing_train.txt / missing_test.txt."
        )

    print("\nCXR-3A extraction completed successfully with no missing images.")


if __name__ == "__main__":
    main()
