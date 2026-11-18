# Local datasets

This directory contains local training and evaluation datasets used by the
WildGuard model services. Dataset archives and extracted media are intentionally
excluded from version control because they can be large and may have independent
license or redistribution requirements.

## Oregon wildlife

`oregon-wildlife.zip` is a species-organized image-classification dataset. Keep
the original archive here and extract or transform it through a reproducible
preparation script rather than editing the source data in place.

Before using or redistributing the dataset, record its source, license, version,
and any required attribution.

## Wildlife Very Dark

The Hugging Face dataset `yin30lei/wildlife_very_dark` is downloaded and saved
locally under `wildlife_very_dark/`. Reproduce the download from the project
root with:

```bash
uv run python -m scripts.download_wildlife_very_dark
```

Datasets:
https://www.kaggle.com/datasets/virtualdvid/oregon-wildlife
https://universe.roboflow.com/ds/AiVyqzbpJ9?key=8ANUi4P2zh

#Hugging face 1
from datasets import load_dataset
ds = load_dataset("yin30lei/wildlife_very_dark")
