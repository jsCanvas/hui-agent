# HuiAgent 官网

静态介绍页，可部署到 GitHub Pages。

## 本地预览

```bash
cd website
python3 -m http.server 8080
# 打开 http://localhost:8080
```

## GitHub Pages

**前置条件（只需一次）**：仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**（不要选 Deploy from a branch）。

Workflow：`.github/workflows/pages.yml`（从 `website/` 目录发布）

演示区肖像与 Companion 共用 **seq-webp** 资源（idle/listening 静态首帧，speaking 循环采样）：

```bash
cd website && bash scripts/prepare-demo-frames.sh
# 2× 像素缓冲：bash scripts/prepare-demo-frames.sh 208 88
```

```bash
# 手动触发：GitHub → Actions → pages → Run workflow
# 或推送 website/ 变更后自动部署
git push origin main
```

部署地址：<https://jscanvas.github.io/hui-agent/>

> branch 部署模式只能选 `/` 或 `/docs`，**不能**选 `/website`；请用 GitHub Actions。
