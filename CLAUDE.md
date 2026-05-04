# MFV Deal Flow（基于 xiaohongshu-skills）

小红书 AI 创业项目筛选工具。在用户真实浏览器中操作小红书，结合 LLM 评分帮助投资人发现优质标的。

---

## 🗂 双仓库结构（重要）

本机有两份目录，**只在 internal 里开发**，永不直接编辑 public：

```
~/Desktop/
├── xiaohongshu-skills-main/         ← internal 开发版（有 .env、mfv.db、真实数据）
│   ├── dev 分支    = 开发中
│   └── main 分支   = 内部验收
│
└── xiaohongshu-skills-public/       ← public GitHub 镜像（脱敏，git@github.com:TinaDu-AI/dealflow.git）
    └── main 分支   = 公开验收
```

**同步流程：** `internal/dev` → 合并到 `internal/main` → 跑 `./sync-public.sh "说明"` → 自动剔除敏感文件 → 推到 GitHub。

---

## 📋 三份状态文档（每次开发后必须更新）

- `MFV-Deal-Flow-开发状态.md` — 描述 dev 分支当前在改什么、还有什么没改完
- `MFV-Deal-Flow-验收状态.md` — 描述 main 分支当前稳定功能（合并到 main 时同步更新）
- `MFV-Deal-Flow-需求看板.md` — 所有需求/Bug 留痕（"版本腐烂"防护）

> 少云原话："版本腐烂绝对不允许 — 所有需求都要提单留痕"

---

## ✅ 提交约定（每完成一项功能必须走完）

1. 改完代码 → `git commit` + `git push`
2. **更新 `MFV-Deal-Flow-开发状态.md`**：在变更日志写一句"这次改了啥"
3. 如果是修 Bug 或完成需求 → 移到 `MFV-Deal-Flow-需求看板.md` 的"已完成"区，填 commit hash
4. 重大节点 → 切到 main 分支 merge dev → 更新 `MFV-Deal-Flow-验收状态.md` → 跑 `./sync-public.sh`

---

## 🧪 实验规范（涉及 LLM 的修改必须遵守）

参考少云方法论：

1. **禁止重写**：实验过程**严禁**为了实验重写生产函数，必须直接调用生产代码
2. **控制变量法**：每次实验只改一个变量（prompt / 模型 / 参数三选一），其余保持不变
3. **结果可视化、可回溯**：实验脚本放在 `experiments/<编号>-<主题>/`，输出 `report.html` 或 `results.json`
4. **新旧对比**：每次实验产出"优化前 vs 优化后"的对比报告，写入 `experiments/README.md` 索引

---

## Git 分支约定

- `main` = 验收版（不直接提交，只接受 dev merge）
- `dev` = 默认开发分支
- `feature/xxx` = 大功能（开新分支，最后合 dev）
- `fix/xxx` = 修 Bug
- `exp/xxx` = 实验性改动（可能丢弃）

## 开发命令

```bash
uv sync                    # 安装依赖
uv run ruff check .        # Lint 检查
uv run ruff format .       # 代码格式化
uv run pytest              # 运行测试
```

## 架构

双层结构：`scripts/` 是 Python 自动化引擎，`skills/` 是 Claude Code Skills 定义（SKILL.md 格式）。

- `scripts/xhs/` — 核心自动化库（模块化，每个功能一个文件）
- `scripts/cli.py` — 统一 CLI 入口，JSON 结构化输出，自动启动 bridge server 和浏览器
- `scripts/bridge_server.py` — 本地通信服务（连接 CLI 与浏览器扩展）
- `extension/` — Chrome 扩展，在用户的真实浏览器中执行操作
- `skills/*/SKILL.md` — 指导 Claude 如何调用 scripts/

### 调用方式

```bash
python scripts/cli.py check-login
python scripts/cli.py search-feeds --keyword "关键词"
python scripts/cli.py publish --title-file t.txt --content-file c.txt --images pic.jpg
```

> CLI 会自动检测环境，若浏览器未打开也会自动启动 Chrome。

## 代码规范

- 行长度上限 100 字符
- 完整 type hints，使用 `from __future__ import annotations`
- 异常继承 `XHSError`（`xhs/errors.py`）
- CLI exit code：0=成功，1=未登录，2=错误
- 用户可见错误信息使用中文
- JSON 输出 `ensure_ascii=False`

### 安全约束

- 发布类操作必须有用户确认机制
- 文件路径必须使用绝对路径
- 敏感内容通过文件传递，不内联到命令行参数

## CLI 子命令对照表

| CLI 子命令 | 对应 MCP 工具 | 分类 |
|--|--|--|
| `check-login` | check_login_status | 认证 |
| `login` | get_login_qrcode | 认证 |
| `phone-login` | — | 认证 |
| `delete-cookies` | delete_cookies | 认证 |
| `list-feeds` | list_feeds | 浏览 |
| `search-feeds` | search_feeds | 浏览 |
| `get-feed-detail` | get_feed_detail | 浏览 |
| `user-profile` | user_profile | 浏览 |
| `post-comment` | post_comment_to_feed | 互动 |
| `reply-comment` | reply_comment_in_feed | 互动 |
| `like-feed` | like_feed | 互动 |
| `favorite-feed` | favorite_feed | 互动 |
| `publish` | publish_content | 发布 |
| `publish-video` | publish_with_video | 发布 |
| `fill-publish` | — | 分步发布（图文填写） |
| `fill-publish-video` | — | 分步发布（视频填写） |
| `click-publish` | — | 分步发布（点击发布） |
| `long-article` | — | 长文发布（填写+排版） |
| `select-template` | — | 长文发布（选择模板） |
| `next-step` | — | 长文发布（下一步+描述） |
