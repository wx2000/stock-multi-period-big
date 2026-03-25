"""
消息发送模块
支持：企业微信群机器人 Webhook、飞书群机器人 Webhook
发送内容：K线图PNG + 文字摘要（股票代码/名称/最新价/涨跌幅）
"""

import base64
import json
import os
import requests


# ══════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════

def _img_to_base64(img_path: str) -> tuple:
    """读取图片并返回 (base64_str, md5_str)"""
    import hashlib
    with open(img_path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("utf-8")
    md5 = hashlib.md5(raw).hexdigest()
    return b64, md5


def _build_summary(stock_data: dict) -> str:
    """
    构建文字摘要
    stock_data 格式: {"info": {display, name, market}, "periods": {...}}
    返回单只股票的摘要文本
    """
    info = stock_data.get("info", {})
    display = info.get("display", "N/A")
    name    = info.get("name", display)
    market  = info.get("market", "")

    # 从日线最后一根蜡烛取价格
    df_day = stock_data.get("periods", {}).get("日线")
    if df_day is not None and not df_day.empty:
        last = df_day.iloc[-1]
        price   = last.get("close", 0)
        chg_pct = last.get("chg_pct", 0)
        # 中国惯例：涨=红 跌=绿（文本里用符号表示）
        arrow = "+" if chg_pct >= 0 else "-"
        price_str = f"{price:.2f}  {arrow}{abs(chg_pct):.2f}%"
    else:
        price_str = "暂无数据"

    market_label = {
        "A_SH": "A股·沪",
        "A_SZ": "A股·深",
        "HK":   "港股",
        "US":   "美股",
    }.get(market, market)

    return f"📊 {name}（{display}）[{market_label}]\n   最新价: {price_str}"


# ══════════════════════════════════════════════════════════════════
#  企业微信群机器人
# ══════════════════════════════════════════════════════════════════

class WeCom:
    """
    企业微信群机器人
    文档: https://developer.work.weixin.qq.com/document/path/91770
    """

    def __init__(self, webhook_url: str):
        """
        :param webhook_url: 企业微信群机器人 Webhook 完整 URL
            格式: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
        """
        self.webhook_url = webhook_url.strip()

    def _post(self, payload: dict) -> dict:
        resp = requests.post(
            self.webhook_url,
            json=payload,
            timeout=15,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    def send_text(self, text: str) -> dict:
        """发送纯文本消息"""
        payload = {
            "msgtype": "text",
            "text": {"content": text},
        }
        return self._post(payload)

    def send_image(self, img_path: str) -> dict:
        """
        发送图片（base64方式，支持JPG/PNG，大小≤2MB）
        超过2MB建议先压缩或改用 send_image_url
        """
        size_mb = os.path.getsize(img_path) / 1024 / 1024
        if size_mb > 2:
            raise ValueError(
                f"图片大小 {size_mb:.1f}MB 超过企业微信限制(2MB)，"
                f"请先压缩或使用 send_image_file_via_media()"
            )
        b64, md5 = _img_to_base64(img_path)
        payload = {
            "msgtype": "image",
            "image": {"base64": b64, "md5": md5},
        }
        return self._post(payload)

    def send_image_compressed(self, img_path: str, quality: int = 70) -> dict:
        """
        自动压缩后发送图片（解决>2MB限制）
        需要 Pillow
        """
        import io
        from PIL import Image

        img = Image.open(img_path)
        buf = io.BytesIO()
        # 转 RGB（PNG可能有 RGBA 通道）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        raw = buf.getvalue()

        import hashlib
        b64 = base64.b64encode(raw).decode("utf-8")
        md5 = hashlib.md5(raw).hexdigest()

        size_mb = len(raw) / 1024 / 1024
        print(f"  [企微] 压缩后大小: {size_mb:.2f}MB")

        if size_mb > 2:
            raise ValueError(f"压缩后仍 {size_mb:.1f}MB，请降低 quality 参数或缩小图片尺寸")

        payload = {
            "msgtype": "image",
            "image": {"base64": b64, "md5": md5},
        }
        return self._post(payload)

    def send_stock(self, stock_data: dict, img_path: str) -> bool:
        """
        发送单只股票：文字摘要 + K线图
        :param stock_data: fetch_stock_data() 返回的字典
        :param img_path: 已生成的图片路径
        :return: 是否成功
        """
        try:
            summary = _build_summary(stock_data)
            # 先发文字
            self.send_text(summary)
            # 再发图片（自动处理大小限制）
            size_mb = os.path.getsize(img_path) / 1024 / 1024
            if size_mb > 2:
                print(f"  [企微] 图片 {size_mb:.1f}MB > 2MB，自动压缩...")
                self.send_image_compressed(img_path)
            else:
                self.send_image(img_path)
            print(f"  [企微] OK 发送成功: {stock_data['info']['display']}")
            return True
        except Exception as e:
            print(f"  [企微] FAIL 发送失败: {e}")
            return False

    def send_batch(self, stock_data_list: list, img_paths: list) -> int:
        """
        批量发送
        :return: 成功发送数量
        """
        ok = 0
        # 先发汇总标题
        names = [
            f"{d['info'].get('name', d['info']['display'])}({d['info']['display']})"
            for d in stock_data_list
        ]
        header = "[多周期K线图报告]\n" + "\n".join(f"  * {n}" for n in names)
        try:
            self.send_text(header)
        except Exception as e:
            print(f"  [企微] 发送标题失败: {e}")

        for data, path in zip(stock_data_list, img_paths):
            if self.send_stock(data, path):
                ok += 1
        return ok


# ══════════════════════════════════════════════════════════════════
#  飞书群机器人
# ══════════════════════════════════════════════════════════════════

class Feishu:
    """
    飞书群机器人
    文档: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
    图片发送需先上传获取 image_key，使用 multipart/form-data
    """

    def __init__(self, webhook_url: str):
        """
        :param webhook_url: 飞书群机器人 Webhook 完整 URL
            格式: https://open.feishu.cn/open-apis/bot/v2/hook/xxx
        """
        self.webhook_url = webhook_url.strip()

    def _post(self, payload: dict) -> dict:
        resp = requests.post(
            self.webhook_url,
            json=payload,
            timeout=15,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        resp.raise_for_status()
        return resp.json()

    def send_text(self, text: str) -> dict:
        """发送纯文本消息"""
        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        return self._post(payload)

    def send_image(self, img_path: str) -> dict:
        """
        飞书群机器人直接通过 Webhook 发送图片（base64方式）
        注意: 飞书 Webhook 不直接支持图片消息，需上传后用 image_key
        此方法将图片以 post（富文本）消息嵌入
        """
        b64, _ = _img_to_base64(img_path)
        # 飞书 webhook 富文本：图片用 image 类型（需要 image_key，Webhook 不支持直传）
        # 退而求其次：以文件链接形式发送提示
        raise NotImplementedError(
            "飞书 Webhook 不支持直接发图片，请使用 send_image_as_post() 或自建应用方式"
        )

    def send_image_via_multipart(self, img_path: str) -> dict:
        """
        通过 multipart 上传图片并发送（飞书 Webhook 支持 image_key 方式）
        实际上飞书 Webhook 消息类型中 image 消息 需要先上传图片获取 image_key
        由于 Webhook 本身不支持上传，此处改用"分享图片链接"方式（需图片已托管）
        改用 send_rich_text() 发送文字+图片说明
        """
        raise NotImplementedError("请使用 send_stock() 统一接口")

    def _upload_image(self, img_path: str, app_id: str = None, app_secret: str = None) -> str:
        """
        （可选）上传图片到飞书并返回 image_key
        仅在使用自建应用时有效，Webhook 模式不需要
        """
        raise NotImplementedError("仅自建应用模式支持图片上传，当前为 Webhook 模式")

    def send_rich_card(self, title: str, summary: str, img_path: str) -> dict:
        """
        发送飞书卡片消息（interactive）
        飞书卡片支持图片，需先将图片转为 base64 并使用 image 组件
        注意：飞书 Webhook 卡片中的图片需要 image_key，无法直接嵌 base64
        此方法改为：文字卡片 + 单独提示图片已保存本地
        """
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": summary,
                    },
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"📁 图片已保存: {os.path.basename(img_path)}",
                        }
                    ],
                },
            ],
        }
        payload = {
            "msg_type": "interactive",
            "card": json.dumps(card, ensure_ascii=False),
        }
        return self._post(payload)

    def send_image_as_base64_post(self, img_path: str, title: str = "") -> dict:
        """
        飞书富文本消息（post类型）发送图片
        飞书 Webhook post 消息支持 img 标签，但 image_key 必须预先上传
        退而求其次：压缩图片后转 base64，以文字形式告知图片大小和路径
        实用方案：文字摘要 + 图片本地路径
        """
        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [
                            [{"tag": "text", "text": f"📁 图片路径: {img_path}"}]
                        ],
                    }
                }
            },
        }
        return self._post(payload)

    def send_stock(self, stock_data: dict, img_path: str) -> bool:
        """
        发送单只股票：卡片摘要（飞书 Webhook 限制，图片以本地路径注明）
        :param stock_data: fetch_stock_data() 返回的字典
        :param img_path: 已生成的图片路径
        :return: 是否成功
        """
        try:
            info    = stock_data.get("info", {})
            display = info.get("display", "N/A")
            name    = info.get("name", display)
            summary = _build_summary(stock_data)

            title = f"[多周期K线图] {name}({display})"
            self.send_rich_card(title, summary, img_path)
            print(f"  [飞书] OK 发送成功: {display}")
            return True
        except Exception as e:
            print(f"  [飞书] FAIL 发送失败: {e}")
            return False

    def send_batch(self, stock_data_list: list, img_paths: list) -> int:
        """批量发送，返回成功数量"""
        ok = 0
        for data, path in zip(stock_data_list, img_paths):
            if self.send_stock(data, path):
                ok += 1
        return ok


