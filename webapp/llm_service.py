"""
LLM service — Qwen via DashScope OpenAI-compatible API.

Tasks:
  - classify_rejection: 左滑 → A / B1 / B2 分类 + 关键词提取
  - extract_pass_keywords: 右滑 → 内容关键词提取（Layer A 权重回收）
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Callable

# ── load .env ──────────────────────────────────────────────────────────────────
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-turbo"

ENABLED = bool(DASHSCOPE_API_KEY)


# ── core Qwen caller ───────────────────────────────────────────────────────────

def _call_qwen(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    """Call Qwen and return raw text. Returns '' on any error."""
    if not ENABLED:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=0.1, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[llm] Qwen call failed: {e}")
        return ""


def _parse_json(raw: str) -> dict | list | None:
    """Strip markdown fences and parse JSON."""
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        # take the content inside the first fence
        text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
    try:
        return json.loads(text)
    except Exception:
        return None


# ── Task 1 & 2: rejection classification ──────────────────────────────────────

_CLASSIFY_SYSTEM = (
    "你是一位投资助手，帮助分析投资人拒绝某个项目的原因。"
    "只输出合法 JSON，不要任何额外文字。"
)

_CLASSIFY_PROMPT = """项目信息：
名称：{name}
摘要：{summary}
类型：{type}
MFV关键词：{mfv_keywords}

投资人拒绝理由：{note}

请将本次拒绝分类为以下三类之一，输出 JSON：

A类（内容类型排除）：投资人不想看这一类型的项目（如"不做纯文字游戏"、"不看K12教育"）
  → extracted_keyword: 具体内容子类型（如"纯文字游戏"、"K12教育"）
  → expiry_type 规则：
      permanent  = 投资人表达强烈永久排斥（"永远不"、"完全不感兴趣"）
      trend      = 当前趋势相关，可能会变（3轮后失效）
      temporary  = 暂时不想看（10轮后失效）

B1类（评分信号）：因某个评分维度太低而拒绝（如"创意太普通"、"管线没护城河"）
  → extracted_keyword: 评分维度名称（如"创意"、"管线"、"引力"）

B2类（习惯偏好）：个人习惯偏好，非内容类型、非评分（如"太早期"、"团队背景不够"）
  → extracted_keyword: 偏好描述（简短，如"过早期"、"团队背景弱"）

输出 JSON（严格格式）：
{{
  "rejection_type": "A" | "B1" | "B2",
  "extracted_keyword": "关键词" | null,
  "expiry_type": "permanent" | "trend" | "temporary" | null,
  "expiry_after_scans": 3 | 10 | null
}}"""

_EXPIRY_SCANS = {"trend": 3, "temporary": 10, "permanent": None}


def classify_rejection(company: dict, note: str) -> dict:
    """
    Classify a left-swipe rejection.
    Returns dict with keys: rejection_type, extracted_keyword, expiry_type, expiry_after_scans.
    """
    _empty = {"rejection_type": None, "extracted_keyword": None,
               "expiry_type": None, "expiry_after_scans": None}
    if not ENABLED:
        return _empty

    prompt = _CLASSIFY_PROMPT.format(
        name=company.get("name", ""),
        summary=company.get("summary", ""),
        type=company.get("type", ""),
        mfv_keywords=company.get("mfv_keywords", ""),
        note=note or "（无备注）",
    )
    raw = _call_qwen(prompt, _CLASSIFY_SYSTEM)
    result = _parse_json(raw)
    if not isinstance(result, dict):
        print(f"[llm] classify_rejection bad output: {raw!r}")
        return _empty

    rt = result.get("rejection_type")
    if rt not in ("A", "B1", "B2"):
        return _empty

    # Normalise expiry fields
    et = result.get("expiry_type")
    if rt == "A" and et in _EXPIRY_SCANS:
        result["expiry_after_scans"] = _EXPIRY_SCANS[et]
    else:
        result["expiry_type"] = None
        result["expiry_after_scans"] = None

    return {
        "rejection_type": rt,
        "extracted_keyword": result.get("extracted_keyword") or None,
        "expiry_type": result.get("expiry_type"),
        "expiry_after_scans": result.get("expiry_after_scans"),
    }


# ── Task 4: pass keyword extraction ───────────────────────────────────────────

_PASS_SYSTEM = "你是投资分析助手，从项目信息提取内容关键词。只输出 JSON 数组，不要其他内容。"

_PASS_PROMPT = """从以下项目信息中提取 3-5 个最能代表其内容类型的关键词（中文，简短）：

名称：{name}
摘要：{summary}
类型：{type}
MFV关键词：{mfv_keywords}

