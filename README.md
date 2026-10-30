# SakuraFrp 自动签到脚本

使用 Playwright 驱动浏览器，并通过 AI 视觉识别完成 SakuraFrp 九宫格验证码签到。

## 功能特性

- 自动登录 SakuraFrp 账户
- AI 视觉识别九宫格验证码
- 自动点击匹配的验证码格子
- 失败自动重试，默认最多 10 次
- 支持 GitHub Actions 定时执行
- 支持 Bark、邮件通知和日志归档

## 本地运行

### 1. 环境准备

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

本项目默认优先使用本机已安装的 Chrome，不需要下载 ChromeDriver，也不强制执行 `playwright install chromium`。

如果本机没有 Chrome，或希望使用 Playwright 托管浏览器，可以执行：

```bash
python -m playwright install chromium
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
SAKURAFRP_USER=your_username
SAKURAFRP_PASS=your_password

BASE_URL=https://api.example.com/v1
API_KEY=your_api_key
MODEL=your_model_name
# 必填：可使用双引号包裹多行提示词
AI_PROMPT="填写你自己的完整提示词"

MAX_RETRIES=10
HEADLESS=false
CHROME_BINARY_PATH=

# 是否将验证码图片转换为 base64（可选）
# 可接受：true/false, 1/0, yes/no, on/off
# 通过第三方适配器接入的服务可能不支持直接使用图片 URL，此时设为 true。
IMAGE_AS_BASE64=false
```

`CHROME_BINARY_PATH` 可选。留空时会自动查找系统 Chrome；如果你的 Chrome 不在默认位置，可以显式指定：

```env
CHROME_BINARY_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

Playwright 只复用 Chrome 可执行文件，不会读取你日常 Chrome 的用户目录、Cookie、历史记录或扩展。

### 3. 运行脚本

```bash
python main.py
```

## GitHub Actions 部署

工作流文件位于 `.github/workflows/sakurafrp_sign.yml`，默认每天北京时间 7:00 执行，也支持手动触发。

需要配置以下 Secrets：

| 名称 | 说明 |
| --- | --- |
| `SAKURAFRP_USER` | SakuraFrp 用户名 |
| `SAKURAFRP_PASS` | SakuraFrp 密码 |
| `BASE_URL` | OpenAI 兼容 API 地址 |
| `API_KEY` | API 密钥 |
| `MODEL` | 多模态模型名称 |

### 自定义 AI 提示词（必填）

打开仓库 `Settings → Secrets and variables → Actions → Variables → New repository variable`，新增或编辑
`AI_PROMPT`，将完整提示词直接粘贴到 Value 中，无需修改代码，也无需添加引号。
这是必填的 Repository variable，不是 Secret；账号密码和 API Key 仍放在 Secrets。
多行内容会完整保留；未填写或只包含空白时，程序会在启动浏览器前报配置错误并停止。
项目不再内置默认提示词，也不会拼接其他说明。

提示词的输出约定须与现有解析逻辑一致：返回 JSON 对象，字符串键 `"1"` 至 `"9"`
表示各格物品名称，`"10"` 表示参考图名称，所有值为字符串；匹配使用名称完全相等。
配置提示词不会改变模型服务本身的使用限制。

邮件通知为可选配置：

| 名称 | 说明 |
| --- | --- |
| `EMAIL_USERNAME` | 发件邮箱 |
| `EMAIL_PASSWORD` | 邮箱授权码或应用密码 |
| `RECEIVER_EMAIL` | 收件邮箱，默认发给自己 |
| `SMTP_SERVER` | SMTP 服务器，默认 `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 端口，默认 `587` |

Actions 使用 GitHub runner 自带 Chrome，并执行 `python -m playwright install-deps chromium` 安装 Linux 运行依赖，避免每次下载 Playwright Chromium 大包。

### Bark 通知（可选）

在仓库 `Settings → Secrets and variables → Actions → New repository secret` 中添加：

| 名称 | 说明 |
| --- | --- |
| `BARK_URL` | 包含设备 Key 的推送地址，例如 `https://api.day.app/你的设备Key`；支持自建服务器及路径前缀 |
| `BARK_ICON` | 可选，自定义通知图标的图片 URL；留空默认使用粉色樱花图标（Twemoji，CC-BY 4.0） |

地址只填到设备 Key，不附加通知标题、正文或查询参数。更换服务器时只需修改这个 Secret。
请不要将真实推送地址提交到代码、README 或日志中。

