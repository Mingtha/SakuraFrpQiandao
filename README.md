# SakuraFrp 自动签到

使用 Playwright 登录 SakuraFrp，通过视觉模型识别验证码并完成每日签到。支持 GitHub Actions 定时运行、Bark 和邮件通知。

## GitHub Actions 部署

1. Fork 本仓库，在 **Actions** 页面启用工作流。
2. 打开 **Settings → Secrets and variables → Actions → Secrets**，添加以下配置：

| Secret | 内容 |
| --- | --- |
| `SAKURAFRP_USER` | SakuraFrp 用户名 |
| `SAKURAFRP_PASS` | SakuraFrp 密码 |
| `BASE_URL` | OpenAI 兼容 API 的 Base URL |
| `API_KEY` | API 密钥 |
| `MODEL` | 支持图片输入的模型名称 |

3. 在 **Actions → SakuraFrp 自动签到 → Run workflow** 中手动运行一次，确认配置正确。

默认每天**北京时间 7:07** 执行。同一仓库的签到任务串行运行，单次上限 30 分钟。
修改时间可编辑 [签到工作流](.github/workflows/sakurafrp_sign.yml) 的 cron，例如 `7 23 * * *` 对应北京时间次日 7:07。

**识别提示词已内置在 [config.py](config.py) 的 `AI_PROMPT` 常量中，无需配置 Repository variable。原有 `AI_PROMPT` 环境变量或仓库变量不再生效。**

### 可选通知

同样添加到 Actions Secrets；不配置就自动跳过。

| Secret | 内容 / 默认值 |
| --- | --- |
| `BARK_URL` | 含设备 Key 的完整推送地址，如 `https://api.day.app/你的设备Key`；支持自建服务 |
| `BARK_ICON` | 自定义图标 URL；默认樱花图标 |
| `EMAIL_USERNAME` | 发件邮箱 |
| `EMAIL_PASSWORD` | 邮箱授权码或应用密码 |
| `RECEIVER_EMAIL` | 收件邮箱；默认发给自己 |
| `SMTP_SERVER` | 默认 `smtp.gmail.com` |
| `SMTP_PORT` | 默认 `587`（STARTTLS）；`465` 使用 SSL |

Bark 地址只填到设备 Key，不附加标题、正文或查询参数。Bark 仅推送结果摘要，点击可查看本次 Actions；邮件会附带运行日志。
两者均以本次签到结果判断成功，不以通过验证码或历史日志作为成功依据。任务未启动或被强制终止时，无法保证通知送达。

默认图标来自 [Twemoji](https://github.com/twitter/twemoji)，遵循 [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)。

## 本地运行

需要 Python 3.11+ 和 Chrome。在仓库目录中安装依赖：

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用：.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
```

创建 `.env` 文件，填写自己的配置：

```dotenv
SAKURAFRP_USER=your_username
SAKURAFRP_PASS=your_password
BASE_URL=https://api.example.com/v1
API_KEY=your_api_key
MODEL=your_vision_model
```

执行 `python main.py`。程序优先使用系统 Chrome；未安装时，可运行 `python -m playwright install chromium` 下载托管浏览器。Linux 如缺少运行依赖，执行 `python -m playwright install-deps chromium`。

本地可在 `.env` 中添加以下可选配置。已有环境变量优先于 `.env`。

| 变量 | 默认值 / 用途 |
| --- | --- |
| `MAX_RETRIES` | `10`，必须为正整数 |
| `HEADLESS` | `false`；CI 环境自动无头运行 |
| `CHROME_BINARY_PATH` | 留空自动查找；也可指定 Chrome 路径 |
| `IMAGE_AS_BASE64` | `false`；模型服务不支持图片 URL 时设为 `true` |

Actions 中的 `IMAGE_AS_BASE64` 可通过同名 Secret 设置。本地 `main.py` 只执行签到；通知脚本需要单独运行，并从进程环境变量读取通知配置。

## 结果与排查

- **查看结果**：`checkin.log` 保存日志，`checkin_result.json` 保存本次结果；失败返回非零退出码。Actions 运行页面的 `checkin-logs` 附件保留 7 天。
- **等待成功**：验证码处理后最多等待 20 秒，成功标识出现便结束；超时后刷新确认。尝试计数仅记录实际验证码处理。
- **登录失败**：检查账户和密码；本地可设 `HEADLESS=false` 查看页面。
- **模型报错**：检查 Base URL、密钥及模型的图片输入能力。模型 API 错误会终止流程，避免重复刷新验证码。
- **收不到邮件**：确认 SMTP 配置和邮箱授权码，查看邮件通知步骤日志。

请勿频繁触发签到；不要提交真实密码、API Key、Bark 地址或 `.env` 文件。

## 测试

```bash
python -m unittest discover -s tests -v
```

PR 和 main 分支推送会自动运行单元测试。测试模拟页面及网络，不登录真实账户、发送通知或消耗模型额度。

