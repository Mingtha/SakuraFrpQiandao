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
        try:
            from captcha_handler import CaptchaHandler
        except ImportError:
            from captcha_handler import CaptchaHandler  # 如果模块名不同
        self.captcha_handler = CaptchaHandler(config)
        try:
            from human_simulator import HumanSimulator
        except ImportError:
            from human_simulator import HumanSimulator  # 如果模块名不同
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
                if browser and headless:
                    browser.close()
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

            self.simulator.random_sleep(3, 5)
            logger.info("登录成功")
            return True

        except PlaywrightTimeoutError:
            logger.error("登录页面元素加载超时")
            return False
        except Exception as e:
            logger.error(f"登录过程出错: {e}", exc_info=True)
            return False

    def _navigate_to_sakurafrp(self, page: Page) -> bool:
        """跳转到 SakuraFrp 仪表板"""
        try:
            # 点击 SakuraFrp 链接
            # sakura_link = page.locator("div.action-list a", has_text="Sakura Frp")
            # logger.info("点击 SakuraFrp 跳转链接...")
            # sakura_link.click()
            # self.simulator.random_sleep(2, 4)

            # 处理年龄确认弹窗（如果存在）
            try:
                age_confirm = page.locator("div.yes a", has_text="是，我已满18岁")
                age_confirm.wait_for(state="visible", timeout=5000)
                logger.info("处理年龄确认弹窗...")
                age_confirm.click()
                self.simulator.random_sleep(2, 3)
            except PlaywrightTimeoutError:
                logger.info("未检测到年龄确认弹窗")

            logger.info("成功跳转到 SakuraFrp 仪表板")
            return True

        except PlaywrightTimeoutError:
            logger.warning("SakuraFrp 跳转链接未找到，可能已在目标页面")
            return True
        except Exception as e:
            logger.error(f"跳转过程出错: {e}", exc_info=True)
            return False

    def _perform_checkin(self, page: Page) -> bool:

        """执行签到操作"""
        for attempt in range(1, self.max_retries+1):
            logger.info(f"验证码尝试 {attempt}/{self.max_retries}")
            try:
                # 查找签到按钮
                check_in_button = None
                try:
                    check_in_button = page.locator("button", has_text="点击这里签到")
                    check_in_button.wait_for(state="visible")
                    logger.info("找到签到按钮")
                except PlaywrightTimeoutError:
                    # 检查是否已签到
                    try:
                        page.locator("p", has_text="今天已经签到过啦").wait_for(
                            state="visible",
                            timeout=2000,
                        )
                        logger.info("今日已签到")
                        return True
                    except PlaywrightTimeoutError:
                        logger.error("未找到签到按钮或已签到标识")
                        return False

                # 点击签到按钮
                if check_in_button:
                    logger.info("点击签到按钮...")
                    check_in_button.click()
                    self.simulator.random_sleep(2, 4)

                    # 处理验证码
                    self.captcha_handler.handle_geetest_captcha(page)
                    page.reload(wait_until="domcontentloaded")
                    time.sleep(5)
                    continue

                return False

            except ModelApiError:
                raise
            except PlaywrightError as e:
                logger.error(f"签到过程出错: {e}", exc_info=True)
                return False
            except Exception as e:
                logger.error(f"签到过程出错: {e}", exc_info=True)
                return False
        logger.info("已达到最大重试次数")
        return False
