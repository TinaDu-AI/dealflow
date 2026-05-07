# MFV Deal Flow — 验收状态

> 这份文档描述 **main 分支**的当前稳定状态。  
> 每次从 dev 合并到 main 时同步更新此文件。

## 当前版本

- **版本号**：v1.1.0
- **最后更新**：2026-05-07
- **管理员账号**：通过 `webapp/.env` 中 `ADMIN_EMAIL` / `ADMIN_PHONE` 配置

## 已上线功能

### 用户系统
- 邮箱验证码注册/登录（163 SMTP）
- 邀请码机制
- 管理员角色（首次启动自动创建）

### 项目筛选（核心）
- 卡片滑动 UI（左滑跳过 / 右滑发私信）
- 自定义关键词管理
- 赛道（Track）配置
- LLM 评分（Rubric 三维度：创意 / 管线 / 引力）
- 起死回生逻辑（左滑 3 轮冷却后重新入队）

### 批量导入
- 通过 Chrome 扩展抓取小红书内容
- LLM 评分 pipeline 自动跑分
- 进度实时反馈
- 记录每条公司的来源关键词 + XHS 互动数据（点赞/评论/收藏）

### 拒绝智能（左滑后异步处理）
- LLM 自动分类拒绝原因（类型不感兴趣 / 评分维度不达标 / 其他偏好）
- 关键词提取 + 软排除（同类项目 N 轮内不再出现）

### 通过反馈（右滑后异步处理）
- LLM 自动抽取内容关键词，回流到 Layer A 跟踪表
- 联系话术：LLM 原版与用户最终发送版双存档

### 数据看板（管理员专属）
- 全 pipeline 数据视图：抓取 / 抽取 / 评分 / 推送 / Swipe 五段
- KPI 横条 + 距实验门槛进度条（50 swipe + 20 带备注左滑 + 30 反馈条数）
- 三筛选（已划/未划、已评分/未评分、文本搜索）+ 卡片列表 + 详情抽屉
- **5 个 pipeline 阶段反馈槽**：评分给 1-5 ground truth；分类选正确类 + 关键词；其他二元反馈
- 话术修改 LCS 字符级 diff 高亮
- 手机优先 UI（横向锁滚 + 纵向触摸滚动）

### Notion 自动同步
- 每天 10:30 + 23:00（北京时间）通过 launchd 自动 sync 到 Notion 数据看板页
- 手动触发：管理员页 → 数据看板 → 📤 导出按钮
- 同步内容：所有 companies + 最近一次 swipe 状态 + 拒绝分类 + 话术状态

### 实验隔离环境
- `experiments/` 目录骨架（`_shared/{runner, metrics, report}.py` + corpus/samples 目录）
- `experiments/README.md` 含 pipeline 节点 + 编号约定（001-009 抓取 / 010-019 筛选 / 020-029 推送 / 030-039 分类）
- 生产代码参数化：`webapp/llm_service.py` 的 `_call_qwen` 和 `score_company_rubric` 接受 `model` / `temperature` / `system_template` / `prompt_template` 参数（默认值=现行生产值）

### 历史记录
- 列表视图 + 卡片详情底部弹层
- 已联系状态标记
- 待发送话术（pending swipes）跳转

## 已知限制

- 仅支持单台 Mac 部署
- ngrok 公网访问需手动配置静态域名
- Notion 自动同步前提：webapp 进程须在跑（launchd 不直接执行 Python，规避 iCloud 死锁）
- LLM 评分 prompt 未做系统性优化（待数据看板反馈攒够后开 #001 实验）
- 长内容（>5000字）未做分段处理

## 部署状态

- **本机端口**：5173
- **公网域名**：通过 ngrok 静态域名（配置在 `.env` 的 `NGROK_DOMAIN`）
- **进程托管**：launchd
  - `com.mfv.bridge`：Chrome 扩展 WebSocket bridge
  - `com.mfv.webapp`：Flask 主进程（手动启动模式，规避 iCloud 锁）
  - `com.mfv.ngrok`：公网隧道
  - `com.mfv.notion-sync`：每日 10:30 + 23:00 自动同步 Notion
