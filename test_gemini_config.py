"""测试 Gemini 配置是否正确"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

try:
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    
    logger.info("✓ 导入模块成功")
    
    # 加载配置
    config = GeminiConfig()
    logger.info(f"✓ 配置加载成功")
    logger.info(f"  - API Key: {config.GEMINI_API_KEY[:20]}...")
    logger.info(f"  - 模型: {config.model}")
    logger.info(f"  - API Base URL: {config.api_base_url}")
    logger.info(f"  - API Endpoint: {config.api_endpoint}")
    logger.info(f"  - 验证 SSL: {config.verify_ssl}")
    logger.info(f"  - 视频路径: {config.video_path}")
    
    # 初始化处理器
    logger.info("\n初始化 Gemini 客户端...")
    processor = GeminiVideoProcessor(config)
    logger.info("✓ Gemini 客户端初始化成功")
    
    logger.info("\n✅ 所有测试通过！配置正确。")
    
except Exception as e:
    logger.error(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
