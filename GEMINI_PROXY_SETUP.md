# Gemini 代理服务配置指南

如果你需要通过代理服务访问 Gemini API（例如国内无法直接访问 Google API），可以按照以下步骤配置。

## 配置方法

### 方法1: 修改配置文件 (推荐)

编辑 `config_gemini.yml`:

```yaml
# API Key (从代理服务提供商获取)
GEMINI_API_KEY: "sk-your-proxy-api-key-here"

# 代理服务配置
api_base_url: "https://your-proxy-service.com"  # 替换为你的代理服务地址
api_endpoint: "/v1beta/models/gemini-2.0-flash:generateContent"  # API 路径

# 模型配置 (确保与 api_endpoint 中的模型名称一致)
model: gemini-2.0-flash
```

### 方法2: 使用环境变量

如果 google-genai SDK 不支持通过配置设置 base_url，可以使用环境变量：

**Linux/Mac:**
```bash
export GOOGLE_API_BASE="https://your-proxy-service.com"
export GEMINI_API_KEY="sk-your-proxy-api-key-here"
uv run main_gemini.py
```

**Windows PowerShell:**
```powershell
$env:GOOGLE_API_BASE="https://your-proxy-service.com"
$env:GEMINI_API_KEY="sk-your-proxy-api-key-here"
uv run main_gemini.py
```

**Windows CMD:**
```cmd
set GOOGLE_API_BASE=https://your-proxy-service.com
set GEMINI_API_KEY=sk-your-proxy-api-key-here
uv run main_gemini.py
```

## 常见代理服务提供商

### 1. OpenAI 兼容格式代理

如果你的代理服务使用 OpenAI 兼容格式：

```yaml
api_base_url: "https://proxy.example.com"
api_endpoint: "/v1beta/models/gemini-2.0-flash:generateContent"
```

### 2. 自定义代理格式

根据你的代理服务文档调整：

```yaml
# 示例1: 完整路径
api_base_url: "https://api.proxy.com"
api_endpoint: "/v1beta/models/gemini-2.0-flash:generateContent"

# 示例2: 包含版本号
api_base_url: "https://api.proxy.com/v1beta"
api_endpoint: "/models/gemini-2.0-flash:generateContent"
```

## 配置示例

### 示例1: 使用你提到的代理格式

```yaml
GEMINI_API_KEY: "sk-Ianh6ysPZ4t1kzAEKVZ1xcOQOFGITMwInPQ9gWuNWgelmoWW"

# 代理配置
api_base_url: "https://your-proxy.com"  # 你的代理服务地址
api_endpoint: "/v1beta/models/gemini-2.0-flash:generateContent"

# SSL 配置 (重要!)
verify_ssl: false  # 如果遇到 SSL 握手失败错误，设置为 false
                   # ⚠️ 这会跳过 SSL 证书验证，降低安全性

model: gemini-2.0-flash  # 注意这里改为 2.0
use_file_api: false  # 代理可能不支持 File API

# 视频配置
video_path: "./test/考核点2：困难捕捉与反馈/过家家（操作失败）.mp4"
```

### 示例2: 使用官方 API (无代理)

```yaml
GEMINI_API_KEY: "your-google-api-key"

# 不设置代理
api_base_url: null
api_endpoint: "/models/gemini-2.5-flash:generateContent"

model: gemini-2.5-flash
use_file_api: true  # 官方 API 支持
```

## 注意事项

### 1. 模型名称匹配

确保配置文件中的 `model` 字段与 `api_endpoint` 中的模型名称一致：

```yaml
# ✅ 正确
model: gemini-2.0-flash
api_endpoint: "/v1beta/models/gemini-2.0-flash:generateContent"

# ❌ 错误
model: gemini-2.5-flash
api_endpoint: "/v1beta/models/gemini-2.0-flash:generateContent"
```

### 2. API Key 格式

不同的代理服务可能使用不同的 API Key 格式：
- Google 官方: `AIza...`
- 某些代理: `sk-...`
- 其他格式: 根据代理文档

