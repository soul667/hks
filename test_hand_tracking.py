"""
手部追踪测试示例
使用摄像头实时演示手部追踪和轨迹绘制
"""

import cv2
import mediapipe as mp
import numpy as np
from collections import deque
import time


def test_webcam():
    """使用摄像头测试手部追踪"""
    print("=================================")
    print("手部追踪 - 摄像头测试")
    print("=================================")
    print("按 'q' 退出，按 'c' 清除轨迹")
    print()
    
    # 初始化 MediaPipe
    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles
    
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    
    # 轨迹存储
    trails = {}
    max_trail_length = 30  # 保存最近30个点
    
    # 颜色
    colors = {
        'Left': (255, 0, 0),   # 蓝色
        'Right': (0, 0, 255),  # 红色
    }
    
    # 打开摄像头
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("错误：无法打开摄像头")
        return
    
    # 设置摄像头分辨率
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    frame_count = 0
    start_time = time.time()
    
    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                print("警告：无法读取帧")
                continue
            
            frame_count += 1
            
            # 镜像翻转
            frame = cv2.flip(frame, 1)
            
            # 转换为RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 处理
            results = hands.process(frame_rgb)
            
            height, width, _ = frame.shape
            current_hands = set()
            
            # 检测手部
            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                    hand_label = handedness.classification[0].label
                    hand_id = f"{hand_label}_{handedness.classification[0].index}"
                    current_hands.add(hand_id)
                    
                    # 绘制骨架
                    mp_drawing.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style()
                    )
                    
                    # 获取手腕位置
                    wrist = hand_landmarks.landmark[0]
                    x = int(wrist.x * width)
                    y = int(wrist.y * height)
                    
                    # 初始化轨迹
                    if hand_id not in trails:
                        trails[hand_id] = deque(maxlen=max_trail_length)
                    
                    # 添加点
                    trails[hand_id].append((x, y))
                    
                    # 绘制中心点
                    color = colors.get(hand_label, (255, 255, 255))
                    cv2.circle(frame, (x, y), 8, color, -1)
                    cv2.circle(frame, (x, y), 10, (255, 255, 255), 2)
                    
                    # 标注
                    cv2.putText(frame, hand_label, (x + 15, y - 15),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            # 绘制轨迹
            for hand_id, trail in list(trails.items()):
                if len(trail) < 2:
                    continue
                
                # 如果手消失了，逐渐减少轨迹点
                if hand_id not in current_hands:
                    if len(trail) > 0:
                        trail.popleft()
                    if len(trail) == 0:
                        del trails[hand_id]
                        continue
                
                # 绘制轨迹线
                points = np.array(list(trail), dtype=np.int32)
                
                # 根据手确定颜色
                if 'Left' in hand_id:
                    color = colors['Left']
                else:
                    color = colors['Right']
                
                # 绘制渐变轨迹
                for i in range(len(points) - 1):
                    alpha = (i + 1) / len(points)  # 越新越明显
                    fade_color = tuple(int(c * alpha) for c in color)
                    thickness = max(1, int(3 * alpha))
                    cv2.line(frame, tuple(points[i]), tuple(points[i + 1]), 
                           fade_color, thickness)
            
            # 计算FPS
            elapsed_time = time.time() - start_time
            fps = frame_count / elapsed_time if elapsed_time > 0 else 0
            
            # 显示信息
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Hands: {len(current_hands)}", (10, 60),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, "Press 'q' to quit, 'c' to clear", (10, height - 20),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            
            # 显示
            cv2.imshow('Hand Tracking Test', frame)
            
            # 按键处理
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("退出...")
                break
            elif key == ord('c'):
                print("清除轨迹")
                trails.clear()
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        hands.close()
    
    print(f"\n总帧数: {frame_count}")
    print(f"平均 FPS: {fps:.2f}")
    print("测试完成！")


if __name__ == '__main__':
    try:
        test_webcam()
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
