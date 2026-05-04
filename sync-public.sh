#!/bin/bash
# 同步 internal/main → public/main，自动剔除敏感文件，提交并推送到 GitHub
# 用法：./sync-public.sh "commit message"
#
# 前提：internal 当前分支必须是 main（验收版本）

set -e

INTERNAL="$(cd "$(dirname "$0")" && pwd)"
PUBLIC="$INTERNAL/../xiaohongshu-skills-public"
MSG="${1:-Sync from internal main}"

# 检查当前分支
cd "$INTERNAL"
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
  echo "❌ internal 当前在分支 $BRANCH，必须切到 main 才能同步"
  exit 1
fi

# 检查 public 仓库存在
if [ ! -d "$PUBLIC/.git" ]; then
  echo "❌ 找不到 public 仓库：$PUBLIC"
  exit 1
fi

echo "📂 internal: $INTERNAL"
echo "📂 public:   $PUBLIC"
echo ""

# rsync 同步，剔除敏感文件和无关目录
# --no-links: 不复制 symlink（iCloud 会创建 .venv 2 → .venv.nosync 这种链接）
rsync -av --delete --no-links \
  --exclude=".git/" \
  --exclude=".venv*" \
  --exclude="webapp/.env" \
  --exclude="webapp/mfv.db*" \
  --exclude="webapp/logs/" \
  --exclude=".claude/settings.local.json" \
  --exclude="__pycache__/" \
  --exclude="*.pyc" \
  --exclude=".DS_Store" \
  --exclude="*.zip" \
  --exclude="MFV-Deal-Flow-开发状态.md" \
  "$INTERNAL/" "$PUBLIC/"

echo ""
echo "✅ 文件同步完成"
echo ""

# 提交并推送
cd "$PUBLIC"
git add -A
if git diff --staged --quiet; then
  echo "ℹ️  public 仓库无变更，无需推送"
  exit 0
fi

git status --short
echo ""
read -p "确认推送到 GitHub？[y/N] " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "已取消，但 public 目录的改动保留"
  exit 0
fi

git commit -m "$MSG"
git push origin main
echo ""
echo "🚀 已推送到 GitHub"
