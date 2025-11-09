# 手部轨迹追踪使用指南

## 概述

`hand_tracking.py` 使用 MediaPipe 对视频进行手部追踪，并在每一帧中绘制手在过去一秒内所在的轨迹。

## 功能特性

- ✅ 使用 MediaPipe Hands 进行实时手部检测和追踪
- ✅ 支持同时追踪最多 2 只手（左手和右手）
- ✅ 绘制手部骨架和关键点
- ✅ 显示手部运动轨迹（默认显示过去 1 秒的轨迹）
- ✅ 轨迹颜色区分（左手蓝色，右手红色）
- ✅ 轨迹渐变效果（越近的轨迹越明显）
- ✅ 实时显示帧数、时间和检测到的手数

## 环境要求

**重要：MediaPipe 目前最高支持 Python 3.12，不支持 Python 3.13**

### 方法 1: 使用 Python 3.12 虚拟环境（推荐）

```bash
# 创建 Python 3.12 虚拟环境
python3.12 -m venv venv312

# 激活虚拟环境 (Windows PowerShell)
.\venv312\Scripts\Activate.ps1

# 安装依赖
pip install mediapipe opencv-python numpy

# 运行脚本
python hand_tracking.py <输入视频路径>
```

### 方法 2: 使用 conda（推荐）

```bash
# 创建 Python 3.12 环境
conda create -n handtrack python=3.12

# 激活环境
conda activate handtrack

# 安装依赖
pip install mediapipe opencv-python numpy

# 运行脚本
python hand_tracking.py <输入视频路径>
```

### 方法 3: 使用 pyenv（Linux/Mac）

```bash
# 安装 Python 3.12
pyenv install 3.12.7

# 设置本地 Python 版本
pyenv local 3.12.7

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install mediapipe opencv-python numpy
```

## 使用方法

### 基本使用

```bash
python hand_tracking.py <输入视频路径>
```

输出文件会自动生成，命名格式为：`原文件名_hand_tracking.mp4`

### 指定输出路径

```bash
python hand_tracking.py <输入视频> -o <输出视频>
```

### 自定义轨迹时长

```bash
# 显示过去 2 秒的轨迹
python hand_tracking.py input.mp4 -t 2.0

# 显示过去 0.5 秒的轨迹
python hand_tracking.py input.mp4 --trail-time 0.5
```

### 调整检测参数

```bash
# 调整检测和追踪的置信度阈值
python hand_tracking.py input.mp4 --min-detection 0.7 --min-tracking 0.7
```

### 完整示例

```bash
python hand_tracking.py ./test/video.mp4 \
    -o ./output/tracked_video.mp4 \
    -t 1.5 \
    --min-detection 0.6 \
    --min-tracking 0.6
```

## 参数说明

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `input` | - | 必需 | - | 输入视频文件路径 |
| `--output` | `-o` | 可选 | 自动生成 | 输出视频文件路径 |
| `--trail-time` | `-t` | float | 1.0 | 轨迹显示时长（秒） |
| `--min-detection` | - | float | 0.5 | 最小检测置信度（0-1） |
| `--min-tracking` | - | float | 0.5 | 最小追踪置信度（0-1） |

## 视觉效果说明

### 颜色编码
- 🔵 **蓝色**：左手的轨迹和标记
- 🔴 **红色**：右手的轨迹和标记
- ⚪ **白色**：手掌中心点的外圈标记
- 🦴 **绿色线条**：手部骨架连接

### 轨迹特性
- **渐变透明度**：越新的轨迹点越明显，越旧的越淡
- **渐变线宽**：越新的轨迹线越粗，越旧的越细
- **时间限制**：默认只显示过去 1 秒的轨迹点

### 信息显示
- **Frame**: 当前帧数 / 总帧数
- **Time**: 当前时间（秒）
- **Trail**: 轨迹显示时长
- **Hands**: 当前检测到的手数（0-2）

## 性能优化建议

### 对于高分辨率视频
如果视频分辨率很高（如 4K），可以考虑：

