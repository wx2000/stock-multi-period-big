# 项目长期记忆 · 多周期K线图 Skill

## 项目概述
- **目标**: 接受股票列表（A股/港股/美股），生成多周期K线图PNG，可选发送企业微信/飞书
- **Python 版本**: 3.7.3，所有依赖已降级兼容
- **数据源**: 东方财富 API（K线）+ 新浪财经 API（股票名称）

## 文件结构
| 文件 | 说明 |
|------|------|
| `main.py` | 主入口，支持命令行/文件/交互模式，支持 --wecom/--feishu/--notify，支持 --layout 参数切换布局方案，支持 --offline 离线模式 |
| `data_fetcher.py` | 数据获取，支持6周期（分时/日/周/月/季/年），季线由月线聚合；**已优化**：Session复用、请求重试、本地缓存、改进日志 |
| `chart_generator.py` | 图表生成（方案A），黑底2×3布局（6周期），每图含K线+均线+成交量+MACD |
| `chart_generator_b.py` | 图表生成（方案B），黑底2×2布局（4周期），去掉分时和年线，保留日线/周线/月线/季线 |
| `notifier.py` | 通知发送，支持企业微信Webhook、飞书Webhook、飞书自建应用 |
| `config.yaml.example` | 配置模板，复制为 config.yaml 填写 Webhook URL |
| `requirements.txt` | 依赖：requests/pandas/numpy/matplotlib/Pillow/PyYAML |
| `stocks.txt` | 默认股票列表 |

## 关键技术决策
- 中文字体：`_setup_chinese_font()` 自动检测 SimHei/微软雅黑
- pandas 兼容：使用旧版字典 agg 语法（pandas 0.24+）
- matplotlib 兼容：GridSpec 去掉 `figure=` 参数（3.1.x不支持）
- 季线：由月线 groupby("Q") 聚合（东方财富无直接季线接口）
- 企业微信图片：自动检测>2MB时用 Pillow 压缩为 JPEG 发送
- 飞书 Webhook 限制：不支持直接发图，发卡片消息（含本地路径）；真正发图需 FeishuApp 自建应用模式
- 日线均线配置（2026-03-27）：只保留 MA260（淡蓝色 #aaaaff），MAX_BARS=300；K线区左上角显示偏差值 = 收盘/MA260-1（百分比，涨红跌绿）
- **错误处理强化（2026-03-31）**：Session 连接复用、请求重试（3次指数退避 1s/2s/4s）、本地 JSON 缓存（24h 有效期）、改进日志（[INFO]/[WARN]/[ERROR]）、离线模式支持

## 使用方式
```bash
# 基础运行（默认方案A：2×3布局，6周期）
python main.py

# 指定股票（方案A）
python main.py --stocks 000001 600036 00700 AAPL

# 方案B：2×2布局，4周期（日线/周线/月线/季线）
python main.py --stocks 000001 --layout B

# 显式指定方案A
python main.py --stocks 000001 --layout A

# 发送企业微信（URL方式，默认方案A）
python main.py --stocks 000001 --wecom "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=KEY"

# 发送飞书（方案B）
python main.py --stocks 000001 --layout B --feishu "https://open.feishu.cn/open-apis/bot/v2/hook/HOOK"

# 从 config.yaml 读取配置发送
python main.py --notify

# 离线模式（仅使用本地缓存，不发起网络请求）
python main.py --stocks 000001 --offline
```

## 沟通约定（重要）
- **遇到问号必须先沟通**：当 King 的消息中出现 `?` 或 `？`（英文或中文问号），必须先和 King 沟通确认需求，**不得直接动手修改代码**。

## 布局方案对比（2026-03-31添加方案B）

### 方案A（默认）- 2×3布局，6周期
- GridSpec：2行×3列
- 周期：分时、日线、周线、月线、季线、年线
- 文件名：无后缀（如 `000001-平安银行_20260331_155900.png`）
- 用途：专业分析，信息全面
- 使用：`python main.py --stocks CODE` 或 `python main.py --stocks CODE --layout A`

### 方案B - 2×2布局，4周期
- GridSpec：2行×2列
- 周期：日线、周线、月线、季线（去掉分时和年线）
- 文件名：带 `_b` 后缀（如 `000001-平安银行_b_20260331_155917.png`）
- 间距参数：hspace=0.28, wspace=0.15（相比方案A的0.25/0.12略增）
- 用途：精简版本，重点关注核心周期
- 使用：`python main.py --stocks CODE --layout B`

## 数据源备份方案研究（2026-03-31）

### 综合测试结果
已详尽测试三个备选数据源能否作为东方财富的备份：

| 数据源 | 实时报价 | K线日数据 | 6周期支持 | 可靠性 | 备注 |
|--------|---------|---------|----------|--------|------|
| **东方财富** | ✅ | ✅ | ✅ | ⭐⭐⭐⭐ | 主力源，稳定 |
| **腾讯财经** | ✅ | ❌ | ❌ | ⭐ | K线API失效，不可用 |
| **新浪财经** | ❌ | ❌ | ❌ | ⭐ | 大多接口已失效/限制 |
| **AKShare** | ✅ | ✅ | ✅ | ⭐⭐⭐ | 代码需升级pandas/numpy，破坏兼容性 |

### 各源详情
- **腾讯**：实时报价工作（qt.gtimg.cn），K线接口全返回 param error
- **新浪**：主要接口返回 404 或空，Web 页面需要 JS 渲染，反爬虫限制强
- **AKShare**：库本身支持6周期，但依赖冲突（需 pandas>=1.3.5，当前0.24.2）

### 最终建议（2026-03-31 确认）
**采用方案 A：保持东方财富单源 + 强化错误处理**

理由：
1. 东方财富 API 近 2-3 年未有大变更，本身很稳定
2. 备选源都有严重问题，无法可靠使用
3. 强化错误处理成本最低，稳定性最高

具体改进：
- 增加重试机制（max_retries=3，指数退避）
- 本地缓存最后一次成功数据（离线 fallback）
- 改进错误日志和提示
- 优化超时和连接池设置

详见：`TEST_SINA_BACKUP_SUMMARY.md`

## 待扩展
- ✅ **数据源备份评估完成（2026-03-31）** - 最终决策：保持单源 + 强化错误处理
- ✅ **错误处理强化完成（2026-03-31）** - 实现 Session复用、请求重试、本地缓存、改进日志、离线模式
- 多数据源 fallback 机制实现（低优先级，仅当东方财富 API 频繁故障时考虑）
- 飞书自建应用直接发图片（需 app_id + app_secret + chat_id）
- 定时任务（cron/任务计划）自动运行
- API 速率限制监控（可选，当前用户场景日运行1次 ≤ 20只股票，无压力）

## GitHub Pages + Cloudflare Pages 托管（已完成，2026-03-25/26）
- `git_push.py`：自动将 HTML 复制到 docs/index.html + docs/archive/，然后 git add/commit/push
- `main.py` 默认启用 push，离线使用加 `--no-push`
- `.gitignore` 排除 config.yaml、output PNG/HTML、pycache
- GitHub Pages 设置：Branch=main, 目录=/docs，地址：https://wx2000.github.io/stock-multi-period-big/
- Cloudflare Pages：绑定同一 GitHub 仓库，Build output=docs，地址：https://stock-multi-period-big.pages.dev（国内访问更快）
- 企业微信通知链接已更新为 Cloudflare Pages 地址
