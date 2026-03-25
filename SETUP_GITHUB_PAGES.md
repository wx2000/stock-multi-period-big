# GitHub Pages 一次性配置指南

本文档说明如何将多周期K线图报告托管到 GitHub Pages。**只需配置一次**，之后每次运行 `python main.py` 都会自动推送更新。

---

## 前置条件

- 已安装 [Git](https://git-scm.com/)
- 已有 [GitHub](https://github.com) 账号
- 推荐使用 SSH 认证（避免每次 push 输密码）

---

## 第一步：在 GitHub 创建仓库

1. 打开 https://github.com/new
2. 仓库名填写：`stock-multi-period-big`
3. 选择 **Public**（GitHub Pages 免费版需要公开仓库）
4. **不要**勾选 "Initialize this repository"（本地已有代码）
5. 点击 **Create repository**

---

## 第二步：本地初始化 Git 仓库

在项目根目录（`e:\Myskills\stock-multi-period-big\`）打开终端，依次执行：

```powershell
# 初始化本地仓库
git init

# 设置默认分支名为 main
git branch -M main

# 关联远程仓库（替换 YOUR_USERNAME 为你的 GitHub 用户名）
git remote add origin https://github.com/YOUR_USERNAME/stock-multi-period-big.git

# 或者使用 SSH（推荐，免密）
git remote add origin git@github.com:YOUR_USERNAME/stock-multi-period-big.git
```

---

## 第三步：首次推送

```powershell
# 添加所有文件（.gitignore 会自动排除敏感文件）
git add .

# 首次提交
git commit -m "init: 多周期K线图 Skill + GitHub Pages 支持"

# 推送到 GitHub
git push -u origin main
```

---

## 第四步：开启 GitHub Pages

1. 打开你的仓库页面：`https://github.com/YOUR_USERNAME/stock-multi-period-big`
2. 点击 **Settings** → 左侧菜单找到 **Pages**
3. **Source** 选择：`Deploy from a branch`
4. **Branch** 选择：`main`，目录选择：`/docs`
5. 点击 **Save**

等待约 1 分钟，页面会出现：

```
Your site is live at https://YOUR_USERNAME.github.io/stock-multi-period-big/
```

---

## 第五步：验证自动推送

运行一次脚本，观察输出：

```powershell
python main.py --stocks 000001 600036
```

正常输出应包含：

```
==================================================
正在推送到 GitHub Pages...
  [GitHub Pages] 已更新 docs/index.html
  [GitHub Pages] 已归档 docs/archive/report_YYYYMMDD_HHMMSS.html
  [GitHub Pages] git add docs/ 完成
  [GitHub Pages] git commit: update: report_xxx.html [2026-03-25 20:30]
  [GitHub Pages] git push 成功！GitHub Pages 将在约 1 分钟内更新
```

然后访问你的 GitHub Pages 网址，即可看到最新报告。

---

## 常用命令

```powershell
# 正常运行（生成图表 + 自动 push）
python main.py

# 离线使用（跳过 push）
python main.py --no-push

# 只指定部分股票
python main.py --stocks 000001 AAPL --no-push
```

---

## SSH 认证配置（推荐，避免每次输密码）

```powershell
# 生成 SSH 密钥（如果还没有）
ssh-keygen -t ed25519 -C "your_email@example.com"

# 查看公钥内容
cat ~/.ssh/id_ed25519.pub

# 将上面的内容复制到 GitHub：
# Settings → SSH and GPG keys → New SSH key → 粘贴 → Add SSH key
```

然后修改远程地址为 SSH 格式：

```powershell
git remote set-url origin git@github.com:YOUR_USERNAME/stock-multi-period-big.git
```

---

## 注意事项

| 事项 | 说明 |
|------|------|
| `config.yaml` | 含 Webhook 密钥，已被 `.gitignore` 排除，**永远不会被推送** |
| `output/` 目录 | PNG 和 HTML 均在本地，不推送，节省仓库空间 |
| `docs/index.html` | 每次运行后自动覆盖为最新报告 |
| `docs/archive/` | 保留所有历史报告，可在 GitHub 上直接查看 |
| 报告大小 | 每个 HTML 文件约 10-30MB（含 base64 图片），历史增长可控 |
