from pathlib import Path

import pytest

from scripts.train_deer_detector import ValidationResult, choose_best


def _result(
    name: str, *, map50_95: float, map50: float, recall: float
) -> ValidationResult:
    return ValidationResult(
        initialization=name,
        checkpoint=Path(f"{name}.pt"),
        precision=0.5,
        recall=recall,
        map50=map50,
        map50_95=map50_95,
    )


def test_choose_best_prioritizes_map50_95() -> None:
    lower_map = _result("wildlife", map50_95=0.4, map50=0.9, recall=0.9)
    higher_map = _result("coco", map50_95=0.5, map50=0.6, recall=0.6)

    assert choose_best([lower_map, higher_map]) is higher_map


def test_choose_best_requires_results() -> None:
    with pytest.raises(ValueError, match="At least one"):
        choose_best([])
