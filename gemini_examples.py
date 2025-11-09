"""
Gemini 视频理解系统 - 快速使用示例
"""

# 示例1: 最简单的使用方式 - 视频描述
def example_basic():
    """基础示例: 描述视频内容"""
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    
    config = GeminiConfig()
    config.GEMINI_API_KEY = "your-api-key-here"
    config.model = "gemini-2.5-flash"
    config.video_path = "./test/考核点1：活动状态识别/画画2.mov"
    config.prompt = "请用3句话描述这个视频的内容"
    
    processor = GeminiVideoProcessor(config)
    response, timings = processor.process_video(config.video_path, config.prompt)
    print(f"AI回答: {response}")
    print(f"耗时: {timings['total_time']:.2f}秒")


# 示例2: 活动分类 (JSON格式输出)
def example_activity_classification():
    """活动分类示例"""
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    
    config = GeminiConfig()
    config.GEMINI_API_KEY = "your-api-key-here"
    config.model = "gemini-2.5-flash"
    config.video_path = "./test/考核点1：活动状态识别/运动3.mov"
    config.prompt = """
    分析这个视频中儿童的活动，从以下类别选择: ['画画', '做手工', '过家家', '运动']
    
    请以JSON格式返回:
    {
        "activity_label": "类别名称",
        "content_description": "详细描述视频内容",
        "key_objects": ["物体1", "物体2"]
    }
    """
    
    processor = GeminiVideoProcessor(config)
    response, _ = processor.process_video(config.video_path, config.prompt)
    
    # 解析JSON
    import json
    result = json.loads(response)
    print(f"活动类别: {result['activity_label']}")
    print(f"内容描述: {result['content_description']}")


# 示例3: 时间戳问答
def example_timestamp_qa():
    """时间戳问答示例"""
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    
    config = GeminiConfig()
    config.GEMINI_API_KEY = "your-api-key-here"
    config.video_path = "./your-video.mp4"
    config.prompt = """
    请回答以下问题:
    1. 在 00:10 的时候发生了什么?
    2. 在 00:30 的时候画面中有什么物体?
    3. 从 00:45 到 01:00 之间发生了什么变化?
    """
    
    processor = GeminiVideoProcessor(config)
    response, _ = processor.process_video(config.video_path, config.prompt)
    print(response)


# 示例4: YouTube 视频分析
def example_youtube():
    """YouTube视频分析示例"""
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    
    config = GeminiConfig()
    config.GEMINI_API_KEY = "your-api-key-here"
    config.support_youtube = True
    config.video_path = "https://www.youtube.com/watch?v=VIDEO_ID"
    config.prompt = "请总结这个视频的主要内容，包括关键事件和亮点"
    
    processor = GeminiVideoProcessor(config)
    response, _ = processor.process_video(config.video_path, config.prompt)
    print(response)


# 示例5: 自定义视频处理参数
def example_custom_processing():
    """自定义处理参数示例"""
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    
    config = GeminiConfig()
    config.GEMINI_API_KEY = "your-api-key-here"
    config.model = "gemini-2.5-pro"  # 使用更强大的模型
    config.video_path = "./long-video.mp4"
    
    # 自定义处理参数
    config.video_fps = 2  # 每秒2帧 (捕捉更多细节)
    config.video_start_offset = "10s"  # 从第10秒开始
    config.video_end_offset = "60s"  # 到第60秒结束
    config.media_resolution = "low"  # 低分辨率 (节省成本)
    
    config.prompt = "详细分析这段视频中的活动和交互"
    
    processor = GeminiVideoProcessor(config)
    response, timings = processor.process_video(config.video_path, config.prompt)
    print(response)


# 示例6: 批量处理多个视频
def example_batch_processing():
    """批量处理示例"""
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    import os
    
    config = GeminiConfig()
    config.GEMINI_API_KEY = "your-api-key-here"
    config.model = "gemini-2.5-pro"
    config.prompt = "用一句话描述这个视频的主要活动"
    
    processor = GeminiVideoProcessor(config)
    
    # 批量处理文件夹中的视频
    video_folder = "./test/考核点1：活动状态识别/"
    video_files = [f for f in os.listdir(video_folder) if f.endswith('.mov')]
    
    results = []
    for video_file in video_files:
        video_path = os.path.join(video_folder, video_file)
        response, _ = processor.process_video(video_path, config.prompt)
        results.append({
            'file': video_file,
            'response': response
        })
    
    # 输出结果
    for result in results:
        print(f"{result['file']}: {result['response']}")


