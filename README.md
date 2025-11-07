# Qwen Omni 视频音频处理工具

这个工具可以读取视频文件,提取视频帧和音频,然后发送给 Qwen Omni 模型进行多模态分析。

## 功能特性

- ✅ 从视频文件提取视频帧
- ✅ 从视频文件提取音频并转换为 16kHz PCM 格式
- ✅ 支持多种视频格式: **MP4, MOV, AVI, MKV, FLV, WMV, M4V**
- ✅ 支持自定义提示词
- ✅ 实时接收 AI 的文本和语音回复
- ✅ 可配置的视频帧率和分辨率

## 安装依赖

```bash
# 使用 uv 安装依赖
uv pip install dashscope pyaudio opencv-python pillow pyyaml

# 或使用 pip
pip install dashscope pyaudio opencv-python pillow pyyaml
```

**注意**: 还需要安装 FFmpeg 用于音频提取。

### 安装 FFmpeg (Windows)

1. 下载 FFmpeg: https://www.gyan.dev/ffmpeg/builds/
2. 解压到某个目录,例如 `C:\ffmpeg`
3. 将 `C:\ffmpeg\bin` 添加到系统 PATH 环境变量
4. 验证安装: `ffmpeg -version`

## 配置文件

编辑 `config.yml` 文件:

```yaml
DASHSCOPE_API_KEY: "your-api-key-here"  # 必填:你的 API Key
video_path: "./input.mov"  # 输入视频文件路径 (支持: mp4, mov, avi, mkv, flv, wmv, m4v)
prompt: "请描述这个视频的内容"  # 提示词
video_fps: 1  # 每秒提取的帧数
video_max_width: 640  # 视频帧最大宽度
```

## 支持的视频格式

- **MP4** (.mp4) - 推荐格式
- **MOV** (.mov) - QuickTime 格式,完全支持
- **AVI** (.avi) - Windows 常用格式
- **MKV** (.mkv) - Matroska 容器格式
- **FLV** (.flv) - Flash 视频格式
- **WMV** (.wmv) - Windows Media 格式
- **M4V** (.m4v) - iTunes 格式

> **注意**: 确保已安装 FFmpeg,它会自动处理各种视频格式的音频提取。

## 使用方法

1. 将你的 API Key 填入 `config.yml`
2. 将要处理的视频文件路径配置到 `video_path` (支持相对路径和绝对路径)
   ```yaml
   video_path: "./my_video.mov"  # MOV 格式
   # 或
   video_path: "./videos/demo.mp4"  # MP4 格式
   # 或
   video_path: "C:/Users/Videos/test.avi"  # 绝对路径
   ```
3. 运行程序:

```bash
uv run main.py
# 或
python main.py
```

## 工作流程

1. **提取媒体**: 从视频文件提取视频帧和音频 (支持 MP4, MOV, AVI 等多种格式)
2. **连接服务器**: 建立 WebSocket 连接到 Qwen Omni 服务
3. **发送数据**: 
   - 发送所有视频帧 (每秒 N 帧,可配置)
   - 发送完整音频数据
   - 发送提示词
4. **接收响应**: 实时接收 AI 的文本和语音回复
5. **播放音频**: 通过扬声器播放 AI 的语音回复

## 配置说明

### 视频配置
- `video_fps`: 每秒提取的帧数 (1 = 每秒 1 帧)
- `video_max_width`: 视频帧最大宽度 (像素)

### 音频配置
- `audio_sample_rate`: 音频采样率 (16000 Hz)
- `sample_rate`: 输出音频采样率 (24000 Hz)

### 模型配置
- `model`: 使用的模型名称
- `voice`: AI 回复的语音音色
- `prompt`: 发送给 AI 的提示词

## 示例提示词

```yaml
prompt: "请详细描述这个视频的内容,包括画面和声音"
prompt: "这个视频在说什么?请总结主要内容"
prompt: "分析视频中的场景和对话内容"
```

## 注意事项

1. 确保视频文件路径正确
2. 视频文件不要太大 (建议 < 100MB)
3. 需要稳定的网络连接
4. 确保已安装 FFmpeg (用于音频提取)
5. **MOV 格式**: iPhone/Mac 录制的视频通常是 MOV 格式,完全支持
6. 中文路径支持: 支持包含中文的文件路径

## 故障排除

### FFmpeg 未找到
```
Error: ffmpeg not found
```
解决: 安装 FFmpeg 并添加到 PATH

### 无法打开视频文件
```
Cannot open video file
```
解决: 检查视频文件路径是否正确

### API Key 错误
```
Authorization failed
```
解决: 检查 config.yml 中的 API Key 是否正确
