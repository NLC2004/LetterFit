"""邮箱服务商与大模型预设。"""
from __future__ import annotations

SMTP_PRESETS: dict[str, dict] = {
    "QQ 邮箱": {
        "host": "smtp.qq.com",
        "port": 465,
        "ssl": True,
        "user_hint": "你的 QQ 邮箱地址，如 123456@qq.com",
        "guide": "先在网页版 QQ 邮箱开启 SMTP，然后填写邮箱和邮箱密码。",
    },
    "163 邮箱": {
        "host": "smtp.163.com",
        "port": 465,
        "ssl": True,
        "user_hint": "你的 163 邮箱地址",
        "guide": "先在网页版 163 邮箱开启 SMTP，然后填写邮箱和邮箱密码。",
    },
    "Outlook / 微软邮箱": {
        "host": "smtp.office365.com",
        "port": 587,
        "ssl": False,
        "user_hint": "你的 Outlook 地址",
        "guide": "填写 Outlook 邮箱和邮箱密码。",
    },
    "Gmail": {
        "host": "smtp.gmail.com",
        "port": 465,
        "ssl": True,
        "user_hint": "你的 Gmail 地址",
        "guide": "填写 Gmail 和邮箱密码。国内网络通常无法直连。",
    },
    "校园 / 其他邮箱（手动填写）": {
        "host": "",
        "port": 465,
        "ssl": True,
        "user_hint": "你的邮箱完整地址",
        "guide": "在学校邮箱帮助页查看 SMTP 地址和端口，然后填写邮箱和邮箱密码。",
    },
}

LLM_PRESETS: dict[str, dict] = {
    "DeepSeek（推荐，新用户有免费额度）": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "guide": "打开 platform.deepseek.com 注册 → API keys → 创建密钥，粘贴到下方。",
    },
    "月之暗面 Kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "guide": "打开 platform.moonshot.cn 创建 API Key。",
    },
    "通义千问": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "guide": "打开阿里云百炼平台创建 API-KEY。",
    },
    "其他 OpenAI 兼容接口（手动填写）": {
        "base_url": "",
        "model": "",
        "guide": "填写服务商提供的 Base URL、模型名和 API Key。",
    },
}
