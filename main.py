from config import Config
from automation import CheckInAutomation
import logging
import json
from pathlib import Path
import sys

logger = logging.getLogger(__name__)


def main():
    """主函数"""
    success = False
    try:
        # 加载配置
        config = Config.from_env()
        logger.info(f"使用账户: {config.sakurafrp_user}")
        
        # 执行自动签到
        automation = CheckInAutomation(config)
        success = automation.run() is True
        
    except ValueError as e:
        logger.error(f"配置错误: {e}")
    except Exception as e:
        logger.error(f"程序执行失败: {e}", exc_info=True)

    Path("checkin_result.json").write_text(
        json.dumps({"success": success}), encoding="utf-8"
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
