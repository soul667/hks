"""
使用 MediaPipe 追踪手部轨迹
对于视频中的每一帧，绘制其在一秒前手所在的轨迹
"""

import cv2
import mediapipe as mp
import numpy as np
from collections import deque
import os
import argparse
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HandTracker:
    """手部追踪器"""
    
    def __init__(self, max_trail_seconds=1.0, min_detection_confidence=0.5, min_tracking_confidence=0.5):
        """
        初始化手部追踪器
        
        Args:
            max_trail_seconds: 轨迹显示的最大时长（秒）
            min_detection_confidence: 最小检测置信度
            min_tracking_confidence: 最小追踪置信度
        """
        self.max_trail_seconds = max_trail_seconds
        
        # 初始化 MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,  # 最多追踪2只手
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )
        
        # 存储手部轨迹，每只手一个队列
        # 格式: {hand_id: deque([(x, y, timestamp), ...])}
        self.trails = {}
        
        # 颜色配置（BGR格式）
        self.colors = {
            'Left': (255, 0, 0),   # 蓝色 - 左手
            'Right': (0, 0, 255),  # 红色 - 右手
            'trail': (0, 255, 255),  # 黄色 - 轨迹
        }
    
    def _get_hand_center(self, hand_landmarks, frame_width, frame_height):
        """计算手掌中心点（使用手腕位置）"""
        # 使用手腕（landmark 0）作为手的中心点
        wrist = hand_landmarks.landmark[0]
        x = int(wrist.x * frame_width)
        y = int(wrist.y * frame_height)
        return (x, y)
    
    def process_video(self, input_path, output_path=None):
        """
        处理视频，追踪手部并绘制轨迹
        
        Args:
            input_path: 输入视频路径
            output_path: 输出视频路径（如果为None，自动生成）
        """
        # 检查输入文件
        if not os.path.exists(input_path):
            logger.error(f"输入视频不存在: {input_path}")
            return
        
        # 打开视频
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            logger.error(f"无法打开视频: {input_path}")
            return
        
        # 获取视频属性
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        logger.info(f"视频信息: {width}x{height} @ {fps:.2f} FPS, 总帧数: {total_frames}")
        
        # 计算每帧对应的最大轨迹点数
        self.max_trail_frames = int(self.max_trail_seconds * fps)
        
        # 生成输出路径
        if output_path is None:
            base_name = os.path.splitext(input_path)[0]
            output_path = f"{base_name}_hand_tracking.mp4"
        
        # 创建视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        logger.info(f"开始处理视频...")
        logger.info(f"轨迹时长: {self.max_trail_seconds}秒 ({self.max_trail_frames}帧)")
        
        frame_count = 0
        current_time = 0.0
        
        try:
            while cap.isOpened():
                success, frame = cap.read()
                if not success:
                    break
                
                frame_count += 1
                current_time = frame_count / fps
                
                # 转换为RGB（MediaPipe需要）
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # 处理帧
                results = self.hands.process(frame_rgb)
                
                # 当前帧检测到的手
                current_hands = set()
                
                if results.multi_hand_landmarks and results.multi_handedness:
                    for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                        # 获取手的类型（Left/Right）
                        hand_label = handedness.classification[0].label
                        hand_id = f"{hand_label}_{handedness.classification[0].index}"
                        current_hands.add(hand_id)
                        
                        # 绘制手部骨架
                        self.mp_drawing.draw_landmarks(
                            frame,
                            hand_landmarks,
                            self.mp_hands.HAND_CONNECTIONS,
                            self.mp_drawing_styles.get_default_hand_landmarks_style(),
                            self.mp_drawing_styles.get_default_hand_connections_style()
                        )
                        
                        # 获取手掌中心点
                        center = self._get_hand_center(hand_landmarks, width, height)
                        
                        # 初始化该手的轨迹队列
                        if hand_id not in self.trails:
                            self.trails[hand_id] = deque(maxlen=self.max_trail_frames)
                        
                        # 添加当前位置到轨迹
                        self.trails[hand_id].append((center[0], center[1], current_time))
                        
                        # 绘制当前手掌中心点
                        color = self.colors.get(hand_label, (255, 255, 255))
                        cv2.circle(frame, center, 8, color, -1)
                        cv2.circle(frame, center, 10, (255, 255, 255), 2)
                        
                        # 标注手的类型
                        cv2.putText(frame, hand_label, (center[0] + 15, center[1] - 15),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                # 绘制所有手的轨迹
                for hand_id, trail in list(self.trails.items()):
                    if len(trail) < 2:
                        continue
                    
                    # 移除超过时间限制的点
                    while trail and (current_time - trail[0][2]) > self.max_trail_seconds:
                        trail.popleft()
                    
                    # 如果该手在当前帧未检测到，且轨迹为空，删除该手的记录
                    if hand_id not in current_hands and len(trail) == 0:
                        del self.trails[hand_id]
                        continue
                    
                    # 绘制轨迹
                    points = np.array([(p[0], p[1]) for p in trail], dtype=np.int32)
                    
                    # 根据时间计算渐变透明度
                    for i in range(len(points) - 1):
                        # 计算该点的年龄（0到1，0是最新的）
                        age = (current_time - trail[i][2]) / self.max_trail_seconds
                        alpha = 1.0 - age  # 新点更明显
                        
                        # 根据手的类型选择颜色
                        if 'Left' in hand_id:
                            color = self.colors['Left']
                        else:
                            color = self.colors['Right']
                        
                        # 调整颜色强度
                        fade_color = tuple(int(c * alpha) for c in color)
                        
                        # 绘制线段，线宽随时间变细
                        thickness = max(1, int(3 * alpha))
                        cv2.line(frame, tuple(points[i]), tuple(points[i + 1]), 
                               fade_color, thickness)
                
                # 添加信息文本
                info_text = f"Frame: {frame_count}/{total_frames} | Time: {current_time:.2f}s | Trail: {self.max_trail_seconds}s"
                cv2.putText(frame, info_text, (10, 30),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # 添加手的数量
                hands_count = len(current_hands)
                cv2.putText(frame, f"Hands: {hands_count}", (10, 60),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # 写入帧
                out.write(frame)
                
                # 显示进度
                if frame_count % 30 == 0:
                    progress = (frame_count / total_frames) * 100
                    logger.info(f"处理进度: {progress:.1f}% ({frame_count}/{total_frames})")
        
        finally:
            # 释放资源
            cap.release()
            out.release()
            self.hands.close()
        
        logger.info(f"✓ 处理完成！")
        logger.info(f"输出文件: {output_path}")
        logger.info(f"共处理 {frame_count} 帧")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='使用 MediaPipe 追踪手部轨迹')
    parser.add_argument('input', help='输入视频路径')
    parser.add_argument('-o', '--output', help='输出视频路径（可选）')
    parser.add_argument('-t', '--trail-time', type=float, default=1.0,
                       help='轨迹显示时长（秒），默认1.0秒')
    parser.add_argument('--min-detection', type=float, default=0.5,
                       help='最小检测置信度（0-1），默认0.5')
    parser.add_argument('--min-tracking', type=float, default=0.5,
                       help='最小追踪置信度（0-1），默认0.5')
    
    args = parser.parse_args()
    
    # 创建追踪器
    tracker = HandTracker(
        max_trail_seconds=args.trail_time,
        min_detection_confidence=args.min_detection,
        min_tracking_confidence=args.min_tracking
    )
    
    # 处理视频
    tracker.process_video(args.input, args.output)


if __name__ == '__main__':
    main()
