# Gemini 2.5 视频理解系统使用指南

本系统基于 Google Gemini 2.5 Pro/Flash 实现视频理解功能,支持视频描述、问答、时间戳引用等多种应用场景。

## 功能特性

### 核心能力
- ✅ **视频描述与分析** - 自动生成视频内容描述
- ✅ **视频问答** - 回答关于视频内容的问题
- ✅ **时间戳引用** - 引用视频中的特定时刻 (格式: MM:SS)
- ✅ **场景识别** - 识别视频中的活动、物体、事件
- ✅ **批量评估** - 支持批量处理多个视频并统计准确率

### 视频输入方式
1. **File API 上传** (推荐) - 适用于大文件 (>20MB) 或长视频 (>1分钟)
2. **内嵌数据** - 适用于小文件 (<20MB)
3. **YouTube URL** (预览功能) - 直接处理 YouTube 视频

### 自定义视频处理
- 自定义帧速率 (FPS)
- 视频时间裁剪 (开始/结束偏移)
- 媒体分辨率设置 (标准/低分辨率)

## 安装依赖

### 方法1: 使用 uv (推荐)
```bash
# 添加 google-genai 依赖
uv add google-genai

# 如果需要处理本地视频,还需要 opencv
uv add opencv-python
```

### 方法2: 使用 pip
```bash
pip install google-genai opencv-python pyyaml
```

## 快速开始

