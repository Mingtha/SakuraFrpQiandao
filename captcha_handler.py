import logging
import time
import random
import json
import re
from typing import Optional, Dict

from openai import OpenAI
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from config import Config

logger = logging.getLogger(__name__)


class ModelApiError(Exception):
    """模型 API 错误，属于不可重试错误。"""


class CaptchaHandler:
    """验证码处理器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key
        )

    def get_img(self, page: Page):
        try:
            # 获取验证码图片
            captcha_img_element = page.locator(".geetest_tip_img")
            captcha_img_element.wait_for(state="visible", timeout=10000)

            # 获取 CSS 属性
            bg_style = captcha_img_element.evaluate(
                "el => window.getComputedStyle(el).backgroundImage"
            )

            # 正则匹配
            match = re.search(r'url\(["\']?(.*?)["\']?\)', bg_style)
            if match:
                img_url = match.group(1)
                logger.info(f"成功获取验证码图片 URL: {img_url}")
                return img_url
            else:
                logger.error("无法提取验证码图片 URL")
                return ""
        except PlaywrightTimeoutError:
                logger.info("未检测到 GeeTest 验证码窗口")
                return False

    def handle_geetest_captcha(self, page: Page) -> bool:
        """处理 GeeTest 九宫格验证码（带重试机制）"""
        logger.info("开始处理 GeeTest 验证码...")

        try:
            # 获取验证码图片
            img_url = self.get_img(page)
            if not img_url:
                logger.error("图片获取失败，刷新网页重试...")
                time.sleep(2)
                return False
            
            # 调用视觉模型识别，imagebase64 由配置控制
            recognition_result = self._recognize_captcha(img_url, imagebase64=self.config.image_as_base64)
            if not recognition_result:
                logger.warning("识别失败，刷新网页重试...")
                time.sleep(2)
                return False
            
            logger.info(f"验证码识别结果: {recognition_result}")

            # 根据识别结果点击相应的九宫格
            if not self._click_captcha_items(page, recognition_result):
                logger.warning("点击失败，刷新网页重试...")
                time.sleep(2)
                return False

            logger.warning("验证码流程完成，刷新网页验证是否成功...")
            time.sleep(2)
            return True
        except ModelApiError:
            raise
        except Exception as e:
            logger.error(f"处理验证码时发生错误: {e}", exc_info=True)
            return False

    def _recognize_captcha(self, img_url: str, imagebase64: bool = False) -> Optional[Dict]:
        """使用视觉模型识别验证码，支持 imagebase64 方式"""
        try:
            prompt = self.config.ai_prompt
            image_url_value = img_url
            if imagebase64:
                import requests, base64
                try:
                    resp = requests.get(img_url)
                    resp.raise_for_status()
                    img_bytes = resp.content
                    img_b64 = base64.b64encode(img_bytes).decode('utf-8')
                    image_url_value = f"data:image/jpeg;base64,{img_b64}"
                except Exception as e:
                    logger.error(f"图片转base64失败: {e}")
                    raise ModelApiError("图片转base64失败") from e
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {'type': 'image_url', 'image_url': {'url': image_url_value}}
                    ]
                }],
                stream=False
            )
        
            response_data = response.model_dump() if hasattr(response, "model_dump") else {}
            logger.debug(f"模型完整响应: {response_data}")

            for error_key in ("error", "errors"):
                if response_data.get(error_key):
                    logger.error(f"模型 API 返回错误: {response_data[error_key]}")
                    raise ModelApiError("模型 API 返回错误")

            choices = response_data.get("choices") or []
            if not choices:
                logger.error(f"模型 API 返回非标准成功响应，缺少 choices: {response_data}")
                raise ModelApiError("模型 API 返回非标准成功响应")

            result_content = choices[0].get("message", {}).get("content")
            if not result_content:
                logger.error(f"模型 API 响应缺少 message.content: {response_data}")
                raise ModelApiError("模型 API 响应缺少 message.content")

            logger.info(f"模型原始输出: {result_content}")
            json_text = self._extract_json(result_content)
            if not json_text:
                logger.error("无法从模型输出中提取有效 JSON")
                raise ModelApiError("模型输出不包含有效 JSON")

            cleaned_str = json_text.replace("'", '"').strip()
        
            result_dict = json.loads(cleaned_str)
            if isinstance(result_dict, dict) and result_dict.get("error"):
                logger.error(f"模型 API 返回错误: {result_dict['error']}")
                raise ModelApiError("模型 API 返回错误")

            return result_dict

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            raise ModelApiError("模型输出 JSON 解析失败") from e
        except Exception as e:
            if isinstance(e, ModelApiError):
                raise
            status_code = getattr(e, "status_code", None)
            if status_code:
                logger.error(f"模型 API 调用失败，HTTP {status_code}: {e}")
            else:
                logger.error(f"模型 API 调用失败: {e}", exc_info=True)
            raise ModelApiError("模型 API 调用失败") from e

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """从模型输出中提取 JSON，兼容代码块、Qwen box 标记和普通说明文本。"""
        if not isinstance(text, str):
            text = str(text)

        box_match = re.search(r'<\|begin_of_box\|>(.*?)<\|end_of_box\|>', text, flags=re.DOTALL)
        if box_match:
            return box_match.group(1).strip()

        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, flags=re.DOTALL)
        if code_block_match:
            return code_block_match.group(1).strip()

        start = text.find('{')
        if start == -1:
            return None

        stack = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                stack += 1
            elif text[i] == '}':
                stack -= 1
                if stack == 0:
                    return text[start:i + 1].strip()

        return None

    def _click_captcha_items(self, page: Page, recognition_result: Dict) -> bool:
        """
        根据识别结果点击九宫格中匹配的格子

        九宫格布局（索引从1开始）：
        1  2  3
        4  5  6
        7  8  9
        
        第10个是参考图（左下角）
        """
        try:
            # 获取参考图名称（第10个元素）
            target_name = recognition_result.get("10", "").strip()
            if not target_name:
                logger.error("未能从识别结果中获取参考图名称")
                return False

            logger.info(f"目标物品: {target_name}")

            # 获取所有九宫格元素（前9个）
            grid_items = page.locator(".geetest_item")
            item_count = grid_items.count()

            # 排除最后一个（参考图），只处理前9个
            if item_count < 9:
                logger.error(f"九宫格元素数量不足，只找到 {item_count} 个")
                return False

            # 遍历前9个格子，找到匹配的物品并点击
            clicked_count = 0
            for i in range(9):
                position = i + 1  # 位置索引从1开始
                item_name = recognition_result.get(str(position), "").strip()
                
                logger.info(f"位置 {position}: {item_name}")
                
                # 如果当前格子的物品名称匹配参考图
                if item_name and item_name == target_name:
                    logger.info(f"找到匹配项！位置 {position} - {item_name}")

                    # 点击该格子
                    try:
                        grid_items.nth(i).click()
                        clicked_count += 1
                        logger.info(f"已点击位置 {position}")

                        # 点击后短暂等待，模拟人类操作
                        time.sleep(random.uniform(0.3, 0.6))

                    except Exception as e:
                        logger.error(f"点击位置 {position} 时出错: {e}")

            if clicked_count == 0:
                logger.warning(f"未找到匹配 '{target_name}' 的格子")
                return False

            logger.info(f"共点击了 {clicked_count} 个匹配的格子")

            # 点击完成后，查找并点击确认按钮
            try:
                # 等待确认按钮变为可用状态（移除 geetest_disable 类）
                confirm_button = page.locator(".geetest_commit")
                confirm_button.wait_for(state="attached", timeout=5000)

                # 检查按钮是否可用（没有 geetest_disable 类）
                button_classes = confirm_button.get_attribute("class") or ""
                logger.info(f"确认按钮状态: {button_classes}")

                # 等待按钮变为可点击状态（最多等待3秒）
                max_wait = 3
                start = time.time()
                while "geetest_disable" in (confirm_button.get_attribute("class") or ""):
                    if time.time() - start > max_wait:
                        logger.warning("确认按钮未激活，但仍尝试点击")
                        break
                    time.sleep(0.2)

                logger.info("找到确认按钮，准备点击...")
                confirm_button.click(force=True)
                logger.info("已点击确认按钮")
                time.sleep(1)
            except PlaywrightTimeoutError:
                logger.info("未找到确认按钮，可能自动提交")

            return True

        except Exception as e:
            logger.error(f"点击验证码格子时发生错误: {e}", exc_info=True)
            return False

    def _refresh_captcha(self, page: Page) -> bool:
        """刷新验证码"""
        try:
            logger.info("正在刷新验证码...")
            page.locator(".geetest_refresh").click()
            logger.info("已点击刷新按钮")
            time.sleep(1.5)  # 等待新验证码加载
            return True
        except Exception as e:
            logger.error(f"刷新验证码失败: {e}")
            return False
