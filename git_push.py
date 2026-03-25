"""
GitHub Pages 自动推送模块

每次 main.py 生成 HTML 报告后调用本模块：
  1. 将 HTML 复制到 docs/index.html（覆盖，作为固定入口）
  2. 将 HTML 复制到 docs/archive/<原文件名>（历史归档）
  3. git add docs/ → git commit → git push

依赖：无（仅使用 Python 标准库 subprocess / shutil / os）
"""

import os
import shutil
import subprocess
from datetime import datetime


# docs 目录相对于本文件的位置
_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR   = os.path.join(_BASE_DIR, "docs")
ARCHIVE_DIR = os.path.join(DOCS_DIR, "archive")


def _run(cmd: list, cwd: str) -> tuple:
    """
    执行 git 命令，返回 (returncode, stdout, stderr)
    """
    result = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def push_html_to_github(html_path: str, verbose: bool = True) -> bool:
    """
    将本次生成的 HTML 报告推送到 GitHub Pages。

    参数
    ----
    html_path : 本次生成的 HTML 文件绝对路径（output/report_YYYYMMDD_HHMMSS.html）
    verbose   : 是否打印详细日志，默认 True

    返回
    ----
    True  = push 成功
    False = push 失败（不抛出异常，不影响主流程）
    """

    def log(msg):
        if verbose:
            print(f"  [GitHub Pages] {msg}")

    if not os.path.isfile(html_path):
        log(f"HTML 文件不存在，跳过 push: {html_path}")
        return False

    # ── 1. 确保 docs/ 和 docs/archive/ 存在 ────────────────────
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # ── 2. 复制到 docs/index.html（最新入口，覆盖）──────────────
    index_path = os.path.join(DOCS_DIR, "index.html")
    try:
        shutil.copy2(html_path, index_path)
        log(f"已更新 docs/index.html")
    except Exception as e:
        log(f"复制 index.html 失败: {e}")
        return False

    # ── 3. 复制到 docs/archive/<原文件名>（历史归档）─────────────
    archive_name = os.path.basename(html_path)
    archive_path = os.path.join(ARCHIVE_DIR, archive_name)
    try:
        shutil.copy2(html_path, archive_path)
        log(f"已归档 docs/archive/{archive_name}")
    except Exception as e:
        log(f"复制 archive 失败（非致命）: {e}")
        # 归档失败不阻止 push

    # ── 4. git add docs/ ────────────────────────────────────────
    code, out, err = _run(["git", "add", "docs/"], cwd=_BASE_DIR)
    if code != 0:
        log(f"git add 失败: {err}")
        return False
    log("git add docs/ 完成")

    # ── 5. git commit ────────────────────────────────────────────
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_msg = f"update: {archive_name} [{now_str}]"
    code, out, err = _run(["git", "commit", "-m", commit_msg], cwd=_BASE_DIR)
    if code != 0:
        # 如果 "nothing to commit" 也算成功
        if "nothing to commit" in out or "nothing to commit" in err:
            log("没有变化，无需 commit")
            return True
        log(f"git commit 失败: {err or out}")
        return False
    log(f"git commit: {commit_msg}")

    # ── 6. git push ──────────────────────────────────────────────
    code, out, err = _run(["git", "push"], cwd=_BASE_DIR)
    if code != 0:
        log(f"git push 失败: {err or out}")
        log("请检查：1) git remote 是否已配置  2) 网络是否正常  3) SSH/HTTPS 认证是否有效")
        return False

    log(f"git push 成功！GitHub Pages 将在约 1 分钟内更新")
    return True
