"""Rank candidate species for labeled audio files with AnimalCLAP."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48_000


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["species", "audio_file"]:
            raise ValueError("CSV headers must be exactly: species,audio_file")
        rows = [
            {"species": row["species"].strip(), "audio_file": row["audio_file"].strip()}
            for row in reader
        ]
    if not rows or any(not row["species"] or not row["audio_file"] for row in rows):
        raise ValueError("CSV must contain non-empty species and audio_file values")
    return rows


def make_windows(
    audio: np.ndarray, window_samples: int, hop_samples: int
) -> list[tuple[int, int, np.ndarray]]:
    if audio.size == 0:
        raise ValueError("Audio is empty")
    windows = []
    for start in range(0, max(audio.size, 1), hop_samples):
        end = min(start + window_samples, audio.size)
        chunk = audio[start:end]
        if chunk.size < window_samples:
            chunk = np.pad(chunk, (0, window_samples - chunk.size))
        windows.append((start, end, chunk.astype(np.float32, copy=False)))
        if end == audio.size:
            break
    return windows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--hop-seconds", type=float, default=5.0)
    parser.add_argument("--batch-size", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = args.manifest.resolve()
    rows = read_manifest(manifest)
    audio_dir = manifest.parent
    missing = [
        row["audio_file"]
        for row in rows
        if not (audio_dir / row["audio_file"]).is_file()
    ]
    if missing:
        raise FileNotFoundError(f"Missing audio files: {missing}")

    import librosa
    import torch
    from verify import load_model

    model, device = load_model()
    labels = sorted({row["species"] for row in rows})
    class_text = [label.replace("_", " ") for label in labels]

    with torch.inference_mode():
        text_features = model.encode_text(class_text)
        text_features = model.text_head(text_features)
        text_features = torch.nn.functional.normalize(text_features, dim=-1)

    window_samples = round(args.window_seconds * SAMPLE_RATE)
    hop_samples = round(args.hop_seconds * SAMPLE_RATE)
    results = []

    for index, row in enumerate(rows, start=1):
        path = audio_dir / row["audio_file"]
        audio, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
        windows = make_windows(audio, window_samples, hop_samples)
        window_results = []
        all_scores = []

        for offset in range(0, len(windows), args.batch_size):
            batch_windows = windows[offset : offset + args.batch_size]
            batch = torch.from_numpy(np.stack([item[2] for item in batch_windows])).to(
                device
            )
            with torch.inference_mode():
                audio_features = model.audio_head(
                    model.encode_audio(batch, SAMPLE_RATE)
                )
                audio_features = torch.nn.functional.normalize(audio_features, dim=-1)
                scores = (audio_features @ text_features.T).cpu().numpy()
            all_scores.extend(scores)

            for (start, end, _), score_row in zip(batch_windows, scores, strict=True):
                order = np.argsort(score_row)[::-1]
                window_results.append(
                    {
                        "start_s": round(start / SAMPLE_RATE, 3),
                        "end_s": round(end / SAMPLE_RATE, 3),
                        "predicted_species": labels[int(order[0])],
                        "rankings": [
                            {
                                "species": labels[int(i)],
                                "similarity": round(float(score_row[i]), 6),
                            }
                            for i in order
                        ],
                    }
                )

        mean_scores = np.mean(np.asarray(all_scores), axis=0)
        order = np.argsort(mean_scores)[::-1]
        prediction = labels[int(order[0])]
        results.append(
            {
                "audio_file": row["audio_file"],
                "expected_species": row["species"],
                "predicted_species": prediction,
                "correct": prediction == row["species"],
                "rankings": [
                    {
                        "species": labels[int(i)],
                        "mean_similarity": round(float(mean_scores[i]), 6),
                    }
                    for i in order
                ],
                "windows": window_results,
            }
        )
        progress = f"[{index}/{len(rows)}] {path.name}"
        print(f"{progress}: expected={row['species']} predicted={prediction}")

    payload = {
        "model": "risashinoda/animalclap",
        "candidate_species": labels,
        "window_seconds": args.window_seconds,
        "hop_seconds": args.hop_seconds,
        "files": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    correct = sum(result["correct"] for result in results)
    accuracy = correct / len(results)
    print(f"Top-1 file accuracy: {accuracy:.3f} ({correct}/{len(results)})")
    print(f"Saved {args.output.resolve()}")


if __name__ == "__main__":
    main()
