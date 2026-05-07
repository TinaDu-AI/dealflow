"""把 results.json 渲染成可读的 report.html。骨架先占位。"""
from __future__ import annotations

import json
from pathlib import Path


def render_report(results_json: str | Path, output_html: str | Path) -> Path:
    """读 results.json，写 report.html（side-by-side 对比 + evidence 字段可见）。"""
    raise NotImplementedError("跑完第一次实验、有真实 results.json 后再实装模板")


def render_index(experiments_root: str | Path) -> Path:
    """扫描 experiments/*/results.json，生成总索引（新旧对比表）。"""
    raise NotImplementedError("有 2 次以上实验后再实装")
