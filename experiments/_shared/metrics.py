"""实验评估指标。骨架先搭，跑实验时按需填充。"""
from __future__ import annotations

from typing import Iterable


def accuracy(predictions: Iterable[bool], ground_truth: Iterable[bool]) -> float:
    """二元准确率。"""
    pred = list(predictions)
    truth = list(ground_truth)
    if not pred or len(pred) != len(truth):
        return 0.0
    return sum(p == t for p, t in zip(pred, truth)) / len(pred)


def mae(predictions: Iterable[float], ground_truth: Iterable[float]) -> float:
    """平均绝对误差（用于 1-5 分评分对比）。"""
    pred = list(predictions)
    truth = list(ground_truth)
    if not pred or len(pred) != len(truth):
        return 0.0
    return sum(abs(p - t) for p, t in zip(pred, truth)) / len(pred)


def spearman(predictions: list[float], ground_truth: list[float]) -> float:
    """Spearman 秩相关。等跑评分实验时实装（用 scipy.stats.spearmanr）。"""
    raise NotImplementedError("等评分实验时实装")


def disagreement_pairs(
    model_a: list[dict], model_b: list[dict], key: str = "score"
) -> list[tuple[dict, dict]]:
    """找出两个模型分歧的样本对。供"双模型互审"使用。"""
    pairs = []
    for a, b in zip(model_a, model_b):
        if a.get(key) != b.get(key):
            pairs.append((a, b))
    return pairs
