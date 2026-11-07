import logging
import os
from typing import Optional
from dataclasses import dataclass, field

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('checkin.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


AI_PROMPT = "这是一个儿童画册，请按从左到右、从上到下的顺序识别每个格子里的物品名称，最后识别左下角的参考图。输出格式为JSON：{\"1\":\"名称\", \"2\":\"名称\", ..., \"10\":\"参考图名称\"}。名称要简洁，参考图名称必须是九宫格里已有的名称。若有类似物品（如气球与热气球），请统一名称。"


@dataclass
class Config:
    """配置数据类"""
    sakurafrp_user: str
    sakurafrp_pass: str = field(repr=False)
    base_url: str
    api_key: str = field(repr=False)
    model: str
    ai_prompt: str = AI_PROMPT
    chrome_binary_path: Optional[str] = None
    max_retries: int = 10
    image_as_base64: bool = False
    
    @classmethod
    def from_env(cls) -> 'Config':
        """从环境变量加载配置"""
        def get_env(key: str, required: bool = True) -> str:
            raw = os.environ.get(key, "")
            value = raw.split('\n')[0].strip()
            if required and not value:
                raise ValueError(f"环境变量 {key} 未设置或为空")
            return value

        def get_bool_env(key: str, default: bool = False) -> bool:
            raw_value = os.environ.get(key, "").strip().lower()
            if not raw_value:
                return default
            if raw_value not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
                raise ValueError(f"环境变量 {key} 必须是有效布尔值")
            return raw_value in {"1", "true", "yes", "on"}

        try:
            max_retries = int(get_env("MAX_RETRIES", required=False) or 10)
        except ValueError:
            raise ValueError("MAX_RETRIES 必须是正整数") from None
        if max_retries < 1:
            raise ValueError("MAX_RETRIES 必须是正整数")
        
        return cls(
            sakurafrp_user=get_env("SAKURAFRP_USER"),
            sakurafrp_pass=get_env("SAKURAFRP_PASS"),
            base_url=get_env("BASE_URL"),
            api_key=get_env("API_KEY"),
            model=get_env("MODEL"),
            ai_prompt=AI_PROMPT,
            chrome_binary_path=get_env("CHROME_BINARY_PATH", required=False),
            max_retries=max_retries,
            image_as_base64=get_bool_env("IMAGE_AS_BASE64", default=False)
        )