### 3. File API 支持

大多数代理服务不支持 File API，建议设置：

```yaml
use_file_api: false  # 使用内嵌方式
```

对于大视频文件，你可能需要：
- 压缩视频
- 降低分辨率
- 减少帧率

```yaml
video_fps: 0.5  # 每2秒1帧
media_resolution: low  # 低分辨率
```

### 4. YouTube 支持

代理服务通常不支持 YouTube URL：

```yaml
support_youtube: false
```

### 5. 视频大小限制

代理服务可能有更严格的大小限制（通常 <20MB）：

```yaml
# 如果视频太大，可以裁剪
video_start_offset: "10s"
video_end_offset: "60s"
```

## 测试配置

运行以下命令测试配置是否正确：

```bash
uv run main_gemini.py
```

如果看到以下输出，说明配置成功：

```
✓ 已初始化 Gemini 客户端 (模型: gemini-2.0-flash)
使用自定义 API 端点: https://your-proxy.com/v1beta/models/gemini-2.0-flash:generateContent
```

## 常见问题

### Q1: SSL 握手失败错误

**错误信息:**
```
[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] sslv3 alert handshake failure
httpx.ConnectError: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]
```

**解决方案:**

在 `config_gemini.yml` 中设置:
```yaml
verify_ssl: false  # 禁用 SSL 验证
```

⚠️ **安全警告**: 禁用 SSL 验证会降低安全性，仅在以下情况使用：
- 使用可信的代理服务
- 在测试/开发环境
- 代理服务使用自签名证书

**更安全的替代方案** (如果代理服务提供):
1. 下载代理服务的 SSL 证书
2. 在系统中安装该证书
3. 保持 `verify_ssl: true`

### Q2: 连接超时

**A:**
- 检查代理服务地址是否正确
- 测试网络连接: `ping your-proxy.com`
- 确认代理服务是否在线

### Q3: 模型不支持

**A:**
- 确认代理服务支持的模型列表
- 检查 `api_endpoint` 中的模型名称
- 更新 `model` 字段匹配代理服务

### Q4: 视频上传失败

**A:**
- 设置 `use_file_api: false`
- 减小视频大小和长度
- 降低 `video_fps` 和使用 `media_resolution: low`

### Q5: SDK 版本不兼容

**A:**
```bash
# 更新 google-genai 到最新版本
uv add google-genai@latest

# 或者使用环境变量方式
export GOOGLE_API_BASE="https://your-proxy.com"
```

## 完整配置示例

```yaml
# ------------Gemini 代理服务完整配置示例--------------------

# API Key
GEMINI_API_KEY: "sk-your-proxy-api-key"

# 代理服务配置
api_base_url: "https://your-proxy.com"
api_endpoint: "/v1beta/models/gemini-2.0-flash:generateContent"

# 模型配置
model: gemini-2.0-flash

# 视频处理配置 (针对代理服务优化)
use_file_api: false  # 代理通常不支持
video_fps: 1  # 标准帧率
media_resolution: default  # 或 low 以节省成本

# 视频裁剪 (如果视频太大)
video_start_offset: null
video_end_offset: null

# YouTube (代理通常不支持)
support_youtube: false

# 输入配置
video_path: "./test/考核点2：困难捕捉与反馈/过家家（操作失败）.mp4"

# 提示词
prompt: |
    你是一个专业的儿童活动分析专家。
    请分析这个视频并以 JSON 格式返回结果...

# 评估器
evaluator:
  enabled: false
  dataset_path: './test/考核点1：活动状态识别/'
  results_path: './eval_results_gemini.json'
```

## 获取帮助

如果遇到问题：

1. 查看日志文件: `app_gemini.log`
2. 检查代理服务文档
3. 联系代理服务提供商
4. 提交 Issue: [项目 GitHub]

## 相关资源

- [Google Gemini API 文档](https://ai.google.dev/docs)
- [google-genai Python SDK](https://github.com/googleapis/python-genai)
- [代理服务设置示例](./config_gemini.yml)
