# MFV Deal Flow

小红书 AI 创业项目自动筛选工具。通过小红书搜索 AI 创业相关内容，结合 LLM 对项目进行 Rubric 评分，帮助投资人快速发现优质标的。

## 功能

- 🔍 **批量搜索** — 按关键词自动抓取小红书内容，记录来源关键词与互动数据
- 🤖 **AI 评分** — 基于自定义 Rubric 对项目进行多维度打分（创意 / 管线 / 引力）
- 📋 **项目管理** — 滑动卡片筛选，右滑发送私信话术，左滑跳过
- 🧠 **拒绝/通过智能** — 左滑后 LLM 自动分类（类型不感兴趣 / 评分维度不达标 / 其他偏好）；右滑提取关键词回流偏好；同类项目 N 轮内不重复出现
- ♻️ **起死回生** — 左滑后 3 轮冷却，符合条件的项目重新入队
- 📊 **数据看板**（管理员）— 全 pipeline 视图（抓取 / 抽取 / 评分 / 推送 / Swipe），手机优先 UI，5 个阶段反馈槽；话术修改字符级 diff
- 🔄 **Notion 自动同步** — 每天定时把数据看板同步到 Notion 页面，也支持手动触发
- 📜 **历史记录** — 查看所有处理过的项目，支持详情查看和补充联系
- 👤 **多用户** — 支持邀请注册，每人独立偏好设置

## 技术架构

```
webapp/          # Flask 后端 + 单页前端
scripts/         # 小红书自动化引擎（Chrome 扩展桥接）
extension/       # Chrome 扩展（在真实浏览器中执行操作）
```

## 快速开始

### 前置条件

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) 包管理器
- Google Chrome 浏览器
- 阿里云百炼 API Key（Qwen 模型，用于 LLM 评分）
- 163 邮箱 SMTP 授权码（用于发送验证码）

### 安装

```bash
git clone https://github.com/TinaDu-AI/dealflow.git
cd dealflow
uv sync
```

### 配置

```bash
cp webapp/.env.example webapp/.env
# 编辑 .env，填入真实值
```

`.env` 必填项：

```
ADMIN_EMAIL=your-admin@example.com
ADMIN_PHONE=138xxxxxxxx
SMTP_USER=your-account@163.com
SMTP_PASS=your-163-auth-code
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

可选项（Notion 同步）：

```
NOTION_API_KEY=secret_xxx                 # Notion integration token
NOTION_DASHBOARD_PAGE_ID=xxxxxxxx         # 接收同步的目标页面 ID
CRON_SECRET=<random>                      # 定时同步用的 X-Cron-Secret 鉴权值
```

### 安装 Chrome 扩展

1. 打开 Chrome，地址栏输入 `chrome://extensions/`
2. 右上角开启**开发者模式**
3. 点击**加载已解压的扩展程序**，选择 `extension/` 目录

### 启动

```bash
no_proxy=localhost,127.0.0.1 uv run python webapp/server.py
```

浏览器访问 `http://localhost:5173`，用 `.env` 中配置的管理员邮箱注册登录。

## 开发

```bash
uv sync                    # 安装依赖
uv run ruff check .        # Lint 检查
uv run ruff format .       # 代码格式化
uv run pytest              # 运行测试
```

## Credits

小红书自动化引擎（`scripts/` 和 `extension/`）基于 [xiaohongshu-skills](https://github.com/autoclaw-cc/xiaohongshu-skills) 开发，MIT License。

## License

MIT