默认樱花图标由 [Twemoji](https://github.com/twitter/twemoji) 提供，图片许可为 [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)。自定义图标需要 iOS 15 或以上；首次下载超过 10 秒时，Bark 会回退到默认图标。

未配置时自动跳过 Bark。配置后，通知标题仅显示 `SakuraFrp`，正文为 `签到成功`
或 `签到失败 · 点击查看日志`，不重复显示时间与状态；
点击通知可打开本次 Actions 运行页面。推送不包含账号、密钥、模型响应或完整日志。
网络异常和限流最多尝试 3 次；网络超时重试可能产生重复通知。

签到结果写入 `checkin_result.json`，失败时进程返回非零退出码。
Bark 根据结果文件及 Actions 步骤状态判定结果，不将“通过验证码”单独视为签到成功。
如果依赖安装失败、签到步骤被跳过或结果缺失，会推送失败。
若 runner 未启动、检出代码失败或任务被强制终止，则无法保证通知送达。

本地运行时设置 `BARK_URL` 环境变量，然后依次运行 `python main.py` 和
`python send_bark.py`。通知读取当前目录中的结果文件，请在每次签到执行后发送，避免使用旧结果。

## 项目结构

```text
SakuraFrp-Qiandao/
├── .github/workflows/sakurafrp_sign.yml
├── automation.py          # Playwright 签到主流程
├── captcha_handler.py     # GeeTest 验证码识别和点击
├── config.py              # 环境变量和日志配置
├── human_simulator.py     # 简单人类操作模拟
├── main.py                # 程序入口
├── send_email.py          # 邮件通知
├── send_bark.py           # Bark 结果通知
├── requirements.txt       # Python 依赖
└── README.md
```

## 配置说明

### 定时任务时间

修改 `.github/workflows/sakurafrp_sign.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '0 23 * * *'  # UTC 前一天 23:00 = 北京时间次日 7:00
```

常用时间对照：
- `0 23 * * *` - 每天 7:00（北京时间，当前默认）
- `0 1 * * *` - 每天 9:00（北京时间）
- `0 13 * * *` - 每天 21:00（北京时间）
- `0 1,13 * * *` - 每天 9:00 和 21:00

### AI 模型推荐

支持任何兼容 OpenAI API 的多模态模型：

- 阿里通义: `qwen-vl-plus`, `qwen-vl-max`
- 智谱 AI: `glm-4v`
- GitHub Copilot: 可通过第三方 OpenAI 兼容适配层接入
- ~~ModelScope: 各种开源视觉模型~~，鉴于魔搭社区在2026/8/6改为魔粒机制，需要每天登录才能获取魔粒使用模型，现已不推荐魔搭社区。
- 可以使用智谱官网的免费视觉模型`GLM-4.6V-Flash`，但有时候高峰期会429，推荐使用`GLM-4.1V-Thinking-Flash`,效果差不多。

## 故障排查

### 验证码识别失败

尝试更换更强的视觉模型，或增加 `MAX_RETRIES`。模型需要支持图片输入，并兼容 OpenAI Chat Completions API。

### 模型返回非标准响应

脚本会记录完整响应结构。如果响应中包含 `error` 或 `errors`，会直接终止，因为刷新验证码无法修复模型 API 错误。

### Playwright 下载 Chromium 失败

如果出现 `timed out`、`ECONNRESET` 或 `Failed to download Chrome for Testing`，通常是网络到 Playwright/CDN 下载源不稳定。推荐直接使用系统 Chrome，并在 `.env` 中按需设置 `CHROME_BINARY_PATH`。

### 登录失败

检查 `SAKURAFRP_USER` 和 `SAKURAFRP_PASS` 是否正确，必要时关闭无头模式查看页面行为：

```env
HEADLESS=false
```

### 未收到邮件

确认邮箱开启 SMTP，并使用授权码或应用专用密码，不要直接使用普通登录密码。

## 注意事项

请勿频繁触发签到，避免被限流。妥善保管账号密码、API Key 和邮箱授权码。

## 相关链接

- [SakuraFrp 官网](https://www.natfrp.com/)
- [Playwright 文档](https://playwright.dev/python/)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [copilot-api](https://github.com/caozhiyuan/copilot-api)
- [LiteLLM](https://github.com/BerriAI/litellm)