输出 JSON 数组，例如：["AI游戏引擎", "多Agent协作", "创作者工具"]
只输出数组，不要其他内容。"""


def extract_pass_keywords(company: dict) -> list[str]:
    """Extract content keywords from a right-swiped company for Layer A tracking."""
    if not ENABLED:
        return []
    prompt = _PASS_PROMPT.format(
        name=company.get("name", ""),
        summary=company.get("summary", ""),
        type=company.get("type", ""),
        mfv_keywords=company.get("mfv_keywords", ""),
    )
    raw = _call_qwen(prompt, _PASS_SYSTEM)
    result = _parse_json(raw)
    if isinstance(result, list):
        return [str(k) for k in result[:5] if k]
    print(f"[llm] extract_pass_keywords bad output: {raw!r}")
    return []


# ── Async wrappers (fire-and-forget background threads) ───────────────────────

def classify_rejection_async(
    swipe_id: int,
    company: dict,
    note: str,
    on_done: Callable[[int, dict], None],
) -> None:
    """Run classify_rejection in background, call on_done(swipe_id, result) when complete."""
    def _worker():
        result = classify_rejection(company, note)
        if result.get("rejection_type"):
            try:
                on_done(swipe_id, result)
            except Exception as e:
                print(f"[llm] classify on_done error: {e}")
    threading.Thread(target=_worker, daemon=True).start()


def extract_keywords_async(
    swipe_id: int,
    company: dict,
    on_done: Callable[[int, list[str]], None],
) -> None:
    """Run extract_pass_keywords in background, call on_done(swipe_id, keywords) when complete."""
    def _worker():
        keywords = extract_pass_keywords(company)
        if keywords:
            try:
                on_done(swipe_id, keywords)
            except Exception as e:
                print(f"[llm] keywords on_done error: {e}")
    threading.Thread(target=_worker, daemon=True).start()


# ── Task 5: rubric scoring ─────────────────────────────────────────────────────

_SCORE_SYSTEM_TMPL = (
    "你是{institution}投资基金的AI分析助手，根据投资框架对项目进行评分。"
    "只输出合法 JSON，不要任何额外文字。"
)

_SCORE_PROMPT_TMPL = """项目信息：
名称：{name}
摘要：{summary}
类型：{type}
投资分析：{note}

请根据以下框架对该项目打分（每项 1-5 分）并回答现实核查：

{scoring_block}

现实核查（每个问题用≤15字回答）：
{viability_block}

输出 JSON（严格格式，key 使用维度名）：
{json_template}"""


def score_company_rubric(
    company: dict,
    scoring_items: list[dict],
    viability_items: list[dict],
    institution_name: str = "MFV",
) -> dict:
    """
    Score a company against the user's rubric.

    scoring_items: rubric rows with category='scoring', each has category_name, question, scale_1, scale_5
    viability_items: rubric rows with category='viability', each has question

    Returns:
        {
          "score_origin": int (1-5, avg of 1st dim),
          "score_amplification": int (1-5, avg of 2nd dim),
          "score_gravity": int (1-5, avg of 3rd dim),
          "viability_summary": str ("答1·答2·答3"),
        }
    All values default to None on failure.
    """
    _empty: dict = {
        "score_origin": None, "score_amplification": None,
        "score_gravity": None, "viability_summary": None,
    }
    if not ENABLED or not scoring_items:
        return _empty

    # Group scoring items by category_name (preserve insertion order → first 3 distinct dims)
    dim_map: dict[str, list[dict]] = {}
    for item in scoring_items:
        name = (item.get("category_name") or "").strip()
        if not name:
            continue
        dim_map.setdefault(name, []).append(item)
    if not dim_map:
        return _empty
    dims = list(dim_map.keys())[:3]  # at most 3 scoring dimensions

    # Build scoring block
    scoring_lines = []
    for dim in dims:
        scoring_lines.append(f"【{dim}】（输出 JSON key: \"{dim}\"，值为整数数组）")
        for i, item in enumerate(dim_map[dim], 1):
            q = item.get("question", "").replace(f"【{dim}】", "").strip()
            s1 = item.get("scale_1") or ""
            s5 = item.get("scale_5") or ""
            scale = f"（1={s1}，5={s5}）" if s1 or s5 else ""
            scoring_lines.append(f"  Q{i}: {q}{scale}")
    scoring_block = "\n".join(scoring_lines)

    # Build viability block
    v_lines = [f"V{i+1}: {item.get('question','')}" for i, item in enumerate(viability_items[:3])]
    viability_block = "\n".join(v_lines) if v_lines else "（无）"

    # Build expected JSON template
    dim_entries = ", ".join(f'"{d}": [分,分,分]' for d in dims)
    v_entries = ", ".join(f'"v{i+1}": "答案"' for i in range(len(v_lines)))
    json_template = "{" + dim_entries + (", " + v_entries if v_entries else "") + "}"

    prompt = _SCORE_PROMPT_TMPL.format(
        name=company.get("name", ""),
        summary=company.get("summary", ""),
        type=company.get("type", ""),
        note=company.get("mfv_note", ""),
        scoring_block=scoring_block,
        viability_block=viability_block,
        json_template=json_template,
    )
    system = _SCORE_SYSTEM_TMPL.format(institution=institution_name)
    raw = _call_qwen(prompt, system, max_tokens=600)
    if not raw:
        return _empty

    result = _parse_json(raw)
    if not isinstance(result, dict):
        print(f"[llm] score_company_rubric bad output: {raw!r}")
        return _empty

    def _avg(vals: list) -> int | None:
        nums = [v for v in vals if isinstance(v, (int, float))]
        if not nums:
            return None
        return max(1, min(5, round(sum(nums) / len(nums))))

    dim_scores = [_avg(result.get(d, [])) for d in dims]
    # Pad to 3 dimensions
    while len(dim_scores) < 3:
        dim_scores.append(None)

    # viability_summary: join short answers with "·"
    v_answers = [str(result.get(f"v{i+1}", "")).strip() for i in range(len(v_lines))]
    viability_summary = "·".join(a for a in v_answers if a) or None

    return {
        "score_origin": dim_scores[0],
        "score_amplification": dim_scores[1],
        "score_gravity": dim_scores[2],
        "viability_summary": viability_summary,
    }
