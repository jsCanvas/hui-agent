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

演示区肖像序列帧来自 Companion **beifen/speaking HD PNG**（与桌面端白边形象同一套），按区段采样 idle / listening / speaking：

```bash
cd website && bash scripts/prepare-demo-frames.sh
# 宽度与质量：bash scripts/prepare-demo-frames.sh 200 86
```

```bash
# 手动触发：GitHub → Actions → pages → Run workflow
# 或推送 website/ 变更后自动部署
git push origin main
```

部署地址：<https://jscanvas.github.io/hui-agent/>

> branch 部署模式只能选 `/` 或 `/docs`，**不能**选 `/website`；请用 GitHub Actions。
