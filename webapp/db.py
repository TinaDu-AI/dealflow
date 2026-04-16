from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import os

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(__file__).parent / "mfv.db"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY,
                name TEXT,
                account TEXT,
                type TEXT,
                publish_date TEXT,
                one_liner TEXT,
                summary TEXT,
                mfv_keywords TEXT,
                mfv_note TEXT,
                xhs_url TEXT,
                xhs_user_id TEXT,
                batch_date TEXT
            );

            CREATE TABLE IF NOT EXISTS swipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                direction TEXT,
                note TEXT,
                dm_text TEXT,
                swiped_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                password_hash TEXT,
                name TEXT,
                gender TEXT,
                age INTEGER,
                institution TEXT,
                title TEXT,
                is_admin INTEGER DEFAULT 0,
                email_verified INTEGER DEFAULT 0,
                profile_completed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                expires_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS verification_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                used INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS user_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                track_main TEXT NOT NULL,
                track_sub TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS pass_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                keyword TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)

        # Incremental migrations — safe to re-run
        migrations = [
            "ALTER TABLE swipes ADD COLUMN contact_status TEXT DEFAULT 'pending'",
            "ALTER TABLE swipes ADD COLUMN user_id INTEGER",
            "ALTER TABLE companies ADD COLUMN is_revival INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN previous_rejection TEXT",
            "ALTER TABLE companies ADD COLUMN score_origin INTEGER",
            "ALTER TABLE companies ADD COLUMN score_amplification INTEGER",
            "ALTER TABLE companies ADD COLUMN score_gravity INTEGER",
            "ALTER TABLE companies ADD COLUMN viability_summary TEXT",
            # P0: swipe timing + rejection intelligence
            "ALTER TABLE swipes ADD COLUMN shown_at TEXT",
            "ALTER TABLE swipes ADD COLUMN decided_at TEXT",
            "ALTER TABLE swipes ADD COLUMN rejection_type TEXT",
            "ALTER TABLE swipes ADD COLUMN extracted_keyword TEXT",
            "ALTER TABLE swipes ADD COLUMN expiry_type TEXT",
            "ALTER TABLE swipes ADD COLUMN expiry_after_scans INTEGER",
            # P0: rubric category names
            "ALTER TABLE rubric ADD COLUMN category_name TEXT",
            # P2: revival — scan-round tracking
            "ALTER TABLE users ADD COLUMN scan_count INTEGER DEFAULT 0",
            "ALTER TABLE swipes ADD COLUMN rejected_at_scan INTEGER",
            # Custom keywords per user (JSON array stored as TEXT)
            "ALTER TABLE users ADD COLUMN custom_keywords TEXT DEFAULT '[]'",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
            except Exception:
                pass

    _seed_admin()
    init_rubric()
    _migrate_category_names()


def _seed_admin() -> None:
    """Pre-create the admin user if not already exists."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)
        ).fetchone()
        if not row:
            conn.execute(
                """INSERT INTO users (email, phone, is_admin, email_verified)
                   VALUES (?, ?, 1, 0)""",
                (ADMIN_EMAIL, ADMIN_PHONE),
            )


# ──────────────────────────────────────────────────────────────────────────────
# RUBRIC
# ──────────────────────────────────────────────────────────────────────────────

def init_rubric() -> None:
    """Create rubric table and seed system defaults if empty."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rubric (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                category TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                question TEXT NOT NULL,
                threshold TEXT,
                scale_1 TEXT,
                scale_5 TEXT,
                enabled INTEGER DEFAULT 1
            );
        """)
        # migrate: add user_id if missing
        try:
            conn.execute("ALTER TABLE rubric ADD COLUMN user_id INTEGER")
        except Exception:
            pass

        count = conn.execute(
            "SELECT COUNT(*) FROM rubric WHERE user_id IS NULL"
        ).fetchone()[0]
        if count > 0:
            return

    # Seed system defaults (user_id = NULL)
    exclusion_items = [
        (1, "AI 是产品的核心运转机制，而非仅用于生产流程？", "Yes 才留", None, None),
        (2, "帖子发布时间在窗口内或有持续热度？", "7天内，或互动仍在增长", None, None),
        (3, "互动数据非零？（赞+藏+评之和）", "≥ 10", None, None),
        (4, "可识别出具体项目或团队（非泛泛内容号）？", "Yes 才留", None, None),
    ]
    # (sort_order, question, threshold, scale_1, scale_5, category_name)
    scoring_items = [
        (1, "【Origin】创意核心是否只有极少数人会想到？", None, "泛泛，很多人都有", "万里挑一，极度偏执", "创意"),
        (2, "【Origin】创始人是否有明显的执念与坚持证据？", None, "无证据", "半年+坚持/自掏腰包/放弃稳定工作", "创意"),
        (3, "【Origin】这个创意是否只有在AI出现后才成立？", None, "AI出现前就能做", "纯AI原生，无AI则不存在", "创意"),
        (4, "【Amplification】AI在产品中的角色是？", None, "辅助生产工具", "管线即产品，AI是核心交付物", "管线"),
        (5, "【Amplification】小团队用此管线，放大倍数是？", None, "没有明显放大", "1人能干10人团队的活", "管线"),
        (6, "【Amplification】AI管线的可替代性（护城河深度）？", None, "随时可换其他工具", "深度集成，竞对极难复制", "管线"),
        (7, "【Gravity】用户行为本身是否在生产内容或数据？", None, "无，纯消费", "每次互动都是内容生产", "引力"),
        (8, "【Gravity】是否有早期用户自发传播的证据？", None, "无", "多群满员/内测溢出/自发二创", "引力"),
        (9, "【Gravity】互动内容质量（评论是否有实质讨论）？", None, "无效互动/刷屏", "深度讨论，用户强代入感", "引力"),
    ]
    viability_items = [
        (1, "这是「值得投的公司」还是「值得观察的现象」？", None, None, None),
        (2, "这个人/团队能融资、能交付、能长大吗？", None, None, None),
        (3, "是否有任何收入或付费意愿信号？", None, None, None),
    ]

    insert_sql = (
        "INSERT INTO rubric"
        " (user_id, category, sort_order, question, threshold, scale_1, scale_5, enabled, category_name)"
        " VALUES (NULL, ?, ?, ?, ?, ?, ?, 1, ?)"
    )
    with get_conn() as conn:
        for sort_order, question, threshold, scale_1, scale_5 in exclusion_items:
            conn.execute(insert_sql, ("exclusion", sort_order, question, threshold, scale_1, scale_5, None))
        for sort_order, question, threshold, scale_1, scale_5, cat_name in scoring_items:
            conn.execute(insert_sql, ("scoring", sort_order, question, threshold, scale_1, scale_5, cat_name))
        for sort_order, question, threshold, scale_1, scale_5 in viability_items:
            conn.execute(insert_sql, ("viability", sort_order, question, threshold, scale_1, scale_5, None))


def _migrate_category_names() -> None:
    """One-time: extract [Tag] prefix from scoring questions into category_name."""
    import re
    tag_map = {"Origin": "创意", "Amplification": "管线", "Gravity": "引力"}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, question FROM rubric WHERE category='scoring'"
            " AND (category_name IS NULL OR category_name = '')"
        ).fetchall()
        for row in rows:
            m = re.match(r"^【([^】]+)】", row["question"])
            if m:
                cat_name = tag_map.get(m.group(1), m.group(1))
                conn.execute(
                    "UPDATE rubric SET category_name = ? WHERE id = ?",
                    (cat_name, row["id"]),
                )


def ensure_user_rubric(user_id: int) -> None:
    """Copy system default rubric to user if they have no personal rubric yet."""
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM rubric WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        if count > 0:
            return
        defaults = conn.execute(
            "SELECT * FROM rubric WHERE user_id IS NULL ORDER BY category, sort_order, id"
        ).fetchall()
        for row in defaults:
            conn.execute(
                """INSERT INTO rubric
                   (user_id, category, sort_order, question, threshold, scale_1, scale_5, enabled, category_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    row["category"],
                    row["sort_order"],
                    row["question"],
                    row["threshold"],
                    row["scale_1"],
                    row["scale_5"],
                    row["enabled"],
                    row["category_name"] if "category_name" in row.keys() else None,
                ),
            )


