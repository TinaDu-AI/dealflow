"""
实验通用执行器。

设计原则（少云方法论）：
- 直接 import 生产代码（webapp/llm_service.py 等），禁止重写生产函数
- 实验通过传参（model_name / prompt_template）替换生产默认值
- 所有结果只写 JSON，不写 mfv.db

典型用法（在 experiments/<编号>-<主题>/run.py 中）：

    from experiments._shared.runner import run_score_experiment

    run_score_experiment(
        corpus="experiments/_shared/corpus/2026-05-04-snapshot.jsonl",
        config={
            "model_name": "deepseek-chat",
            "prompt_template": open("prompt.txt").read(),
            "temperature": 0.1,
        },
        output_dir=".",  # results.json + report.html 写到本地
    )
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_WEBAPP = _PROJECT_ROOT / "webapp"

if str(_WEBAPP) not in sys.path:
    sys.path.insert(0, str(_WEBAPP))


def load_corpus(path: str | Path) -> list[dict]:
    """读取冻结的 corpus JSONL 文件。每行一个帖子 dict。"""
    path = Path(path)
    items: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_ground_truth(path: str | Path) -> dict[str, dict]:
    """读取 ground truth JSONL。返回 {item_id: {label, score, notes, ...}}。"""
    path = Path(path)
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "id" in row:
                out[row["id"]] = row
    return out


def write_results(output_dir: str | Path, results: list[dict], config: dict) -> Path:
    """写 results.json 到实验目录。返回写入路径。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "results.json"
    with path.open("w") as f:
        json.dump(
            {"config": config, "results": results},
            f,
            ensure_ascii=False,
            indent=2,
        )
    return path


# ── 占位：实验执行函数 ──────────────────────────────────────────────────────
# 这些函数在跑第一个实验时填充实现。骨架先搭好，避免后续把"实验逻辑"和
# "调用生产代码"耦合在一起。

def run_score_experiment(corpus: str, config: dict, output_dir: str) -> dict:
    """
    跑评分实验：corpus 中每条帖子调用生产 score_company_rubric，
    可通过 config 覆盖 model_name / prompt_template。
    返回 summary dict，结果写到 output_dir/results.json。
    """
    raise NotImplementedError("等第一个评分实验时实装")


def run_extract_experiment(corpus: str, config: dict, output_dir: str) -> dict:
    """跑抽取实验（1c 阶段）：判断是否真创业项目 + 提取结构化信息。"""
    raise NotImplementedError("等第一个抽取实验时实装")


def run_classify_experiment(corpus: str, config: dict, output_dir: str) -> dict:
    """跑左滑分类实验（A/B1/B2）。"""
    raise NotImplementedError("等第一个分类实验时实装")
