from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def parse_cxr3a_labels(labels_file: Path, source_name: str) -> list[str]:
    filenames: list[str] = []

    with labels_file.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) != 4:
                raise ValueError(
                    f"Expected 4 columns in {labels_file} at line {line_number}, "
                    f"found {len(parts)}: {line!r}"
                )

            _, filename, _, source = parts
            if source.lower() == source_name.lower():
                filenames.append(filename)

    return filenames


def materialize(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        return "exists"

    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover missing COVIDx CXR-3A images from the Cohen source repository."
    )
    parser.add_argument(
        "--labels-file",
        type=Path,
        required=True,
        help="Path to train_COVIDx_CXR-3A.txt.",
    )
    parser.add_argument(
        "--missing-file",
        type=Path,
        required=True,
        help="Path to missing_train.txt produced by extract_cxr3a.py.",
    )
    parser.add_argument(
        "--cohen-root",
        type=Path,
        required=True,
        help="Root of the cloned ieee8023/covid-chestxray-dataset repository.",
    )
    parser.add_argument(
        "--output-train",
        type=Path,
        required=True,
        help="Destination CXR-3A train directory.",
    )
    args = parser.parse_args()

    source_images = args.cohen_root / "images"
    if not source_images.is_dir():
        raise FileNotFoundError(f"Cohen images directory not found: {source_images}")

    cohen_required = set(parse_cxr3a_labels(args.labels_file, "cohen"))
    missing_all = {
        line.strip()
        for line in args.missing_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    target_files = sorted(cohen_required & missing_all)

    stats = {"required_missing": len(target_files), "found": 0, "missing": 0,
             "hardlink": 0, "copy": 0, "exists": 0}
    still_missing: list[str] = []

    for filename in target_files:
        src = source_images / filename
        dst = args.output_train / filename

        if not src.is_file():
            stats["missing"] += 1
            still_missing.append(filename)
            continue

        stats["found"] += 1
        mode = materialize(src, dst)
        stats[mode] += 1

    print("Cohen recovery summary")
    for key, value in stats.items():
        print(f"  {key:<16} {value:>6,}")

    if still_missing:
        report = args.output_train.parent / "missing_cohen_after_recovery.txt"
        report.write_text("\n".join(still_missing) + "\n", encoding="utf-8")
        print(f"\nStill-missing Cohen filenames written to: {report}")
    else:
        print("\nAll missing Cohen images available in the cloned source were recovered.")


if __name__ == "__main__":
    main()
