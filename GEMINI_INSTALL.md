# Gemini 版本安装指南

## 安装步骤

### 1. 安装 google-genai 依赖

使用 uv (推荐):
```bash
uv add google-genai
```

或者手动编辑 `pyproject.toml`:
```toml
[project]
dependencies = [
    "dashscope>=1.25.0",
    "openai-whisper>=20250625",
    "pyaudio>=0.2.14",
    "pyyaml>=6.0.3",
    "google-genai>=0.8.0",  # 新增
]
```

然后运行:
```bash
uv sync
```

### 2. 获取 Gemini API Key

1. 访问 Google AI Studio: https://ai.google.dev/
2. 点击 "Get API Key"
3. 创建或选择一个项目
4. 复制 API Key

### 3. 配置 API Key

编辑 `config_gemini.yml`:
```yaml
GEMINI_API_KEY: "your-api-key-here"  # 替换为你的 API Key
```

### 4. 运行测试

```bash
# 测试单视频
uv run main_gemini.py

# 或使用 Python
python main_gemini.py
```

## 常见问题

### Q: 提示 "无法解析导入 google.genai"
**A:** 需要先安装依赖:
```bash
uv add google-genai
```

### Q: API Key 无效
**A:** 
- 检查 API Key 是否正确复制
- 确认 API Key 已启用
- 检查是否有配额限制

### Q: 视频处理失败
**A:** 
- 检查视频格式是否支持
- 确认视频文件完整无损
- 尝试使用 `use_file_api: true`

### Q: 如何切换到原版 Qwen-Omni?
**A:** 
```bash
# 使用原版
uv run main.py

# 使用 Gemini 版本
uv run main_gemini.py
```

## 功能对比

| 功能 | main.py (Qwen-Omni) | main_gemini.py (Gemini) |
|------|---------------------|-------------------------|
| 视频理解 | ✅ | ✅ |
| 音频理解 | ✅ | ✅ (通过视频) |
| 语音输出 | ✅ | ❌ 仅文本 |
| 实时对话 | ✅ WebSocket | ❌ |
| YouTube | ❌ | ✅ 内置支持 |
| 帧率自定义 | ✅ | ✅ |
| 时间裁剪 | ✅ | ✅ |
| 批量评估 | ✅ | ✅ |

## 推荐使用场景

### 使用 Qwen-Omni (main.py) 当:
- 需要语音输出/交互
- 需要实时对话功能
- 使用阿里云服务

### 使用 Gemini (main_gemini.py) 当:
- 需要处理 YouTube 视频
- 需要更强的视频理解能力
- 纯文本输出即可
- 使用 Google Cloud 服务

## 下一步

参考 `GEMINI_README.md` 了解更多详细用法和示例。
