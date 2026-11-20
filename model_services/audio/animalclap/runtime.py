"""Reusable local AnimalCLAP candidate-species ranker."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from model_services.audio.animalclap.infer_species import SAMPLE_RATE, make_windows
from shared.contracts import SpeciesRanking, WildlifeAudioAnalysis

CANDIDATE_SPECIES = (
    "coyote",
    "elk",
    "grizzly_bear",
    "mountain_lion",
    "wolf",
)


def format_analysis(
    labels: tuple[str, ...], scores: np.ndarray
) -> WildlifeAudioAnalysis:
    order = np.argsort(scores)[::-1]
    top = int(order[0])
    runner_up = int(order[1])
    species = labels[top]
    rendered_species = species.replace("_", " ")
    return WildlifeAudioAnalysis(
        possible_species=species,
        similarity=round(float(scores[top]), 6),
        score_margin=round(float(scores[top] - scores[runner_up]), 6),
        message=(
            "Possible wildlife sound detected — "
            f"possible species: {rendered_species}"
        ),
        rankings=[
            SpeciesRanking(
                species=labels[int(index)],
                similarity=round(float(scores[index]), 6),
            )
            for index in order
        ],
    )


class AnimalCLAPRuntime:
    def __init__(self) -> None:
        import torch

        from model_services.audio.animalclap.verify import load_model

        self.torch = torch
        self.model, self.device = load_model()
        self.labels = CANDIDATE_SPECIES
        prompts = [label.replace("_", " ") for label in self.labels]
        with self.torch.inference_mode():
            features = self.model.text_head(self.model.encode_text(prompts))
            self.text_features = self.torch.nn.functional.normalize(features, dim=-1)

    def analyze(self, audio_path: Path) -> WildlifeAudioAnalysis:
        import librosa

        audio, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
        windows = make_windows(
            audio,
            window_samples=10 * SAMPLE_RATE,
            hop_samples=5 * SAMPLE_RATE,
        )
        score_batches: list[np.ndarray] = []
        for offset in range(0, len(windows), 8):
            batch_windows = windows[offset : offset + 8]
            batch = self.torch.from_numpy(
                np.stack([window[2] for window in batch_windows])
            ).to(self.device)
            with self.torch.inference_mode():
                features = self.model.audio_head(
                    self.model.encode_audio(batch, SAMPLE_RATE)
                )
                features = self.torch.nn.functional.normalize(features, dim=-1)
                score_batches.append(
                    (features @ self.text_features.T).cpu().numpy()
                )
        mean_scores = np.concatenate(score_batches, axis=0).mean(axis=0)
        return format_analysis(self.labels, mean_scores)
