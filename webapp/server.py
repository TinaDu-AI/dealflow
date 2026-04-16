from __future__ import annotations

import sys
from pathlib import Path

# ensure webapp/ is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))

import batch_import
import db
import email_service
import llm_service
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="/static")

DM_TEMPLATE = (
    "你好！我是 Magic Find Ventures（MFV）的投资经理，"
    "我们专注于 AI 原生游戏和娱乐赛道的早期投资。\n"
    "\n"
    "在小红书上看到了{account}关于{name}的分享，{custom_line}\n"
    "\n"
    "MFV目前关注的方向和你们高度重合："
    "AI原生叙事体验、创作者工具基建、以及那些因为AI才真正成立的新游戏品类。\n"
    "\n"
    "如果方便的话，很想找个时间深聊一下，了解你们目前的阶段和规划。期待回复！🙏"
)


def build_dm(company: dict) -> str:
    note = company.get("mfv_note", "")
    one_liner = company.get("one_liner", "")
    first_note_sentence = note.split("。")[0] + "。" if "。" in note else note
    custom_line = f"{one_liner}的方向让我们很感兴趣——{first_note_sentence}"
    return DM_TEMPLATE.format(
        account=company["account"],
        name=company["name"],
        custom_line=custom_line,
    )


def get_current_user() -> dict | None:
    """Extract user from Bearer token in Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    return db.get_user_by_token(token)


def require_auth():
    """Return (user, error_response). If error_response is not None, return it immediately."""
    user = get_current_user()
    if not user:
        return None, (jsonify({"error": "未登录"}), 401)
    return user, None


def require_admin():
    user = get_current_user()
    if not user or not user.get("is_admin"):
        return None, (jsonify({"error": "无权限"}), 403)
    return user, None


# ──────────────────────────────────────────────────────────────────────────────
# STATIC
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ──────────────────────────────────────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/auth/send-code", methods=["POST"])
def api_send_code():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "请输入有效的邮箱地址"}), 400
    code = email_service.generate_code()
    db.save_verification_code(email, code)
    try:
        email_service.send_verification_code(email, code)
    except Exception as e:
        print(f"[email error] {e}")
        if email_service.SMTP_USER:
            return jsonify({"error": "验证码发送失败，邮件服务暂时不可用，请稍后重试"}), 503
    return jsonify({"ok": True, "console_mode": email_service.CONSOLE_MODE})


@app.route("/api/auth/verify-code", methods=["POST"])
def api_verify_code():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    if not email or not code:
        return jsonify({"error": "参数缺失"}), 400
    if not db.check_verification_code(email, code):
        return jsonify({"error": "验证码错误或已过期"}), 400
    user = db.get_or_create_user(email)
    db.mark_email_verified(user["id"])
    token = db.create_session(user["id"])
    user = db.get_user_by_id(user["id"])
    return jsonify({"ok": True, "token": token, "user": _safe_user(user)})


@app.route("/api/auth/set-password", methods=["POST"])
def api_set_password():
    user, err = require_auth()
    if err:
        return err
    data = request.get_json(force=True)
    password = data.get("password", "")
    if len(password) < 6:
        return jsonify({"error": "密码至少 6 位"}), 400
    db.set_password(user["id"], password)
    return jsonify({"ok": True})


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")
    user = db.verify_password(email, password)
    if not user:
        return jsonify({"error": "邮箱或密码错误"}), 401
    token = db.create_session(user["id"])
    return jsonify({"ok": True, "token": token, "user": _safe_user(user)})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        db.delete_session(auth[7:])
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def api_me():
    user = get_current_user()
    if not user:
        return jsonify({"error": "未登录"}), 401
    tracks = db.get_user_tracks(user["id"])
    return jsonify({**_safe_user(user), "tracks": tracks})


@app.route("/api/auth/profile", methods=["PUT"])
def api_update_profile():
    user, err = require_auth()
    if err:
        return err
    data = request.get_json(force=True)
    db.update_user_profile(
        user["id"],
        name=data.get("name", ""),
        gender=data.get("gender", ""),
        age=data.get("age"),
        institution=data.get("institution", ""),
        title=data.get("title", ""),
    )
    return jsonify({"ok": True})


@app.route("/api/auth/tracks", methods=["GET"])
def api_get_tracks():
    user, err = require_auth()
    if err:
        return err
    tracks = db.get_user_tracks(user["id"])
    return jsonify({"tracks": tracks})


@app.route("/api/auth/tracks", methods=["PUT"])
def api_update_tracks():
    user, err = require_auth()
    if err:
        return err
    data = request.get_json(force=True)
    tracks = data.get("tracks", [])
    if not isinstance(tracks, list):
        return jsonify({"error": "invalid tracks"}), 400
    db.set_user_tracks(user["id"], tracks)
    return jsonify({"ok": True})


@app.route("/api/user/keywords", methods=["GET"])
def api_get_user_keywords():
    user = get_current_user()
    if not user:
        return jsonify({"keywords": []})
    return jsonify({"keywords": db.get_user_keywords(user["id"])})


@app.route("/api/user/keywords", methods=["PUT"])
def api_update_user_keywords():
    user, err = require_auth()
    if err:
        return err
    data = request.get_json(force=True)
    keywords = data.get("keywords", [])
    if not isinstance(keywords, list):
        return jsonify({"error": "invalid"}), 400
    cleaned = [str(k).strip() for k in keywords if str(k).strip()][:10]
    db.set_user_keywords(user["id"], cleaned)
    return jsonify({"ok": True, "keywords": cleaned})


def _safe_user(user: dict) -> dict:
    """Return user dict safe to send to client (no password hash)."""
    return {k: v for k, v in user.items() if k != "password_hash"}


# ──────────────────────────────────────────────────────────────────────────────
# COMPANIES
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/companies")
def api_companies():
    user = get_current_user()
    user_id = user["id"] if user else None

    # Layer D: check if user has the time-window exclusion item enabled
    apply_time_filter = False
    if user_id:
        rubric = db.get_rubric(user_id=user_id)
        for item in rubric.get("exclusion", []):
            if "发布时间" in (item.get("question") or "") and item.get("enabled"):
                apply_time_filter = True
                break
        # P2: each feed load = one scan round
        db.increment_scan_count(user_id)

    companies = db.get_companies(user_id=user_id, apply_time_filter=apply_time_filter)
    return jsonify(companies)


# ──────────────────────────────────────────────────────────────────────────────
# SWIPES
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/swipe", methods=["POST"])
def api_swipe():
    data = request.get_json(force=True)
    company_id = data.get("company_id")
    direction = data.get("direction")
    note = data.get("note", "")
    dm_text = data.get("dm_text", "")
    if not company_id or direction not in ("left", "right"):
        return jsonify({"error": "invalid payload"}), 400
    user = get_current_user()
    user_id = user["id"] if user else None
    shown_at = data.get("shown_at") or None
    decided_at = data.get("decided_at") or None
    # P2: record current scan round at rejection so revival can count 3 rounds later
    rejected_at_scan = db.get_scan_count(user_id) if user_id and direction == "left" else None
    swipe_id = db.record_swipe(
        company_id, direction, note, dm_text, user_id, shown_at, decided_at, rejected_at_scan
    )

    company = db.get_company(company_id) or {}

    if direction == "left" and user_id:
        # P1 Task 1&2: async LLM rejection classification → Layer B write-back
        llm_service.classify_rejection_async(
            swipe_id, company, note or "",
            on_done=db.update_swipe_llm_fields,
        )

    if direction == "right" and user_id:
        # P1 Task 4: async keyword extraction for Layer A tracking
        llm_service.extract_keywords_async(
            swipe_id, company,
            on_done=lambda sid, kws: db.save_pass_keywords(user_id, company_id, kws),
        )

    # P1 Task 5: B2 ≥5 → suggest adding to exclusion criteria
    suggest_exclusion = None
    if direction == "left" and user_id:
        suggest_exclusion = db.get_b2_suggestion(user_id)

    return jsonify({"ok": True, "swipe_id": swipe_id, "suggest_exclusion": suggest_exclusion})


@app.route("/api/swipe/<int:swipe_id>/status", methods=["PUT"])
def api_swipe_status(swipe_id: int):
    data = request.get_json(force=True)
    status = data.get("status")
    valid_statuses = {"rejected", "pending", "contacted", "replied", "in_process"}
    if status not in valid_statuses:
        return jsonify({"error": "invalid status"}), 400
    db.update_swipe_status(swipe_id, status)
    return jsonify({"ok": True})


@app.route("/api/history")
def api_history():
    user = get_current_user()
    if user and user.get("is_admin"):
        history = db.get_history(is_admin=True)
    elif user:
        history = db.get_history(user_id=user["id"])
    else:
        history = db.get_history()
    return jsonify(history)


# ──────────────────────────────────────────────────────────────────────────────
# DM
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/dm/<int:company_id>")
def api_dm(company_id: int):
    company = db.get_company(company_id)
    if not company:
        return jsonify({"error": "not found"}), 404
    dm = build_dm(company)
    return jsonify({"dm_text": dm, "xhs_url": company["xhs_url"]})


# ──────────────────────────────────────────────────────────────────────────────
# RUBRIC (per-user)
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/rubric", methods=["GET"])
def api_rubric_get():
    user = get_current_user()
    if user:
        db.ensure_user_rubric(user["id"])
        return jsonify(db.get_rubric(user["id"]))
    return jsonify(db.get_rubric(None))


@app.route("/api/rubric", methods=["POST"])
def api_rubric_create():
    user = get_current_user()
    data = request.get_json(force=True)
    category = data.get("category", "exclusion")
    sort_order = data.get("sort_order", 0)
    question = data.get("question", "新问题")
    threshold = data.get("threshold")
    scale_1 = data.get("scale_1")
    scale_5 = data.get("scale_5")
    enabled = data.get("enabled", 1)
    category_name = data.get("category_name")
    user_id = user["id"] if user else None
    new_id = db.upsert_rubric_item(
        None, category, sort_order, question, threshold, scale_1, scale_5, enabled,
        user_id, category_name=category_name,
    )
    return jsonify({"ok": True, "id": new_id})


@app.route("/api/rubric/<int:item_id>", methods=["PUT"])
def api_rubric_update(item_id: int):
    data = request.get_json(force=True)
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM rubric WHERE id=?", (item_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    current = dict(row)
    category = data.get("category", current["category"])
    sort_order = data.get("sort_order", current["sort_order"])
    question = data.get("question", current["question"])
    threshold = data.get("threshold", current["threshold"])
    scale_1 = data.get("scale_1", current["scale_1"])
    scale_5 = data.get("scale_5", current["scale_5"])
    enabled = data.get("enabled", current["enabled"])
    category_name = data.get("category_name", current.get("category_name"))
    db.upsert_rubric_item(
        item_id, category, sort_order, question, threshold, scale_1, scale_5, enabled,
        category_name=category_name,
    )
    return jsonify({"ok": True})


@app.route("/api/rubric/<int:item_id>", methods=["DELETE"])
def api_rubric_delete(item_id: int):
    db.delete_rubric_item(item_id)
    return jsonify({"ok": True})


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/admin/users")
def api_admin_users():
    user, err = require_admin()
    if err:
        return err
    users = db.list_all_users()
    return jsonify(users)


@app.route("/api/admin/batch-import", methods=["POST"])
def api_batch_import_start():
    user, err = require_admin()
    if err:
        return err
    data = request.get_json(force=True)
    keywords = data.get("keywords") or []
    max_per_keyword = int(data.get("max_per_keyword", 8))

    # If no keywords provided, collect from all users' selected tracks
    if not keywords:
        keywords = db.get_all_users_combined_keywords()

    if not keywords:
        return jsonify({"error": "no keywords — no users have selected tracks yet"}), 400

    institution_name = (user.get("institution") or "MFV").strip() or "MFV"
    job_id = batch_import.start_job(
        keywords,
        max_per_keyword=max_per_keyword,
        institution_name=institution_name,
        user_id=user.get("id"),
    )
    return jsonify({"ok": True, "job_id": job_id, "total_keywords": len(keywords)})


@app.route("/api/admin/batch-import/<job_id>")
def api_batch_import_status(job_id: str):
    user, err = require_admin()
    if err:
        return err
    job = batch_import.get_job(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job)


@app.route("/api/admin/batch-import-jobs")
def api_batch_import_jobs():
    user, err = require_admin()
    if err:
        return err
    return jsonify(batch_import.list_jobs())


# ──────────────────────────────────────────────────────────────────────────────
# BOOT
# ──────────────────────────────────────────────────────────────────────────────

def _warmup_cli_pyc() -> None:
    """
    Pre-compile venv site-packages pyc files in the server's process context.
    The server is launched from Terminal (full Desktop TCC), so this subprocess
    can compile .pyc files in ~/Desktop/... without TCC restrictions.
    Runs once in a background thread at startup.
    """
    import os
    import subprocess
    from pathlib import Path

    project_root = Path(__file__).parent.parent
    # Prefer the external venv (not in iCloud-synced Desktop) for fast imports
    external_venv = Path.home() / ".local" / "share" / "xhs-venv"
    if external_venv.exists():
        venv_python = external_venv / "bin" / "python"
        venv_site = external_venv / "lib" / "python3.11" / "site-packages"
    else:
        venv_python = project_root / ".venv" / "bin" / "python"
        venv_site = project_root / ".venv" / "lib" / "python3.11" / "site-packages"

    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        env.pop(k, None)
    env["no_proxy"] = "localhost,127.0.0.1"
    env["NO_PROXY"] = "localhost,127.0.0.1"

    try:
        subprocess.run(
            [str(venv_python), "-m", "compileall", str(venv_site), "-q"],
            env=env,
            cwd=str(project_root),
            timeout=300,
            capture_output=True,
        )
        print("[warmup] venv pyc compilation complete")
    except Exception as e:
        print(f"[warmup] pyc compilation error (non-fatal): {e}")


if __name__ == "__main__":
    import os
    import threading

    port = int(os.environ.get("FLASK_PORT", 5173))
    db.init_db()
    threading.Thread(target=_warmup_cli_pyc, daemon=True, name="pyc-warmup").start()
    print(f"MFV Deal Flow server starting at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

