# AnimalCLAP runtime

WildGuard uses [AnimalCLAP](https://huggingface.co/risashinoda/animalclap)
for local wildlife-sound experiments. The model is ungated, MIT-licensed, and
does not require a generative LLM.

AnimalCLAP ranks candidate species for 10-second, 48 kHz audio clips. It does
not provide a calibrated animal/non-animal threshold, so WildGuard must measure
that threshold using both wildlife clips and negative controls before enabling
alerts.

## Setup

```bash
./scripts/setup_animalclap_audio.sh
```

The setup script:

1. installs the required audio dependencies in an isolated `uv` environment;
2. checks out the official inference code at a pinned revision;
3. downloads the AnimalCLAP checkpoint and LAION CLAP backbone locally; and
4. verifies that the combined checkpoint loads on the GPU.

The pinned upstream inference script requests a safetensors backbone, while the
published CLAP repository currently provides `pytorch_model.bin`. Setup applies
the checked-in one-line patch `use_pytorch_checkpoint.patch` to load that
official file explicitly.

Runtime files are stored under `storage/models/animalclap/` and the reproducible
upstream checkout is under `model_services/audio/animalclap/upstream/`. Both are
ignored by Git.

Source and model license: MIT. Cite the AnimalCLAP ICASSP 2026 paper when
publishing results produced with the checkpoint.

## Species evaluation

Use a manifest with one labeled file per row:

```csv
species,audio_file
coyote,coyote-verified.ogg
wolf,nri-WolfDENA.mp3
```

Run deterministic 10-second windows with a 5-second hop:

```bash
HF_HUB_CACHE="$PWD/storage/models/animalclap/huggingface/hub" \
  model_services/audio/animalclap/.venv/bin/python \
  model_services/audio/animalclap/infer_species.py \
  data/datasets/audioSet/Voicedata/data.csv \
  notebooks/results/animalclap_species_predictions.json
```

The output contains per-file and per-window candidate rankings. Similarities
are useful for ranking but are not calibrated probabilities.
