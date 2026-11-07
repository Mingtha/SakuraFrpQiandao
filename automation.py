import logging
import os
import shutil
import time
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from config import Config
from captcha_handler import ModelApiError

logger = logging.getLogger(__name__)


class CheckInAutomation:
    """签到自动化主类"""
    def __init__(self, config: Config):
        self.config = config
        from captcha_handler import CaptchaHandler
        self.captcha_handler = CaptchaHandler(config)
        from human_simulator import HumanSimulator
        self.simulator = HumanSimulator()
        self.max_retries = config.max_retries
    
    def run(self) -> bool:
        """执行签到流程"""
        # GitHub Actions 环境自动使用 headless 模式
        headless = os.getenv('CI') == 'true' or os.getenv('HEADLESS', 'false').lower() == 'true'

        with sync_playwright() as playwright:
            browser = None
            try:
                logger.info("正在初始化 Playwright Chromium...")
                launch_options = {
                    "headless": headless,
                    "args": [
                        "--window-size=1280,800",
                        "--disable-blink-features=AutomationControlled",
                        "--no-proxy-server",
                        "--lang=zh-CN",
                        "--disable-gpu",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                }
                chrome_path = self._resolve_chrome_path()
                if chrome_path:
                    logger.info(f"使用 Chrome 路径: {chrome_path}")
                    launch_options["executable_path"] = chrome_path

                browser = playwright.chromium.launch(**launch_options)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                )
                page = context.new_page()
                page.set_default_timeout(20000)

                # 步骤1: 登录
                if not self._login(page):
                    logger.error("登录失败")
                    return False

                # 步骤2: 跳转到 处理年龄
                if not self._navigate_to_sakurafrp(page):
                    logger.error("跳转到 SakuraFrp 失败")
                    return False

                # 步骤3: 执行签到
                if not self._perform_checkin(page):
                    logger.error("签到失败")
                    page.screenshot(path="error_screenshot.png", full_page=True)
                    with open("error_page_source.html", "w", encoding="utf-8") as f:
                        f.write(page.content())
                    return False

                logger.info("✓ 签到流程完成")
                return True

            except ModelApiError:
                logger.error("模型 API 调用失败，终止签到流程")
                return False
            except Exception as e:
                logger.error(f"执行过程中发生错误: {e}", exc_info=True)
                return False
            finally:
                if browser:
                    try:
                        browser.close()
                    except PlaywrightError:
                        logger.warning("关闭浏览器失败")
                logger.info("脚本执行完毕")

    def _resolve_chrome_path(self):
        """优先使用环境变量指定的 Chrome，其次查找系统 Chrome。"""
        if self.config.chrome_binary_path and os.path.exists(self.config.chrome_binary_path):
            return self.config.chrome_binary_path

        candidate_paths = [
            os.path.join(
                os.environ.get("PROGRAMFILES", ""),
                "Google",
                "Chrome",
                "Application",
                "chrome.exe",
            ),
            os.path.join(
                os.environ.get("PROGRAMFILES(X86)", ""),
                "Google",
                "Chrome",
                "Application",
                "chrome.exe",
            ),
            os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Google",
                "Chrome",
                "Application",
                "chrome.exe",
            ),
        ]

        for executable in ("google-chrome", "google-chrome-stable", "chrome", "chromium"):
            found = shutil.which(executable)
            if found:
                return found

        for path in candidate_paths:
            if path and os.path.exists(path):
                return path

        return None

    def _login(self, page: Page) -> bool:
        """执行登录"""
        login_url = "https://www.natfrp.com/user/"
        logger.info(f"导航到登录页面: {login_url}")
        page.goto(login_url, wait_until="domcontentloaded")

        try:
            # 输入用户名和密码
            username_input = page.locator("#username")
            password_input = page.locator("#password")
            username_input.wait_for(state="visible")
            password_input.wait_for(state="visible")

            logger.info("输入登录凭据...")
            username_input.fill("")
            self.simulator.type_text(username_input, self.config.sakurafrp_user)
            password_input.fill("")
            self.simulator.type_text(password_input, self.config.sakurafrp_pass)

            # 点击登录按钮
            login_button = page.locator("#login")
            login_button.wait_for(state="visible")
            logger.info("点击登录按钮...")
            login_button.click()

            page.wait_for_url("https://www.natfrp.com/user/**", timeout=60000)
            self._wait_for_dashboard(page)
            logger.info("登录成功")
            return True

        except PlaywrightTimeoutError:
            logger.error("登录页面元素加载超时")
            return False
        except Exception as e:
            logger.error(f"登录过程出错: {e}", exc_info=True)
            return False

    def _wait_for_dashboard(self, page: Page):
        """等待真实业务元素，避免把登录后的固定延时当成登录成功。"""
        candidates = (
            page.locator(".adult-check"),
            page.get_by_role("button", name="点击这里签到", exact=True),
            page.get_by_text("今天已经签到过啦", exact=False).first,
        )
        deadline = time.monotonic() + 60
        while True:
            if any(candidate.is_visible() for candidate in candidates):
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PlaywrightTimeoutError("等待 SakuraFrp 仪表板超时")
            page.wait_for_timeout(min(200, remaining * 1000))

    def _dismiss_age_confirmation(self, page: Page):
        """保留原有年龄确认行为，并确认遮挡层确实消失。"""
        overlay = page.locator(".adult-check")
        if not overlay.is_visible():
            return
        logger.info("处理年龄确认弹窗...")
        # 此链接没有 href，不能依赖 ARIA link 角色。
        overlay.locator("a").filter(has_text="是，我已满18岁").click(timeout=10000)
        overlay.wait_for(state="hidden", timeout=15000)
        logger.info("年龄确认弹窗已关闭")

    def _navigate_to_sakurafrp(self, page: Page) -> bool:
        """等待仪表板加载并处理年龄确认。失败时不再误报成功。"""
        try:
            self._wait_for_dashboard(page)
            self._dismiss_age_confirmation(page)
            logger.info("SakuraFrp 仪表板已就绪")
            return True
        except PlaywrightError as e:
            logger.error(f"仪表板或年龄确认处理失败: {e}")
            return False

    def _click_checkin(self, page: Page, button):
        """只在点击阶段重试，处理检查后才出现的年龄层。"""
        deadline = time.monotonic() + 30
        while True:
            self._dismiss_age_confirmation(page)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PlaywrightTimeoutError("签到按钮在 30 秒内未能完成点击")
            try:
                button.click(timeout=min(3000, max(1, int(remaining * 1000))))
                return
            except PlaywrightTimeoutError:
                # Playwright 自动等待元素可操作；重新检查延迟出现的年龄层。
                # 不使用强制点击或移除 DOM，其他遮挡最终仍会明确失败。
                if time.monotonic() >= deadline:
                    raise

    def _wait_for_checkin_state(self, page: Page, timeout=20000):
        """同时检查成功标识和签到按钮，避免串行等待按钮超时。"""
        deadline = time.monotonic() + timeout / 1000
        while True:
            if page.get_by_text("今天已经签到过啦", exact=False).first.is_visible():
                return "done"
            if page.get_by_role("button", name="点击这里签到", exact=True).is_visible():
                return "ready"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PlaywrightTimeoutError("未找到签到按钮或已签到标识")
            page.wait_for_timeout(min(200, remaining * 1000))

    def _perform_checkin(self, page: Page) -> bool:
        """只对实际验证码处理计数，并在最后一次尝试后检查结果。"""
        attempts = 0
        try:
            while True:
                if self._wait_for_checkin_state(page) == "done":
                    logger.info("今日已签到")
                    return True
                if attempts >= self.max_retries:
                    logger.error("已达到最大验证码尝试次数，仍未确认签到成功")
                    return False

                button = page.get_by_role("button", name="点击这里签到", exact=True)
                logger.info("点击签到按钮...")
                self._click_checkin(page, button)
                self.simulator.random_sleep(2, 4)

                attempts += 1
                logger.info(f"验证码尝试 {attempts}/{self.max_retries}")
                self.captcha_handler.handle_geetest_captcha(page)

                # 提交后先等待成功标识；仍未确认时才刷新检查服务端状态。
                # 不以签到按钮还在页面上或验证码已关闭作为成功依据。
                try:
                    page.get_by_text("今天已经签到过啦", exact=False).first.wait_for(
                        state="visible", timeout=20000,
                    )
                    logger.info(f"签到成功，共尝试 {attempts} 次验证码")
                    return True
                except PlaywrightTimeoutError:
                    logger.info("暂未检测到签到成功标识，刷新页面确认结果")
                    page.reload(wait_until="domcontentloaded")
                    self._dismiss_age_confirmation(page)

        except ModelApiError:
            raise
        except PlaywrightError as e:
            logger.error(f"签到过程出错: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"签到过程出错: {e}", exc_info=True)
            return False


