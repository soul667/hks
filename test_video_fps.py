"""
测试不同的 video_fps 配置
展示如何使用灵活的帧率配置
"""

# 测试用例
test_cases = [
    # (video_fps, 描述)
    (10, "每秒10帧 - 高精度"),
    (5, "每秒5帧 - 详细分析"),
    (2, "每秒2帧 - 中等精度"),
    (1, "每秒1帧 - 推荐默认值"),
    (0.5, "每2秒1帧 - 低成本"),
    (0.333, "每3秒1帧 - 极低成本"),
    (0.25, "每4秒1帧"),
    (0.2, "每5秒1帧 - 超长视频"),
    (0.1, "每10秒1帧 - 视频概览"),
]

# 假设视频参数
original_fps = 30  # 原始视频 30fps
durations = [10, 30, 60, 300]  # 测试不同时长的视频

print("=" * 80)
print("video_fps 配置效果预测".center(80))
print("=" * 80)

for duration in durations:
    total_frames = int(original_fps * duration)
    print(f"\n📹 视频时长: {duration}秒 (原始: {original_fps}fps, 共{total_frames}帧)")
    print("-" * 80)
    print(f"{'video_fps':<12} {'描述':<20} {'帧间隔':<10} {'提取帧数':<10} {'实际fps':<10}")
    print("-" * 80)
    
    for fps, desc in test_cases:
        if fps >= 1:
            # 每秒提取几帧
            if fps >= original_fps:
                frame_interval = 1
            else:
                frame_interval = int(original_fps / fps)
        else:
            # 每 N 秒提取 1 帧
            seconds_per_frame = 1 / fps
            frame_interval = int(original_fps * seconds_per_frame)
        
        frame_interval = max(1, frame_interval)
        extracted_frames = int(total_frames / frame_interval)
        actual_fps = extracted_frames / duration if duration > 0 else 0
        
        print(f"{fps:<12.3f} {desc:<20} {frame_interval:<10} {extracted_frames:<10} {actual_fps:<10.3f}")

print("\n" + "=" * 80)
print("\n💡 推荐配置：")
print("  - 短视频 (< 30秒): video_fps = 1 到 5")
print("  - 中等视频 (30秒-5分钟): video_fps = 0.5 到 2")
print("  - 长视频 (> 5分钟): video_fps = 0.2 到 1")
print("\n⚠️  注意: 帧数越多，API成本越高，处理时间越长")
print("=" * 80)