# ══════════════════════════════════════════════════════════════════
#  飞书增强版：图片直接发送（利用 /open-apis/im/v1/images 上传）
#  需要飞书自建应用的 app_id + app_secret，或使用已有 token
# ══════════════════════════════════════════════════════════════════

class FeishuApp:
    """
    飞书自建应用方式（支持图片直接发送到群）
    需要: app_id, app_secret, chat_id（群ID）
    相比 Webhook 方式，图片可以直接发送（不受 image_key 限制）
    """

    TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    UPLOAD_URL = "https://open.feishu.cn/open-apis/im/v1/images"
    MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

    def __init__(self, app_id: str, app_secret: str, chat_id: str):
        """
        :param app_id: 飞书应用 App ID
        :param app_secret: 飞书应用 App Secret
        :param chat_id: 目标群 Chat ID（oc_xxx 格式）
        """
        self.app_id     = app_id
        self.app_secret = app_secret
        self.chat_id    = chat_id
        self._token     = None
        self._token_expire = 0

    def _get_token(self) -> str:
        """获取或刷新 tenant_access_token"""
        import time
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        resp = requests.post(
            self.TOKEN_URL,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取飞书 token 失败: {data}")
        self._token = data["tenant_access_token"]
        import time as _time
        self._token_expire = _time.time() + data.get("expire", 7200)
        return self._token

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
        }

    def upload_image(self, img_path: str) -> str:
        """上传图片，返回 image_key"""
        with open(img_path, "rb") as f:
            resp = requests.post(
                self.UPLOAD_URL,
                headers=self._auth_headers(),
                data={"image_type": "message"},
                files={"image": f},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"上传图片失败: {data}")
        return data["data"]["image_key"]

    def send_text(self, text: str) -> dict:
        """发送文本消息到群"""
        resp = requests.post(
            self.MESSAGE_URL,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": self.chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def send_image(self, img_path: str) -> dict:
        """上传并发送图片消息"""
        image_key = self.upload_image(img_path)
        resp = requests.post(
            self.MESSAGE_URL,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": self.chat_id,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key}),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def send_stock(self, stock_data: dict, img_path: str) -> bool:
        """发送文字摘要 + 图片"""
        try:
            summary = _build_summary(stock_data)
            self.send_text(summary)
            self.send_image(img_path)
            print(f"  [飞书App] ✓ 发送成功: {stock_data['info']['display']}")
            return True
        except Exception as e:
            print(f"  [飞书App] ✗ 发送失败: {e}")
            return False

    def send_batch(self, stock_data_list: list, img_paths: list) -> int:
        ok = 0
        names = [
            f"{d['info'].get('name', d['info']['display'])}({d['info']['display']})"
            for d in stock_data_list
        ]
        header = "📈 多周期K线图报告\n" + "\n".join(f"  • {n}" for n in names)
        try:
            self.send_text(header)
        except Exception as e:
            print(f"  [飞书App] 发送标题失败: {e}")
        for data, path in zip(stock_data_list, img_paths):
            if self.send_stock(data, path):
                ok += 1
        return ok


# ══════════════════════════════════════════════════════════════════
#  快捷工厂函数（供 main.py 调用）
# ══════════════════════════════════════════════════════════════════

def make_notifier(config: dict):
    """
    根据 config 字典创建通知器列表
    config 结构见 config.yaml
    返回: list of (name, notifier_instance)
    """
    notifiers = []

    # 企业微信
    wecom_cfg = config.get("wecom", {})
    if wecom_cfg.get("enabled") and wecom_cfg.get("webhook_url"):
        notifiers.append(("企业微信", WeCom(wecom_cfg["webhook_url"])))

    # 飞书 Webhook
    feishu_cfg = config.get("feishu", {})
    if feishu_cfg.get("enabled") and feishu_cfg.get("webhook_url"):
        notifiers.append(("飞书Webhook", Feishu(feishu_cfg["webhook_url"])))

    # 飞书自建应用
    feishu_app_cfg = config.get("feishu_app", {})
    if (feishu_app_cfg.get("enabled")
            and feishu_app_cfg.get("app_id")
            and feishu_app_cfg.get("app_secret")
            and feishu_app_cfg.get("chat_id")):
        notifiers.append(("飞书App", FeishuApp(
            feishu_app_cfg["app_id"],
            feishu_app_cfg["app_secret"],
            feishu_app_cfg["chat_id"],
        )))

    return notifiers


# ══════════════════════════════════════════════════════════════════
#  测试
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import yaml

    cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(cfg_path):
        print("请先配置 config.yaml")
    else:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        notifiers = make_notifier(cfg)
        print(f"已加载 {len(notifiers)} 个通知渠道: {[n for n, _ in notifiers]}")
        for name, n in notifiers:
            try:
                n.send_text(f"[测试] {name} 发送测试 ✓")
                print(f"  {name}: 文本消息发送成功")
            except Exception as e:
                print(f"  {name}: 失败 - {e}")
