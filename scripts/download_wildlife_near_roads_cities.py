"""Download the EDK wildlife-near-roads-cities dataset repository."""

from pathlib import Path

from huggingface_hub import snapshot_download

DATASET_ID = "EDK-Earth/wildlife-near-roads-cities"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "datasets" / "wildlife-near-roads-cities"


def main() -> None:
    snapshot_path = snapshot_download(
        repo_id=DATASET_ID,
        repo_type="dataset",
        local_dir=OUTPUT_DIR,
    )
    print(f"Saved {DATASET_ID} to {snapshot_path}")


if __name__ == "__main__":
    main()