# 示例7: 使用配置文件
def example_with_config_file():
    """使用配置文件示例"""
    from main_gemini import GeminiConfig, run_single_video
    
    # 会自动从 config_gemini.yml 加载配置
    config = GeminiConfig(config_path='./config_gemini.yml')
    run_single_video(config)


# 示例8: 场景转换检测
def example_scene_detection():
    """场景转换检测示例"""
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    
    config = GeminiConfig()
    config.GEMINI_API_KEY = "your-api-key-here"
    config.video_path = "./your-video.mp4"
    config.video_fps = 1  # 每秒1帧
    config.prompt = """
    分析这个视频中的场景转换:
    1. 识别所有主要场景
    2. 标注每个场景的大致时间范围 (使用 MM:SS 格式)
    3. 描述每个场景的主要内容
    
    请以JSON格式返回:
    {
        "scenes": [
            {
                "start_time": "00:00",
                "end_time": "00:30",
                "description": "场景描述"
            }
        ]
    }
    """
    
    processor = GeminiVideoProcessor(config)
    response, _ = processor.process_video(config.video_path, config.prompt)
    print(response)


# 示例9: 性能对比测试
def example_performance_comparison():
    """性能对比示例"""
    from main_gemini import GeminiConfig, GeminiVideoProcessor
    
    video_path = "./test-video.mp4"
    prompt = "描述这个视频的内容"
    
    configs = [
        ("Flash + 低分辨率", "gemini-2.5-flash", "low", 1),
        ("Flash + 标准分辨率", "gemini-2.5-flash", "default", 1),
        ("Pro + 标准分辨率", "gemini-2.5-pro", "default", 1),
        ("Flash + 高FPS", "gemini-2.5-flash", "default", 2),
    ]
    
    for name, model, resolution, fps in configs:
        config = GeminiConfig()
        config.GEMINI_API_KEY = "your-api-key-here"
        config.model = model
        config.media_resolution = resolution
        config.video_fps = fps
        config.video_path = video_path
        
        processor = GeminiVideoProcessor(config)
        response, timings = processor.process_video(video_path, prompt)
        
        print(f"\n{name}:")
        print(f"  耗时: {timings['total_time']:.2f}秒")
        print(f"  回答长度: {len(response)}字符")


# 示例10: 完整的评估流程
def example_full_evaluation():
    """完整评估流程示例"""
    from main_gemini import GeminiConfig, run_evaluator
    
    config = GeminiConfig()
    config.GEMINI_API_KEY = "your-api-key-here"
    config.model = "gemini-2.5-flash"
    
    # 设置评估模式
    config.evaluator = {
        'enabled': True,
        'dataset_path': './test/考核点1：活动状态识别/',
        'results_path': './eval_results_gemini.json'
    }
    
    # 设置分类提示词
    config.prompt = """
    分析视频中的儿童活动，从以下类别中选择: ['画画', '做手工', '过家家', '运动']
    
    请以JSON格式返回:
    {
        "activity_label": "类别名称",
        "content_description": "详细描述"
    }
    """
    
    # 运行评估
    run_evaluator(config)
    
    # 读取并显示结果
    import json
    with open(config.evaluator['results_path'], 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    print(f"\n总体准确率: {results['accuracy']:.2f}%")
    print("\n各类准确率:")
    for label, stats in results['per_class'].items():
        print(f"  {label}: {stats['accuracy']:.2f}%")


if __name__ == '__main__':
    print("Gemini 视频理解系统 - 使用示例")
    print("\n请取消注释下面的某个示例来运行:")
    print("\n# 基础示例")
    # example_basic()
    
    print("\n# 活动分类")
    # example_activity_classification()
    
    print("\n# 时间戳问答")
    # example_timestamp_qa()
    
    print("\n# YouTube视频")
    # example_youtube()
    
    print("\n# 自定义处理")
    # example_custom_processing()
    
    print("\n# 批量处理")
    # example_batch_processing()
    
    print("\n# 使用配置文件")
    # example_with_config_file()
    
    print("\n# 场景检测")
    # example_scene_detection()
    
    print("\n# 性能对比")
    # example_performance_comparison()
    
    print("\n# 完整评估")
    # example_full_evaluation()