### 1. 获取 Gemini API Key
访问 [Google AI Studio](https://ai.google.dev/) 获取免费的 API Key

### 2. 配置文件设置
编辑 `config_gemini.yml`:

```yaml
# 设置你的 API Key
GEMINI_API_KEY: "your-api-key-here"

# 选择模型
model: gemini-2.5-flash  # 或 gemini-2.5-pro

# 设置视频路径
video_path: "./your-video.mp4"

# 设置提示词
prompt: "请用3句话总结这个视频内容"
```

### 3. 运行程序

#### 单视频分析
```bash
# 使用 uv
uv run main_gemini.py

# 或使用 python
python main_gemini.py
```

#### 批量评估模式
修改配置文件:
```yaml
evaluator:
  enabled: true
  dataset_path: './test/考核点1：活动状态识别/'
  results_path: './eval_results_gemini.json'
```

然后运行:
```bash
uv run main_gemini.py
```

## 使用示例

### 示例1: 视频描述
```yaml
model: gemini-2.5-flash
video_path: "./video.mp4"
prompt: "请详细描述这个视频中发生了什么，包括场景、人物和动作。"
```

### 示例2: 活动识别 (JSON格式输出)
```yaml
prompt: |
  分析视频中的儿童活动，从以下类别中选择: ['画画', '做手工', '过家家', '运动']
  
  请以JSON格式返回:
  {
    "activity_label": "类别名称",
    "content_description": "详细描述",
    "confidence": "高/中/低"
  }
```

### 示例3: 时间戳问答
```yaml
prompt: "在视频的 00:30 和 01:15 分别发生了什么？请分别描述。"
```

### 示例4: YouTube 视频分析
```yaml
support_youtube: true
video_path: "https://www.youtube.com/watch?v=VIDEO_ID"
prompt: "总结这个YouTube视频的主要内容"
```

### 示例5: 自定义处理参数
```yaml
video_fps: 5  # 每秒提取5帧 (默认1帧)
video_start_offset: "10s"  # 从第10秒开始
video_end_offset: "60s"  # 到第60秒结束
media_resolution: low  # 使用低分辨率 (节省token和费用)
```

## 模型选择

### Gemini 2.5 Flash
- **特点**: 速度快、成本低
- **适用场景**: 
  - 批量处理
  - 实时应用
  - 简单的视频理解任务
  - 预算有限的项目

### Gemini 2.5 Pro  
- **特点**: 理解能力强、精度高
- **适用场景**:
  - 复杂视频分析
  - 需要高精度的任务
  - 细节提取
  - 专业应用

## 性能优化建议

### 1. 选择合适的输入方式
```yaml
# 大文件 (>20MB) 或长视频 (>1分钟)
use_file_api: true

# 小文件 (<20MB) 且短视频
use_file_api: false
```

### 2. 调整帧速率
```yaml
# 静态场景 (如讲座、演示)
video_fps: 0.5  # 每2秒1帧

# 动态场景 (如运动、活动)
video_fps: 2  # 每秒2帧
```

### 3. 使用低分辨率
```yaml
# 节省约67%的token费用
media_resolution: low
```

### 4. 裁剪无关内容
```yaml
# 只分析视频的中间部分
video_start_offset: "10s"
video_end_offset: "60s"
```

## Token 消耗说明

每秒视频的 Token 消耗:

**标准分辨率 (default)**:
- 视频帧: 258 tokens/帧 × 1 FPS = 258 tokens
- 音频: 32 tokens
- **总计: ~300 tokens/秒**

**低分辨率 (low)**:
- 视频帧: 66 tokens/帧 × 1 FPS = 66 tokens
- 音频: 32 tokens
- **总计: ~100 tokens/秒**

示例:
- 1分钟视频 (标准分辨率): ~18,000 tokens
- 1分钟视频 (低分辨率): ~6,000 tokens

## 支持的视频格式

```
.mp4, .mov, .avi, .mkv, .flv, .wmv, .m4v, 
.3gpp, .webm, .mpeg, .mpg
```

## 技术限制

### 上下文窗口
- **2M token 模型**: 最多2小时(标准)或6小时(低分辨率)
- **1M token 模型**: 最多1小时(标准)或3小时(低分辨率)

### YouTube 视频
- 免费层级: 每天最多8小时
- 付费方案: 无限制
- 仅支持公开视频

### 帧速率
- 默认: 1 FPS
- 建议范围: 0.5 - 5 FPS
- 注意: 高帧率会增加处理时间和费用

## 常见问题

### Q1: 如何获得更准确的结果?
- 使用 `gemini-2.5-pro` 模型
- 提高 `video_fps` 以捕捉更多细节
- 使用 `media_resolution: default`
- 编写更详细的提示词

### Q2: 如何降低成本?
- 使用 `gemini-2.5-flash` 模型
- 设置 `media_resolution: low`
- 降低 `video_fps` 
- 裁剪视频只保留关键部分

### Q3: 处理长视频很慢怎么办?
- 启用 `use_file_api: true`
- 降低帧速率
- 使用视频裁剪功能
- 考虑将长视频分段处理

### Q4: 如何引用视频中的特定时刻?
在提示词中使用 MM:SS 格式:
```
"在 01:30 和 02:45 分别发生了什么?"
```

### Q5: YouTube 视频无法处理?
确保:
- 设置 `support_youtube: true`
- 视频是公开的 (不是私享或未列出)
- 未超过每日时长限制 (免费8小时)

## 项目结构

```
.
├── main_gemini.py          # Gemini 版本主程序
├── config_gemini.yml       # Gemini 配置文件
├── GEMINI_README.md        # 本文档
├── eval_results_gemini.json # 评估结果输出
├── app_gemini.log          # 运行日志
└── test/                   # 测试视频目录
    ├── 考核点1：活动状态识别/
    ├── 考核点2：困难捕捉与反馈/
    └── 考核点3：语音识别与语义理解/
```

## 与原版 (Qwen-Omni) 的对比

| 特性 | Gemini 2.5 | Qwen-Omni |
|------|-----------|-----------|
| 视频理解 | ✅ 强大 | ✅ 支持 |
| 音频输出 | ❌ 仅文本 | ✅ 语音合成 |
| 实时交互 | ❌ 无 | ✅ WebSocket |
| YouTube支持 | ✅ 内置 | ❌ 需预处理 |
| 自定义FPS | ✅ 支持 | ✅ 支持 |
| API成本 | 💰 按token计费 | 💰 按调用计费 |
| 处理速度 | ⚡ Flash快 | ⚡ 较快 |

## 技术支持

- 官方文档: https://ai.google.dev/docs
- API 参考: https://ai.google.dev/api
- 社区论坛: https://discuss.ai.google.dev

## 许可证

本项目代码遵循原项目许可证。Gemini API 使用需遵循 Google 服务条款。