1. **降低输入分辨率**：
```python
# 在代码中添加缩放
frame = cv2.resize(frame, (1280, 720))
```

2. **调整 MediaPipe 参数**：
```bash
# 降低检测置信度以提高速度
python hand_tracking.py input.mp4 --min-detection 0.3 --min-tracking 0.3
```

### 对于长视频
- 建议先用视频编辑软件剪辑出需要分析的片段
- 或者修改代码添加起止帧参数

## 常见问题

### 1. MediaPipe 安装失败
**问题**：`No matching distribution found for mediapipe`

**解决**：确保使用 Python 3.9-3.12 版本
```bash
python --version  # 检查版本
```

### 2. 手部检测不准确
**问题**：某些手部姿势无法识别

**解决**：
- 调低置信度阈值：`--min-detection 0.3 --min-tracking 0.3`
- 确保视频光照条件良好
- 手部尽量在画面中完整显示

### 3. 轨迹断断续续
**问题**：轨迹线条不连续

**解决**：
- 调低追踪置信度：`--min-tracking 0.3`
- 减少手部快速移动
- 提高视频帧率

### 4. 处理速度慢
**问题**：视频处理耗时较长

**解决**：
- 降低视频分辨率
- 减少 `max_num_hands` 参数（修改代码）
- 使用 GPU 加速（需要安装 mediapipe-gpu 版本）

## 代码自定义

### 修改追踪手数
在 `hand_tracking.py` 第 32 行修改：
```python
self.hands = self.mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,  # 改为 1 或更多
    ...
)
```

### 修改颜色方案
在 `hand_tracking.py` 第 42-46 行修改：
```python
self.colors = {
    'Left': (255, 0, 0),      # BGR 格式：蓝色
    'Right': (0, 0, 255),     # BGR 格式：红色
    'trail': (0, 255, 255),   # BGR 格式：黄色
}
```

### 使用不同的关键点
默认使用手腕（landmark 0）作为轨迹点，可以修改为其他关键点：
```python
# 在 _get_hand_center 方法中
# 0: 手腕, 8: 食指尖, 4: 大拇指尖, 12: 中指尖
landmark = hand_landmarks.landmark[8]  # 改为食指尖
```

MediaPipe 手部关键点编号：
```
0: WRIST (手腕)
1-4: THUMB (大拇指)
5-8: INDEX_FINGER (食指)
9-12: MIDDLE_FINGER (中指)
13-16: RING_FINGER (无名指)
17-20: PINKY (小指)
```

## 示例输出

处理后的视频将包含：
- ✅ 手部骨架绘制
- ✅ 手掌中心点标记
- ✅ 彩色运动轨迹
- ✅ 左/右手标签
- ✅ 帧信息和统计

## 技术细节

### MediaPipe Hands 模型
- **模型类型**：实时手部检测和关键点追踪
- **关键点数量**：21个 3D 手部关键点
- **检测范围**：最多 2 只手
- **性能**：约 30-60 FPS（取决于硬件）

### 轨迹存储
- 使用 `deque` 数据结构存储轨迹点
- 自动限制队列长度（基于帧率和时长）
- 格式：`(x, y, timestamp)`

### 渐变算法
```python
age = (current_time - point_time) / max_trail_seconds
alpha = 1.0 - age  # 0 到 1 之间
color = tuple(int(c * alpha) for c in base_color)
thickness = max(1, int(3 * alpha))
```

## 许可和引用

本脚本使用 MediaPipe 库，遵循 Apache 2.0 许可证。

如果在学术研究中使用，请引用：
```
@misc{mediapipe,
  title = {MediaPipe},
  author = {Google},
  year = {2023},
  url = {https://google.github.io/mediapipe/}
}
```

## 相关链接

- [MediaPipe 官方文档](https://google.github.io/mediapipe/)
- [MediaPipe Hands 指南](https://google.github.io/mediapipe/solutions/hands.html)
- [OpenCV 文档](https://docs.opencv.org/)

---

**提示**：如果遇到问题，请先检查 Python 版本是否为 3.9-3.12，这是使用 MediaPipe 的前提条件。