def get_rubric(user_id: int | None = None) -> dict:
    """Return rubric items for a user (or system defaults if user_id is None)."""
    with get_conn() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM rubric WHERE user_id = ? ORDER BY category, sort_order, id",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM rubric WHERE user_id IS NULL ORDER BY category, sort_order, id"
            ).fetchall()

    result: dict[str, list[dict]] = {"exclusion": [], "scoring": [], "viability": []}
    for row in rows:
        d = dict(row)
        cat = d.get("category", "")
        if cat in result:
            result[cat].append(d)
        else:
            result[cat] = [d]
    return result


def upsert_rubric_item(
    id: int | None,
    category: str,
    sort_order: int,
    question: str,
    threshold: str | None,
    scale_1: str | None,
    scale_5: str | None,
    enabled: int,
    user_id: int | None = None,
    category_name: str | None = None,
) -> int:
    with get_conn() as conn:
        if id:
            conn.execute(
                """UPDATE rubric
                   SET category=?, sort_order=?, question=?, threshold=?,
                       scale_1=?, scale_5=?, enabled=?, category_name=?
                   WHERE id=?""",
                (category, sort_order, question, threshold, scale_1, scale_5, enabled,
                 category_name, id),
            )
            return id
        else:
            cur = conn.execute(
                """INSERT INTO rubric
                   (user_id, category, sort_order, question, threshold, scale_1, scale_5, enabled, category_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, category, sort_order, question, threshold, scale_1, scale_5,
                 enabled, category_name),
            )
            return cur.lastrowid


def delete_rubric_item(id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM rubric WHERE id=?", (id,))


# ──────────────────────────────────────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────────────────────────────────────

def save_verification_code(email: str, code: str) -> None:
    expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        # Invalidate old codes for this email
        conn.execute("UPDATE verification_codes SET used=1 WHERE email=?", (email,))
        conn.execute(
            "INSERT INTO verification_codes (email, code, used) VALUES (?, ?, 0)",
            (email, code),
        )


def check_verification_code(email: str, code: str) -> bool:
    """Return True if code is valid and unused (issued within last 10 minutes)."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id FROM verification_codes
               WHERE email=? AND code=? AND used=0
                 AND created_at > datetime('now', 'localtime', '-10 minutes')
               ORDER BY id DESC LIMIT 1""",
            (email, code),
        ).fetchone()
        if not row:
            return False
        conn.execute("UPDATE verification_codes SET used=1 WHERE id=?", (row["id"],))
        return True


def get_or_create_user(email: str) -> dict:
    """Get existing user or create a new unverified one."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO users (email, email_verified) VALUES (?, 0)",
            (email,),
        )
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row)


