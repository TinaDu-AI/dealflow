"""
Batch import pipeline: XHS search → Qwen parse → DB upsert.

Flow per keyword:
  1. Run `cli.py search-feeds --keyword K --sort-by 最新`
  2. For each feed: run `cli.py get-feed-detail --feed-id ID --xsec-token T`
  3. Batch up to 5 details → Qwen classify+extract → structured company dicts
  4. db.upsert_company() for each valid result

Job management:
  start_job(keywords, max_per_keyword) → job_id
  get_job(job_id)                       → status/progress dict
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

# ── paths ─────────────────────────────────────────────────────────────────────

_WEBAPP_DIR = Path(__file__).parent
_PROJECT_ROOT = _WEBAPP_DIR.parent
_SCRIPTS_CLI = _PROJECT_ROOT / "scripts" / "cli.py"

# Lazy import llm_service to avoid loading openai at module init time
import importlib
_llm_service_mod = None

def _get_llm_service():
    global _llm_service_mod
    if _llm_service_mod is None:
        sys.path.insert(0, str(_WEBAPP_DIR))
        import llm_service as _m
        _llm_service_mod = _m
    return _llm_service_mod

# Use attribute-style access for llm_service calls
class _LLMProxy:
    def __getattr__(self, name):
        return getattr(_get_llm_service(), name)

llm_service = _LLMProxy()
# Use venv Python outside iCloud-synced Desktop — avoids iCloud file-lock overhead (5-10s/file)
# The ~/.local/share/xhs-venv is created by: UV_PROJECT_ENVIRONMENT=~/.local/share/xhs-venv uv sync
_VENV_PYTHON = Path.home() / ".local" / "share" / "xhs-venv" / "bin" / "python"
# Fallback to project venv if the external one doesn't exist
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"

# ── in-memory job store ────────────────────────────────────────────────────────

_jobs: dict[str, dict] = {}   # job_id → {status, log, results, counts, started_at, finished_at}
_jobs_lock = threading.Lock()


def start_job(
    keywords: list[str],
    max_per_keyword: int = 8,
    institution_name: str = "MFV",
    user_id: int | None = None,
) -> str:
    """Start a background import job. Returns job_id."""
    job_id = str(uuid.uuid4())[:8]
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "log": [],
            "results": [],
            "counts": {
                "keywords_total": len(keywords),
                "keywords_done": 0,
                "feeds_fetched": 0,
                "feeds_parsed": 0,
                "companies_saved": 0,
                "companies_skipped": 0,
            },
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
        }
    t = threading.Thread(
        target=_run_job, args=(job_id, keywords, max_per_keyword, institution_name, user_id),
        daemon=True,
    )
    t.start()
    return job_id


def get_job(job_id: str) -> dict | None:
    """Return job status dict, or None if not found."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        return dict(job)   # shallow copy is fine for reading


def list_jobs() -> list[dict]:
    """Return last 20 jobs (newest first)."""
    with _jobs_lock:
        jobs = [{"id": k, **v} for k, v in _jobs.items()]
    return sorted(jobs, key=lambda j: j.get("started_at", ""), reverse=True)[:20]


# ── internal helpers ───────────────────────────────────────────────────────────

