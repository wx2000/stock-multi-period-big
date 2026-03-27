# 多周期K线图生成 Skill · v1.1

## 触发关键词
以下任意词语都应激活本 Skill 并执行 `python main.py`：
- 生成报告
- 生成K线图
- 跑报告
- 股票报告
- 看K线
- 出图

## 描述
接受一个股票列表（支持A股、港股、美股），自动获取行情数据，生成专业级多周期K线图（黑色背景，分时/日/周/月/季/年共6个周期），并保存为本地图片文件。

## 功能特性
- **多市场支持**：A股（沪深）、港股、美股
- **6个周期**：分时（1min）、日线、周线、月线、季线、年线
- **专业图表**：黑色背景，每个周期含K线+均线+成交量+MACD
- **批量生成**：可一次为多只股票生成图表
- **免费数据源**：东方财富、新浪财经API

## 使用方法

### 快速开始
```bash
cd e:\Myskills\stock-multi-period-big
pip install -r requirements.txt
python main.py
```

### 指定股票列表
```bash
# 方式1：命令行参数
python main.py --stocks 000001 600036 00700 AAPL

# 方式2：从文件读取
python main.py --file stocks.txt

# 方式3：交互模式
python main.py --interactive
```

### 股票代码格式
- A股：直接写代码，如 `000001`（平安银行）、`600036`（招商银行）
- 港股：直接写代码，如 `00700`（腾讯）、`09988`（阿里巴巴）
- 美股：直接写代码，如 `AAPL`、`TSLA`、`MSFT`

## 输出
图片保存在 `output/` 目录下，文件名格式：`{股票代码}_{时间戳}.png`

## 通知发送（可选）

### 方式一：命令行直接传 Webhook URL（临时使用）
```bash
# 发送到企业微信
python main.py --stocks 000001 --wecom "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"

# 发送到飞书
python main.py --stocks 000001 --feishu "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_HOOK"

# 同时发送到两个渠道
python main.py --stocks 000001 600036 \
  --wecom "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY" \
  --feishu "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_HOOK"
```

### 方式二：配置文件（推荐，永久生效）
```bash
# 1. 复制配置模板
copy config.yaml.example config.yaml

# 2. 编辑 config.yaml，填入你的 Webhook URL，将 enabled 改为 true

# 3. 运行时加 --notify 参数
python main.py --notify
python main.py --stocks 000001 600036 --notify
```

### 如何获取 Webhook URL

**企业微信群机器人：**
1. 打开企业微信 → 进入目标群
2. 点击右上角 `···` → 添加群机器人 → 新建机器人
3. 复制 Webhook 地址

**飞书群机器人：**
1. 打开飞书 → 进入目标群
2. 点击右上角设置 → 群机器人 → 添加机器人 → 自定义机器人
3. 复制 Webhook 地址

### 发送内容说明
- **企业微信**：文字摘要（股票名称/代码/最新价/涨跌幅）+ K线图（PNG，超2MB自动压缩）
- **飞书 Webhook**：卡片消息（含文字摘要），图片以本地路径注明
  > 飞书 Webhook 不支持直接发图片，如需发图片请使用飞书自建应用方式（见 `config.yaml.example`）

## 依赖
见 `requirements.txt`（含 PyYAML，用于读取配置文件）

## 文件结构
```
stock-multi-period-big/
├── SKILL.md              # 本文件
├── main.py               # 主入口
├── data_fetcher.py       # 数据获取模块
├── chart_generator.py    # 图表生成模块
├── notifier.py           # 通知发送模块（企业微信/飞书）
├── config.yaml.example   # 配置文件模板（复制为 config.yaml 并填写）
├── config.yaml           # 你的实际配置（不要提交到 git！）
├── requirements.txt      # Python依赖
├── stocks.txt            # 默认股票列表（可编辑）
├── output/               # 输出图片目录
└── 多周期-big.PNG        # 参考样图
```
