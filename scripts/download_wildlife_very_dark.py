"""Download the wildlife_very_dark dataset for local WildGuard development."""

from pathlib import Path

from datasets import load_dataset

DATASET_ID = "yin30lei/wildlife_very_dark"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "datasets" / "wildlife_very_dark"


def main() -> None:
    dataset = load_dataset(DATASET_ID)
    dataset.save_to_disk(OUTPUT_DIR)

    split_sizes = {name: len(split) for name, split in dataset.items()}
    print(f"Saved {DATASET_ID} to {OUTPUT_DIR}")
    print(f"Splits: {split_sizes}")


if __name__ == "__main__":
    main()
