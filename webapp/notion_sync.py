"""
Notion 同步 — 把 dashboard 数据推到 Notion 页面。

策略：清空目标页 children → 重写 markdown 段落 + 表格。简单粗暴但可靠。
失败时返回 (False, error_msg)，不影响 webapp 主流程。
"""
from __future__ import annotations

import os
import urllib.request
import urllib.error
import json
from pathlib import Path

# Load .env (same pattern as llm_service.py)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_PAGE_ID = os.environ.get("NOTION_DASHBOARD_PAGE_ID", "")
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
ENABLED = bool(NOTION_API_KEY and NOTION_PAGE_ID)


def _request(method: str, path: str, body: dict | None = None) -> dict:
    """Plain HTTPS request to Notion API. Avoids extra deps."""
    url = f"{NOTION_API}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {NOTION_API_KEY}")
    req.add_header("Notion-Version", NOTION_VERSION)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"Notion {method} {path} failed: {e.code} {msg}")


def _list_children(page_id: str) -> list[dict]:
    out: list[dict] = []
    cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        r = _request("GET", path)
        out.extend(r.get("results", []))
        if not r.get("has_more"):
            break
        cursor = r.get("next_cursor")
    return out


def _delete_block(block_id: str) -> None:
    _request("DELETE", f"/blocks/{block_id}")


def _append_children(page_id: str, blocks: list[dict]) -> None:
    # Notion API caps at 100 children per call
    for i in range(0, len(blocks), 100):
        _request("PATCH", f"/blocks/{page_id}/children",
                 {"children": blocks[i:i+100]})


def _rt(text: str) -> list[dict]:
    """Build a minimal rich_text array. Truncate to Notion's 2000-char cap."""
    return [{"type": "text", "text": {"content": (text or "")[:2000]}}]


def _paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rt(text)}}


def _heading(text: str, level: int = 1) -> dict:
    t = f"heading_{min(max(level, 1), 3)}"
    return {"object": "block", "type": t, t: {"rich_text": _rt(text)}}


def _table(rows: list[list[str]], has_header: bool = True) -> dict:
    if not rows:
        return _paragraph("（无数据）")
    width = max(len(r) for r in rows)
    children = []
    for row in rows:
        cells = [_rt(c) for c in row]
        while len(cells) < width:
            cells.append(_rt(""))
        children.append({"object": "block", "type": "table_row",
                         "table_row": {"cells": cells}})
    return {
        "object": "block", "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": has_header,
            "has_row_header": False,
            "children": children,
        },
    }


# ── Public API ───────────────────────────────────────────────────────────────

def sync_from_db() -> tuple[bool, str, int]:
    """Read companies + latest swipes from mfv.db, sync to Notion.

    Shared by:
    - /api/admin/dashboard/export-notion (HTTP)
    - cron_notion_sync.py (launchd)

    Returns (ok, message, rows_synced).
    """
    if not ENABLED:
        return False, "NOTION_API_KEY 或 NOTION_DASHBOARD_PAGE_ID 未配置", 0

    import sys
    from datetime import datetime as _dt
    sys.path.insert(0, str(Path(__file__).parent))
    import db as _db

    cn_class = {"A": "类型不感兴趣", "B1": "评分维度不达标", "B2": "其他偏好"}
    with _db.get_conn() as conn:
        companies = [dict(r) for r in conn.execute(
            "SELECT * FROM companies ORDER BY id DESC"
        ).fetchall()]
        sw_rows = conn.execute("""
            SELECT s.* FROM swipes s
            INNER JOIN (SELECT company_id, MAX(id) AS m FROM swipes GROUP BY company_id) x
              ON s.id = x.m
        """).fetchall()
        swipes_by_cid = {r["company_id"]: dict(r) for r in sw_rows}

    header = ["#", "项目", "账号", "类型", "关键词", "评分",
              "Swipe", "拒绝分类", "备注", "话术", "URL"]
    rows: list[list[str]] = []
    right_cnt = left_cnt = 0
    for c in companies:
        sw = swipes_by_cid.get(c["id"], {})
        score = (
            f"{c['score_origin']}·{c['score_amplification'] or '?'}·{c['score_gravity'] or '?'}"
            if c.get("score_origin") is not None else "—"
        )
        d = sw.get("direction")
        swipe_str = "👉" if d == "right" else ("👈" if d == "left" else "—")
        if d == "right":
            right_cnt += 1
        elif d == "left":
            left_cnt += 1
        rclass = cn_class.get(sw.get("rejection_type"), "—")
        note = (sw.get("note") or "").replace("\n", " ")[:50] or "—"
        dm = "—"
        if d == "right":
            orig = (sw.get("dm_original") or "").strip()
            sent = (sw.get("dm_text") or "").strip()
            dm = "未生成" if not sent else (
                "原版直发" if (not orig or orig == sent) else f"已修改({len(sent)}字)"
            )
        rows.append([
            str(c["id"]), c.get("name", "") or "", "@" + (c.get("account") or ""),
            c.get("type", "") or "", c.get("search_keyword") or "—",
            score, swipe_str, rclass, note, dm, c.get("xhs_url") or "",
        ])

    summary = (
        f"自动同步 · {_dt.now().strftime('%Y-%m-%d %H:%M')} · "
        f"共 {len(companies)} 条 · {right_cnt} 通过 / {left_cnt} 拒绝"
    )
    ok, msg = sync_dashboard(rows, header, summary)
    return ok, msg, len(rows)


def sync_dashboard(rows: list[list[str]], header: list[str], summary: str) -> tuple[bool, str]:
    """
    rows: each row = [#, 项目, 账号, 类型, 关键词, 评分, Swipe, 拒绝分类, 备注, 话术, URL]
    header: same shape, used as table header
    summary: a paragraph at top (timestamp + counts)
    Returns (ok, message).
    """
    if not ENABLED:
        return False, "NOTION_API_KEY 未配置"
    try:
        page_id = NOTION_PAGE_ID
        # 1. Wipe existing children (only top-level direct children)
        existing = _list_children(page_id)
        for blk in existing:
            try:
                _delete_block(blk["id"])
            except Exception:
                pass  # best-effort

        # 2. Compose new content: callout + heading + table
        blocks = [
            {"object": "block", "type": "callout",
             "callout": {
                 "rich_text": _rt(summary),
                 "icon": {"emoji": "📊"},
                 "color": "purple_background",
             }},
            _heading("数据看板", level=2),
            _table([header] + rows, has_header=True),
        ]
        _append_children(page_id, blocks)
        return True, "synced"
    except Exception as e:
        return False, str(e)
