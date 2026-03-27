# 项目长期记忆 · 多周期K线图 Skill

## 项目概述
- **目标**: 接受股票列表（A股/港股/美股），生成多周期K线图PNG，可选发送企业微信/飞书
- **Python 版本**: 3.7.3，所有依赖已降级兼容
- **数据源**: 东方财富 API（K线）+ 新浪财经 API（股票名称）

## 文件结构
| 文件 | 说明 |
|------|------|
| `main.py` | 主入口，支持命令行/文件/交互模式，支持 --wecom/--feishu/--notify |
| `data_fetcher.py` | 数据获取，支持6周期（分时/日/周/月/季/年），季线由月线聚合 |
| `chart_generator.py` | 图表生成，黑底2×3布局，每图含K线+均线+成交量+MACD |
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

## 使用方式
```bash
# 基础运行
python main.py

# 指定股票
python main.py --stocks 000001 600036 00700 AAPL

# 发送企业微信（URL方式）
python main.py --stocks 000001 --wecom "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=KEY"

# 发送飞书（URL方式）
python main.py --stocks 000001 --feishu "https://open.feishu.cn/open-apis/bot/v2/hook/HOOK"

# 从 config.yaml 读取配置发送
python main.py --notify
```

## 待扩展
- 飞书自建应用直接发图片（需 app_id + app_secret + chat_id）
- 定时任务（cron/任务计划）自动运行

## GitHub Pages + Cloudflare Pages 托管（已完成，2026-03-25/26）
- `git_push.py`：自动将 HTML 复制到 docs/index.html + docs/archive/，然后 git add/commit/push
- `main.py` 默认启用 push，离线使用加 `--no-push`
- `.gitignore` 排除 config.yaml、output PNG/HTML、pycache
- GitHub Pages 设置：Branch=main, 目录=/docs，地址：https://wx2000.github.io/stock-multi-period-big/
- Cloudflare Pages：绑定同一 GitHub 仓库，Build output=docs，地址：https://stock-multi-period-big.pages.dev（国内访问更快）
- 企业微信通知链接已更新为 Cloudflare Pages 地址