def _log(job_id: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["log"].append(line)


def _update_counts(job_id: str, **kwargs) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            for k, v in kwargs.items():
                _jobs[job_id]["counts"][k] = _jobs[job_id]["counts"].get(k, 0) + v


def _add_result(job_id: str, company: dict) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["results"].append(company)


# ── Bridge health check (fast, no subprocess) ─────────────────────────────────

def _ping_bridge(timeout: float = 5.0) -> tuple[bool, bool]:
    """
    Quick ping to bridge server to check connectivity without spawning CLI.
    Returns (server_running, extension_connected).
    Uses websockets.sync.client which is available in the project venv.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
        from xhs.bridge import BridgePage
        page = BridgePage()
        server_ok = page.is_server_running()
        if not server_ok:
            return False, False
        ext_ok = page.is_extension_connected()
        return True, ext_ok
    except Exception:
        return False, False


# ── CLI subprocess wrapper ─────────────────────────────────────────────────────

def _run_cli(*args: str, timeout: int = 60) -> dict | None:
    """
    Call `uv run python scripts/cli.py <args>` from project root.
    Returns parsed JSON dict, or None on failure.
    """
    env = os.environ.copy()
    # Remove all proxy settings — websockets ignores NO_PROXY when HTTP_PROXY is set,
    # causing WebSocket connections to localhost:9333 to be routed through the proxy and fail.
    for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
               "all_proxy", "ALL_PROXY"):
        env.pop(_k, None)
    env["no_proxy"] = "localhost,127.0.0.1"
    env["NO_PROXY"] = "localhost,127.0.0.1"

    cmd = [str(_VENV_PYTHON), str(_SCRIPTS_CLI), *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
            env=env,
            timeout=timeout,
        )
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return None
    except (json.JSONDecodeError, Exception):
        return None


def _cli_search(keyword: str, max_count: int) -> list[dict]:
    """Search XHS for keyword, return up to max_count feed dicts."""
    data = _run_cli(
        "search-feeds",
        "--keyword", keyword,
        "--sort-by", "最新",
        timeout=120,
    )
    if not data:
        return []
    if data.get("error") or data.get("success") is False:
        return []  # connection/bridge error — preflight should have caught this
    feeds = data.get("feeds", [])
    return feeds[:max_count]


def _cli_detail(feed_id: str, xsec_token: str) -> dict | None:
    """Fetch feed detail (no comments). Returns note dict or None."""
    data = _run_cli(
        "get-feed-detail",
        "--feed-id", feed_id,
        "--xsec-token", xsec_token,
        "--max-comment-items", "0",
        timeout=90,
    )
    if not data or "note" not in data:
        return None
    return data["note"]


# ── Qwen extraction ────────────────────────────────────────────────────────────

_EXTRACT_SYSTEM_TMPL = (
    "你是{institution}投资基金的AI分析助手。"
    "只输出合法 JSON，不要任何额外文字。"
)

_EXTRACT_PROMPT_TMPL = """以下是从小红书搜索到的帖子列表，请判断每个帖子是否描述了一个真实的创业项目或产品，
并提取关键信息。

帖子列表（JSON）：
{{posts_json}}

对每个帖子，输出一个 JSON 对象。如果不是关于真实创业项目/产品（如纯攻略、教程、测评、广告等），
则输出 null。

有效项目输出格式（严格 JSON）：
{{{{
  "idx": <帖子序号 0-based>,
  "name": "项目/公司名称（从帖子提炼，简短）",
  "account": "小红书账号名（即 nickname）",
  "one_liner": "一句话描述项目核心价值（≤30字）",
  "type": "项目类型（如：AI游戏 / AI工具 / 创作者工具 / 电商 / 社交 / SaaS等）",
  "summary": "2-3句话的项目摘要（中文，约100字）",
  "mfv_keywords": "3-5个与{institution}投资方向相关的关键词，逗号分隔",
  "mfv_note": "用一句话说明对{institution}有吸引力的原因（AI原生/创意/管线/引力等角度）"
}}}}

输出格式：JSON 数组，长度与输入帖子数相同，例如：
[{{{{"idx":0,...}}}}, null, {{{{"idx":2,...}}}}]

注意：
- 必须输出与输入完全相同数量的元素
- 个人博主的经验分享、产品测评等不算创业项目
- 项目名从标题或描述中提炼，不要用账号名作为项目名
"""


def _build_prompts(institution_name: str) -> tuple[str, str]:
    """Build system + user prompts with the correct institution name."""
    system = _EXTRACT_SYSTEM_TMPL.format(institution=institution_name)
    prompt_tmpl = _EXTRACT_PROMPT_TMPL.format(institution=institution_name)
    return system, prompt_tmpl


def _qwen_extract_batch(
    posts: list[dict],  # [{idx, title, desc, nickname, type, time, interact}, ...]
    institution_name: str = "MFV",
) -> list[dict | None]:
    """
    Call Qwen to classify + extract structured data for a batch of posts.
    Returns a list of the same length: each element is a company dict or None.
    """
    # Import lazily to avoid circular/optional deps
    sys.path.insert(0, str(_WEBAPP_DIR))
    try:
        import llm_service
    except ImportError:
        return [None] * len(posts)

    if not llm_service.ENABLED:
        return [None] * len(posts)

    extract_system, extract_prompt_tmpl = _build_prompts(institution_name)
    posts_json = json.dumps(posts, ensure_ascii=False, indent=2)
    prompt = extract_prompt_tmpl.format(posts_json=posts_json)

    raw = llm_service._call_qwen(prompt, extract_system)
    if not raw:
        return [None] * len(posts)

    result = llm_service._parse_json(raw)
    if not isinstance(result, list):
        return [None] * len(posts)

    # Pad/trim to match input length
    out: list[dict | None] = []
    for i in range(len(posts)):
        if i < len(result):
            item = result[i]
            if isinstance(item, dict) and item.get("name"):
                out.append(item)
            else:
                out.append(None)
        else:
            out.append(None)
    return out


# ── main job runner ────────────────────────────────────────────────────────────

def _preflight_check(job_id: str) -> bool:
    """
    Two-step preflight:
    1. Fast WebSocket ping (< 5s) to verify bridge + extension are alive.
       Fail immediately if not — no point waiting 5 minutes for a hanging CLI.
    2. Run check-login (45s timeout) to verify XHS login status.
    """
    # ── Step 1: Quick bridge ping ──────────────────────────────────────────────
    _log(job_id, "🔌 检查浏览器扩展连接…")
    server_ok, ext_ok = _ping_bridge(timeout=5.0)

    if not server_ok:
        _log(job_id, "❌ Bridge Server 未运行，请在终端启动：")
        _log(job_id, "   python scripts/bridge_server.py")
        return False

    if not ext_ok:
        _log(job_id, "❌ Chrome 扩展未连接 Bridge，请确认：")
        _log(job_id, "   1. Chrome 已打开，且处于活跃状态（未最小化/休眠）")
        _log(job_id, "   2. XHS Bridge 扩展已安装并启用")
        _log(job_id, "   3. 可在扩展图标处点击「重新连接」后重试")
        return False

    _log(job_id, "✅ Bridge 已连接，检查登录状态…")

    # ── Step 2: check-login (extension is alive, so this should be fast) ──────
    data = _run_cli("check-login", timeout=45)

    if data is None:
        _log(job_id, "❌ check-login 超时（45s），请检查 Chrome 是否响应正常后重试")
        return False

    # Error response from CLI (bridge/connection failure)
    if data.get("success") is False or data.get("error"):
        _log(job_id, f"❌ 浏览器连接失败: {data.get('error', '未知错误')}")
        return False

    # Explicitly not logged in
    if data.get("logged_in") is False:
        _log(job_id, "⚠️ 未登录小红书，请先在 Chrome 中登录后再导入")
        return False

    # Anything else (including logged_in=True) is success
    _log(job_id, "✅ 已登录，开始搜索…")
    return True


def _run_job(job_id: str, keywords: list[str], max_per_keyword: int, institution_name: str = "MFV",
             user_id: int | None = None) -> None:
    """Background thread: runs the full batch import pipeline."""
    import db  # local import to avoid circular deps at module load time

    batch_date = datetime.now().strftime("%Y-%m-%d")

    # Pre-load rubric for scoring (use user's rubric if available, else system defaults)
    try:
        rubric = db.get_rubric(user_id=user_id)
        _rubric_scoring = rubric.get("scoring", [])
        _rubric_viability = rubric.get("viability", [])
    except Exception:
        _rubric_scoring = []
        _rubric_viability = []

    try:
        # ── Preflight: ensure Chrome + extension connected ─────────────────────
        if not _preflight_check(job_id):
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "error"
                    _jobs[job_id]["finished_at"] = datetime.now().isoformat()
            return

        for kw_idx, keyword in enumerate(keywords):
            _log(job_id, f"🔍 搜索关键词 [{kw_idx+1}/{len(keywords)}]: {keyword}")

            # ── 1. Search ──────────────────────────────────────────────────────
            feeds = _cli_search(keyword, max_per_keyword)
            if not feeds:
                _log(job_id, f"  ⚠️ 「{keyword}」未搜到结果")
                _update_counts(job_id, keywords_done=1)
                continue

            _log(job_id, f"  ✅ 找到 {len(feeds)} 个帖子，开始获取详情…")

            # ── 2. Fetch detail for each feed ─────────────────────────────────
            enriched: list[dict] = []   # posts ready for Qwen
            feed_meta: list[dict] = []  # original feed info (for DB)

            for f in feeds:
                feed_id = f.get("id", "")
                xsec_token = f.get("xsecToken", "")
                if not feed_id or not xsec_token:
                    continue

                detail = _cli_detail(feed_id, xsec_token)
                if not detail:
                    continue

                _update_counts(job_id, feeds_fetched=1)

                # Compute XHS url
                xhs_url = (
                    f"https://www.xiaohongshu.com/explore/{feed_id}"
                    f"?xsec_token={xsec_token}&xsec_source=pc_feed"
                )

                # Publish date from timestamp (ms → readable)
                ts = detail.get("time", 0)
                pub_date = ""
                if ts:
                    try:
                        dt = datetime.fromtimestamp(ts / 1000)
                        pub_date = dt.strftime("%Y年%-m月%-d日")
                    except Exception:
                        pub_date = ""

                enriched.append({
                    "idx": len(enriched),
                    "title": detail.get("title", ""),
                    "desc": detail.get("desc", ""),
                    "nickname": detail.get("user", {}).get("nickname", ""),
                    "type": detail.get("type", ""),
                    "publish_date": pub_date,
                    "interact": detail.get("interactInfo", {}),
                })
                feed_meta.append({
                    "feed_id": feed_id,
                    "xsec_token": xsec_token,
                    "xhs_url": xhs_url,
                    "nickname": detail.get("user", {}).get("nickname", ""),
                    "user_id": detail.get("user", {}).get("userId", ""),
                    "publish_date": pub_date,
                })

            if not enriched:
                _log(job_id, f"  ⚠️ 「{keyword}」详情全部获取失败")
                _update_counts(job_id, keywords_done=1)
                continue

            # ── 3. Qwen extract in batches of 5 ──────────────────────────────
            BATCH = 5
            for b_start in range(0, len(enriched), BATCH):
                batch = enriched[b_start:b_start + BATCH]
                meta_batch = feed_meta[b_start:b_start + BATCH]

                _log(job_id, f"  🤖 Qwen 解析 {b_start+1}–{b_start+len(batch)}/{len(enriched)}…")
                parsed = _qwen_extract_batch(batch, institution_name=institution_name)
                _update_counts(job_id, feeds_parsed=len(batch))

                # ── 4. Upsert valid results ────────────────────────────────────
                for i, company_data in enumerate(parsed):
                    if not company_data or not company_data.get("name"):
                        _update_counts(job_id, companies_skipped=1)
                        continue

                    meta = meta_batch[i]
                    raw = enriched[b_start + i]

                    record = {
                        "name": company_data.get("name", ""),
                        "account": meta["nickname"],
                        "type": company_data.get("type", ""),
                        "publish_date": meta["publish_date"],
                        "one_liner": company_data.get("one_liner", ""),
                        "summary": company_data.get("summary", ""),
                        "mfv_keywords": company_data.get("mfv_keywords", ""),
                        "mfv_note": company_data.get("mfv_note", ""),
                        "xhs_url": meta["xhs_url"],
                        "xhs_user_id": meta["user_id"],
                        "batch_date": batch_date,
                        "is_revival": 0,
                        "previous_rejection": None,
                        "id": None,  # let DB auto-assign
                        # Scoring fields — filled below
                        "score_origin": None,
                        "score_amplification": None,
                        "score_gravity": None,
                        "viability_summary": None,
                    }

                    # ── 4a. Rubric scoring via LLM ────────────────────────────
                    if _rubric_scoring:
                        try:
                            scores = llm_service.score_company_rubric(
                                record, _rubric_scoring, _rubric_viability,
                                institution_name=institution_name,
                            )
                            record.update(scores)
                            score_str = (
                                f"{scores.get('score_origin') or '?'}/"
                                f"{scores.get('score_amplification') or '?'}/"
                                f"{scores.get('score_gravity') or '?'}"
                            )
                            _log(job_id, f"  📊 Rubric 评分: {score_str}")
                        except Exception as e:
                            _log(job_id, f"  ⚠️ Rubric 评分失败: {e}")

                    try:
                        db.upsert_company(record)
                        _update_counts(job_id, companies_saved=1)
                        _add_result(job_id, {
                            "name": record["name"],
                            "account": record["account"],
                            "one_liner": record["one_liner"],
                            "xhs_url": record["xhs_url"],
                            "keyword": keyword,
                        })
                        _log(job_id, f"  💾 已保存: 【{record['name']}】({record['account']})")
                    except Exception as e:
                        _log(job_id, f"  ❌ 保存失败: {record['name']} — {e}")
                        _update_counts(job_id, companies_skipped=1)

            _update_counts(job_id, keywords_done=1)

        _log(job_id, "✅ 批量导入完成！")
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["finished_at"] = datetime.now().isoformat()

    except Exception as e:
        _log(job_id, f"❌ 任务异常终止: {e}")
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["finished_at"] = datetime.now().isoformat()
