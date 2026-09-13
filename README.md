<div align="center">

# LetterFit

**给真正相关的老师，写真正个性化的信。**

保研自荐邮件助手 · 本地运行 · 开源可查证

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)

[快速开始](#快速开始) · [工作原理](#工作原理) · [常见问题](#常见问题)

</div>

---

## 这是什么

套磁最难的不是「发出去」，而是**每一封都像认真写的**。

LetterFit 让你把学院官网师资页全文粘贴进来，由模型按学校、学院、导师名、邮箱、职称、方向整理名单，再按对方研究方向改写你的自荐信——经历和奖项保持原文，模型只填写与老师相关的四个空位。**每一封都经你确认后，才从你自己的邮箱发出。**

邮箱密码、API Key、名单、草稿全部只保存在本机。

## 特性

| | |
|---|---|
| **精准而不群发** | 官网全文粘贴后整理名单，你核对、勾选，只写给真正相关的老师 |
| **不编造** | 模板正文保持你的原文，模型只填 `{老师称呼}` `{老师方向}` `{交叉经历}` `{契合段}` |
| **简历成稿** | 上传简历 PDF，一键生成带空位的通用底稿，检查后再用 |
| **本地优先** | 数据不出电脑；逐封预览确认，发送有间隔，降低邮箱被风控的风险 |
| **三分钟上手** | 首次启动配置向导，下拉选邮箱服务商，不用自己改配置文件 |

## 快速开始

需要 [Python 3.10+](https://www.python.org/downloads/)，安装时勾选 **Add to PATH**。

```powershell
git clone https://github.com/NLC2004/LetterFit.git
cd LetterFit
```

然后双击 `启动.bat`。首次运行会自动创建虚拟环境并安装依赖。

浏览器打开后按向导走完四步：

| 步骤 | 做什么 |
|---|---|
| 1. 个人信息 | 姓名、学校、科研经历。模型只从这里挑选与老师的契合点 |
| 2. 发信邮箱 | 下拉选择服务商，填写邮箱和密码，测试登录 |
| 3. 大模型 | 推荐 [DeepSeek](https://platform.deepseek.com)，新用户有免费额度 |
| 4. 简历 | 上传 PDF 作为附件；也可根据简历生成邮件底稿 |

之后：**师资名单 → 勾选核对 → 生成草稿 → 逐封确认发送。**

学院官网基本无法直接爬取。打开师资页后 `Ctrl+A` 全选、`Ctrl+C` 复制，再在「师资名单」页 `Ctrl+V` 粘贴，让模型按 **学校 / 学院 / 导师名 / 邮箱 / 职称 / 方向** 整理。

## 工作原理

```
官网师资页 ──Ctrl+A / C / V──▶ 模型按学校、学院、导师名、邮箱、职称、方向整理
                         │
                         ▼
                    名单（你核对、勾选）
                         │
你的经历 + 邮件底稿 ──────┤
                         ▼
              大模型只填四个空位
                         │
                         ▼
              草稿（你逐封预览、可改）
                         │
                         ▼
              你的邮箱 SMTP 发出，并记录以免重复发送
```

模型被限制在你提供的经历里选契合点，不会发明你没做过的方向，也不会编造老师的论文题目。

## 常见问题

<details>
<summary><b>发信要填的密码是什么？</b></summary>

就是你的邮箱密码，只写在本机 <code>.env</code> 里。部分邮箱需要先在网页版设置中开启 SMTP，向导里有说明。不要把填好的 <code>.env</code> 发给别人。
</details>

<details>
<summary><b>学院网站抓不到？</b></summary>

学院官网基本爬不下来，请不要依赖「一键抓取」。打开师资页后按 <code>Ctrl+A</code> 全选、<code>Ctrl+C</code> 复制，再到「师资名单」页 <code>Ctrl+V</code> 粘贴，让模型按 <b>学校、学院、导师名、邮箱、职称、方向</b> 的顺序帮你整理，核对后再勾选。
</details>

<details>
<summary><b>老师没有邮箱？</b></summary>

勾选后点「补全已勾选老师的主页信息」，程序会尝试从个人主页查找（单次有上限）。
</details>

<details>
<summary><b>发送有限制吗？</b></summary>

逐封间隔 120 秒，批量间隔 60 秒。每日上限见 <code>config/settings.yaml</code>。短时间大量发送仍可能触发邮箱风控。
</details>

<details>
<summary><b>出问题怎么反馈？</b></summary>

「材料与配置」页可以导出 <code>app.log</code>。日志只记录操作和报错，不含邮件正文。
</details>

## 手动配置（可选）

也可以直接改这些文件：

| 文件 | 内容 |
|---|---|
| `.env` | 大模型 API Key、邮箱密码（不要发给任何人） |
| `config/profile.yaml` | 个人信息与经历（已被 gitignore） |
| `Template/template` | 邮件底稿，请保留四个花括号空位 |
| `config/schools.yaml` | 各学院师资页 URL |
| `config/settings.yaml` | 抓取与发送参数 |

命令行：`python cli.py fetch` / `draft` / `send` / `status`。

日常启动也可以：

```powershell
python -m streamlit run app.py
```

## 免责

本工具用于帮助你给真正相关的老师写**个性化**自荐信。请勿用于垃圾邮件或营销群发。因滥用导致邮箱被限制的后果由使用者自行承担。

## License

[MIT](LICENSE) © 2026 LetterFit