def mark_email_verified(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET email_verified=1 WHERE id=?", (user_id,)
        )


def set_password(user_id: int, plain_password: str) -> None:
    hashed = generate_password_hash(plain_password)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?", (hashed, user_id)
        )


def verify_password(email: str, plain_password: str) -> dict | None:
    """Return user dict if credentials are valid, else None."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not row:
        return None
    user = dict(row)
    if not user.get("password_hash"):
        return None
    if not check_password_hash(user["password_hash"], plain_password):
        return None
    return user


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires),
        )
    return token


def get_user_by_token(token: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT u.* FROM users u
               JOIN sessions s ON s.user_id = u.id
               WHERE s.token = ?
                 AND (s.expires_at IS NULL OR s.expires_at > datetime('now', 'localtime'))""",
            (token,),
        ).fetchone()
    return dict(row) if row else None


def delete_session(token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))


def get_user_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def update_user_profile(
    user_id: int,
    name: str,
    gender: str,
    age: int | None,
    institution: str,
    title: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE users
               SET name=?, gender=?, age=?, institution=?, title=?, profile_completed=1
               WHERE id=?""",
            (name, gender, age, institution, title, user_id),
        )


def set_user_tracks(user_id: int, tracks: list[dict]) -> None:
    """Replace user's track selections. tracks = [{"main": ..., "sub": ...}, ...]"""
    with get_conn() as conn:
        conn.execute("DELETE FROM user_tracks WHERE user_id=?", (user_id,))
        for t in tracks:
            conn.execute(
                "INSERT INTO user_tracks (user_id, track_main, track_sub) VALUES (?, ?, ?)",
                (user_id, t["main"], t["sub"]),
            )


def get_user_tracks(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT track_main, track_sub FROM user_tracks WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_keywords(user_id: int) -> list[str]:
    """Return user's custom search keywords (max 10)."""
    import json as _json
    with get_conn() as conn:
        row = conn.execute(
            "SELECT custom_keywords FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not row or not row["custom_keywords"]:
        return []
    try:
        result = _json.loads(row["custom_keywords"])
        return result if isinstance(result, list) else []
    except Exception:
        return []


def set_user_keywords(user_id: int, keywords: list[str]) -> None:
    """Replace user's custom search keywords. Max 10, each max 20 chars."""
    import json as _json
    cleaned = [str(k).strip() for k in keywords if str(k).strip()][:10]
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET custom_keywords = ? WHERE id = ?",
            (_json.dumps(cleaned, ensure_ascii=False), user_id),
        )


def get_all_users_combined_keywords() -> list[str]:
    """
    Collect the union of search keywords across ALL users:
      - Each user's selected track_sub → keywords from TRACK_KEYWORDS
      - Each user's custom_keywords
    Returns a deduplicated list, preserving insertion order.
    Used by batch import so coverage is driven by users, not admin config.
    """
    import json as _json
    from constants import TRACK_KEYWORDS

    seen: set[str] = set()
    result: list[str] = []

    def _add(kw: str) -> None:
        kw = kw.strip()
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)

    with get_conn() as conn:
        track_rows = conn.execute(
            "SELECT DISTINCT track_main, track_sub FROM user_tracks"
        ).fetchall()
        kw_rows = conn.execute(
            "SELECT custom_keywords FROM users WHERE custom_keywords IS NOT NULL AND custom_keywords != ''"
        ).fetchall()

    # Track-based keywords
    for row in track_rows:
        kws = (
            TRACK_KEYWORDS.get(row["track_main"], {}).get(row["track_sub"])
            or TRACK_KEYWORDS.get(row["track_main"], {}).get(row["track_sub"].strip())
        )
        if kws:
            for kw in kws:
                _add(kw)
        else:
            _add(row["track_sub"])  # fallback: use sub-track name directly

    # Custom keywords from all users
    for row in kw_rows:
        try:
            custom = _json.loads(row["custom_keywords"] or "[]")
            for kw in custom:
                _add(str(kw))
        except Exception:
            pass

    return result


def list_all_users() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, email, name, institution, title, is_admin, profile_completed, created_at"
            " FROM users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────────────────────────
# SCAN-ROUND TRACKING  (used by Layer B expiry + P2 revival)
# ──────────────────────────────────────────────────────────────────────────────

def get_scan_count(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT scan_count FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return int(row["scan_count"] or 0) if row else 0


def increment_scan_count(user_id: int) -> int:
    """Bump scan_count by 1 and return the new value."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET scan_count = COALESCE(scan_count, 0) + 1 WHERE id = ?",
            (user_id,),
        )
        row = conn.execute(
            "SELECT scan_count FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return int(row["scan_count"]) if row else 1


# ──────────────────────────────────────────────────────────────────────────────
# COMPANIES
# ──────────────────────────────────────────────────────────────────────────────

# Keywords that signal the admin manually approved an out-of-window post
_TIME_OVERRIDE_KEYWORDS = ["仍在持续涨", "互动仍在增长", "持续热度", "纳入", "仍活跃", "超出窗口"]


def _parse_publish_date(date_str: str) -> datetime | None:
    """Parse '2026年4月4日（...）' → datetime, or None if unrecognised."""
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str or "")
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def _has_time_override(date_str: str) -> bool:
    """Return True if the date string contains an admin override note."""
    s = date_str or ""
    return any(kw in s for kw in _TIME_OVERRIDE_KEYWORDS)


def _company_matches_layer_b(company: dict, layer_b_keywords: list[str]) -> bool:
    """Return True if any active Layer B keyword appears in the company's text fields."""
    text = " ".join([
        company.get("name", ""),
        company.get("summary", ""),
        company.get("mfv_keywords", ""),
        company.get("type", ""),
        company.get("one_liner", ""),
    ]).lower()
    return any(kw.lower() in text for kw in layer_b_keywords)


def _build_user_layer_a_keywords(user_id: int) -> list[str]:
    """
    Build the full Layer A keyword set for a user:
    track-based keywords (from TRACK_KEYWORDS) + custom keywords.
    Returns [] if the user has no tracks AND no custom keywords
    (meaning no filter should be applied).
    """
    from constants import TRACK_KEYWORDS

    result: list[str] = []
    seen: set[str] = set()

    def _add(kw: str) -> None:
        kw = kw.strip()
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)

    # Track-based keywords
    tracks = get_user_tracks(user_id)
    for t in tracks:
        kws = (
            TRACK_KEYWORDS.get(t["track_main"], {}).get(t["track_sub"])
            or TRACK_KEYWORDS.get(t["track_main"], {}).get(t["track_sub"].strip())
        )
        if kws:
            for kw in kws:
                _add(kw)
        else:
            _add(t["track_sub"])  # fallback: use sub-track name as keyword

    # Custom keywords
    for kw in get_user_keywords(user_id):
        _add(kw)

    return result


def _company_matches_layer_a(company: dict, layer_a_keywords: list[str]) -> bool:
    """Return True if any Layer A keyword appears in the company's text fields."""
    text = " ".join([
        company.get("name", ""),
        company.get("type", ""),
        company.get("summary", ""),
        company.get("mfv_keywords", ""),
        company.get("one_liner", ""),
    ]).lower()
    return any(kw.lower() in text for kw in layer_a_keywords)


def get_companies(user_id: int | None = None, apply_time_filter: bool = False) -> list[dict]:
    """
    Return companies for the feed:
    1. Unseen companies (not yet swiped by this user).
    2. Revival candidates: most-recent swipe was a left-swipe >= 3 scan rounds ago.
    3. Layer B soft filter: exclude companies matching active A-type rejection keywords.
    If apply_time_filter=True, also exclude posts older than 7 days unless
    the admin has marked them with an override note in publish_date.
    """
    with get_conn() as conn:
        if user_id:
            # — Unseen companies —
            rows = conn.execute(
                """SELECT * FROM companies
                   WHERE id NOT IN (
                       SELECT company_id FROM swipes WHERE user_id = ?
                   )
                   ORDER BY id""",
                (user_id,),
            ).fetchall()
            companies = [dict(r) for r in rows]

            # — Revival candidates —
            # The most recent swipe for this company (by this user) must be
            # a left-swipe that happened >= 3 scan rounds ago.
            current_scan = get_scan_count(user_id)
            revival_rows = conn.execute(
                """SELECT c.*, s.note AS rejection_note
                   FROM companies c
                   JOIN swipes s ON c.id = s.company_id
                   WHERE s.user_id = ?
                     AND s.direction = 'left'
                     AND s.rejected_at_scan IS NOT NULL
                     AND (? - s.rejected_at_scan) >= 3
                     AND s.id = (
                         SELECT MAX(id) FROM swipes
                         WHERE company_id = c.id AND user_id = ?
                     )
                   ORDER BY c.id""",
                (user_id, current_scan, user_id),
            ).fetchall()

            already_ids = {c["id"] for c in companies}
            for row in revival_rows:
                c = dict(row)
                if c["id"] in already_ids:
                    continue  # shouldn't happen, but be safe
                c["is_revival"] = 1
                c["previous_rejection"] = c.pop("rejection_note", "") or ""
                companies.append(c)
        else:
            rows = conn.execute("SELECT * FROM companies ORDER BY id").fetchall()
            companies = [dict(r) for r in rows]

    if apply_time_filter:
        cutoff = datetime.now() - timedelta(days=7)
        filtered = []
        for c in companies:
            pub = _parse_publish_date(c.get("publish_date", ""))
            if pub is None or pub >= cutoff or _has_time_override(c.get("publish_date", "")):
                filtered.append(c)
        companies = filtered

    # Layer A: only show companies matching user's track + custom keywords
    # Skip if user has no keywords configured (show everything as fallback)
    if user_id:
        layer_a_kws = _build_user_layer_a_keywords(user_id)
        if layer_a_kws:
            unseen = [c for c in companies if not c.get("is_revival")]
            revivals = [c for c in companies if c.get("is_revival")]
            companies = [c for c in unseen if _company_matches_layer_a(c, layer_a_kws)]
            # Revivals also go through Layer A — no point surfacing irrelevant ones
            companies += [c for c in revivals if _company_matches_layer_a(c, layer_a_kws)]

    # Layer B: soft filter — exclude companies matching active A-type rejection keywords
    if user_id:
        current_scan = get_scan_count(user_id)
        layer_b_kws = get_active_layer_b_keywords(user_id, current_scan)
        if layer_b_kws:
            companies = [c for c in companies if not _company_matches_layer_b(c, layer_b_kws)]

    return companies


def get_company(company_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        return dict(row) if row else None


def check_duplicate_company(account: str, xhs_url: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE account = ? OR xhs_url = ?",
            (account, xhs_url),
        ).fetchone()
        return dict(row) if row else None


def update_company_revival(company_id: int, is_revival: int, previous_rejection: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE companies SET is_revival = ?, previous_rejection = ? WHERE id = ?",
            (is_revival, previous_rejection, company_id),
        )


def upsert_company(data: dict) -> None:
    account = data.get("account", "")
    xhs_url = data.get("xhs_url", "")
    existing = check_duplicate_company(account, xhs_url)

    if existing:
        with get_conn() as conn:
            swipe_row = conn.execute(
                "SELECT direction FROM swipes WHERE company_id = ? ORDER BY swiped_at DESC LIMIT 1",
                (existing["id"],),
            ).fetchone()
        if swipe_row and swipe_row["direction"] == "left":
            data["is_revival"] = 1
            data["previous_rejection"] = existing.get("previous_rejection") or ""
        elif swipe_row and swipe_row["direction"] == "right":
            return

    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO companies
                (id, name, account, type, publish_date, one_liner, summary,
                 mfv_keywords, mfv_note, xhs_url, xhs_user_id, batch_date,
                 is_revival, previous_rejection,
                 score_origin, score_amplification, score_gravity, viability_summary)
            VALUES
                (:id, :name, :account, :type, :publish_date, :one_liner, :summary,
                 :mfv_keywords, :mfv_note, :xhs_url, :xhs_user_id, :batch_date,
                 :is_revival, :previous_rejection,
                 :score_origin, :score_amplification, :score_gravity, :viability_summary)
        """, {
            **data,
            "is_revival": data.get("is_revival", 0),
            "previous_rejection": data.get("previous_rejection", None),
            "score_origin": data.get("score_origin", None),
            "score_amplification": data.get("score_amplification", None),
            "score_gravity": data.get("score_gravity", None),
            "viability_summary": data.get("viability_summary", None),
        })


# ──────────────────────────────────────────────────────────────────────────────
# SWIPES
# ──────────────────────────────────────────────────────────────────────────────

def record_swipe(
    company_id: int,
    direction: str,
    note: str,
    dm_text: str,
    user_id: int | None = None,
    shown_at: str | None = None,
    decided_at: str | None = None,
    rejected_at_scan: int | None = None,
) -> int:
    contact_status = "rejected" if direction == "left" else "pending"
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO swipes
               (company_id, direction, note, dm_text, contact_status, user_id,
                shown_at, decided_at, rejected_at_scan)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_id, direction, note or "", dm_text or "", contact_status,
             user_id, shown_at, decided_at, rejected_at_scan),
        )
        return cur.lastrowid


def update_swipe_status(swipe_id: int, status: str) -> None:
    valid = {"rejected", "pending", "contacted", "replied", "in_process"}
    if status not in valid:
        raise ValueError(f"Invalid status: {status}")
    with get_conn() as conn:
        conn.execute(
            "UPDATE swipes SET contact_status = ? WHERE id = ?", (status, swipe_id)
        )


# ──────────────────────────────────────────────────────────────────────────────
# LLM RESULTS — write-back helpers
# ──────────────────────────────────────────────────────────────────────────────

def update_swipe_llm_fields(swipe_id: int, result: dict) -> None:
    """Write LLM classification results back into the swipe row."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE swipes SET
               rejection_type = ?,
               extracted_keyword = ?,
               expiry_type = ?,
               expiry_after_scans = ?
               WHERE id = ?""",
            (
                result.get("rejection_type"),
                result.get("extracted_keyword"),
                result.get("expiry_type"),
                result.get("expiry_after_scans"),
                swipe_id,
            ),
        )


def save_pass_keywords(user_id: int, company_id: int, keywords: list[str]) -> None:
    """Store keywords extracted from a right-swiped company (Layer A tracking)."""
    with get_conn() as conn:
        # Avoid duplicates for same user+company
        conn.execute(
            "DELETE FROM pass_keywords WHERE user_id = ? AND company_id = ?",
            (user_id, company_id),
        )
        for kw in keywords:
            conn.execute(
                "INSERT INTO pass_keywords (user_id, company_id, keyword) VALUES (?, ?, ?)",
                (user_id, company_id, kw),
            )


def get_active_layer_b_keywords(user_id: int, current_scan: int) -> list[str]:
    """
    Return active A-type rejection keywords for this user.
    Expired keywords (based on expiry_after_scans) are excluded.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT extracted_keyword, expiry_type, expiry_after_scans, rejected_at_scan
               FROM swipes
               WHERE user_id = ?
                 AND direction = 'left'
                 AND rejection_type = 'A'
                 AND extracted_keyword IS NOT NULL
                 AND extracted_keyword != ''""",
            (user_id,),
        ).fetchall()

    active: list[str] = []
    for row in rows:
        kw = row["extracted_keyword"]
        et = row["expiry_type"]
        eas = row["expiry_after_scans"]
        rat = row["rejected_at_scan"]

        if et == "permanent":
            active.append(kw)
        elif et in ("trend", "temporary") and eas and rat is not None:
            if (current_scan - rat) < eas:
                active.append(kw)
        # If no expiry data, treat as permanent
        elif et is None and eas is None:
            active.append(kw)

    # Deduplicate
    return list(dict.fromkeys(active))


def get_b2_suggestion(user_id: int, threshold: int = 5) -> str | None:
    """
    Check if any B2 rejection keyword has accumulated >= threshold rejections.
    Returns the keyword if so (for frontend toast suggestion), else None.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT extracted_keyword, COUNT(*) as cnt
               FROM swipes
               WHERE user_id = ?
                 AND direction = 'left'
                 AND rejection_type = 'B2'
                 AND extracted_keyword IS NOT NULL
                 AND extracted_keyword != ''
               GROUP BY extracted_keyword
               HAVING cnt >= ?
               ORDER BY cnt DESC
               LIMIT 1""",
            (user_id, threshold),
        ).fetchall()
    return rows[0]["extracted_keyword"] if rows else None


def get_history(user_id: int | None = None, is_admin: bool = False) -> list[dict]:
    """Admin sees all swipes; regular users see only their own."""
    with get_conn() as conn:
        if is_admin:
            where = ""
            params: tuple = ()
        elif user_id is not None:
            # Show own swipes + legacy swipes without user_id (pre-auth era)
            where = "WHERE (s.user_id = ? OR s.user_id IS NULL)"
            params = (user_id,)
        else:
            where = ""
            params = ()

        rows = conn.execute(f"""
            SELECT
                s.id, s.company_id, s.direction, s.note, s.dm_text, s.swiped_at,
                s.contact_status, s.user_id,
                c.name, c.account, c.type, c.publish_date, c.one_liner,
                c.summary, c.mfv_keywords, c.mfv_note, c.xhs_url,
                c.is_revival, c.previous_rejection,
                c.score_origin, c.score_amplification, c.score_gravity, c.viability_summary,
                u.name as reviewer_name
            FROM swipes s
            JOIN companies c ON s.company_id = c.id
            LEFT JOIN users u ON s.user_id = u.id
            {where}
            ORDER BY s.swiped_at DESC
        """, params).fetchall()
        return [dict(r) for r in rows]
