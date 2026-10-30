"""通过 Bark 推送签到结果，仅使用 Python 标准库。"""

import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def checkin_succeeded(result_file="checkin_result.json"):
    # 安装失败、步骤跳过等情况不能使用旧结果判为成功。
    outcome = os.getenv("CHECKIN_OUTCOME", "")
    if outcome and outcome != "success":
        return False
    try:
        result = json.loads(Path(result_file).read_text(encoding="utf-8"))
        return isinstance(result, dict) and result.get("success") is True
    except (OSError, ValueError):
        return False


def send_bark(result_file="checkin_result.json"):
    bark_url = os.getenv("BARK_URL", "").strip().rstrip("/")
    if not bark_url:
        print("未设置 BARK_URL，跳过 Bark 通知")
        return True

    try:
        parts = urlsplit(bark_url)
    except ValueError:
        print("BARK_URL 格式错误，请检查推送地址")
        return False
    if (parts.scheme not in {"https", "http"} or not parts.netloc
            or not parts.path.strip("/") or parts.query or parts.fragment
            or parts.username or parts.password):
        print("BARK_URL 格式错误，请填写包含设备 Key 的推送地址")
        return False

    success = checkin_succeeded(result_file)
    status = "成功" if success else "失败"
    payload = {
        "title": "SakuraFrp",
        "body": f"签到{status}" + ("" if success else " · 点击查看日志"),
        "group": "SakuraFrp",
        "icon": os.getenv("BARK_ICON", "").strip() or
                "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f338.png",
    }
    # 只推送结果摘要，避免将账户、模型响应、密钥或完整日志发到推送服务。
    repository = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if repository and run_id:
        github_server = os.getenv("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        payload["url"] = f"{github_server}/{repository}/actions/runs/{run_id}"

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, 4):
        request = Request(
            bark_url, data=data, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                reply = json.load(response)
            if isinstance(reply, dict) and reply.get("code") == 200:
                print("Bark 通知发送成功")
                return True
            code = reply.get("code") if isinstance(reply, dict) else None
            print(f"Bark 未确认推送成功（第 {attempt}/3 次）")
            if isinstance(code, int) and 400 <= code < 500 and code != 429:
                return False
        except HTTPError as error:
            print(f"Bark 请求失败，HTTP {error.code}（第 {attempt}/3 次）")
            if 400 <= error.code < 500 and error.code != 429:
                return False
        except (URLError, OSError, ValueError):
            # 异常信息可能包含服务器地址或请求数据，不直接输出。
            print(f"Bark 网络或响应异常（第 {attempt}/3 次）")
        if attempt < 3:
            time.sleep(2 ** attempt)
    return False


if __name__ == "__main__":
    sys.exit(0 if send_bark() else 1)
