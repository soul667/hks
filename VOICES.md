# Qwen Omni 支持的语音列表

## 中文语音

| 语音 ID | 名称 | 性别 | 特点 |
|---------|------|------|------|
| `longxiaochun` | 龙小春 | 女 | 清晰自然 |
| `longyuanqing` | 龙渊青 | 男 | 沉稳专业 |
| `longxiaoxia` | 龙小夏 | 女 | 活泼温柔 |
| `longtianyang` | 龙天阳 | 男 | 明朗有力 |

## 配置方法

在 `config.yml` 中设置:

```yaml
voice: longxiaochun  # 推荐:女声,清晰自然
# 或
voice: longyuanqing  # 男声,沉稳专业
# 或
voice: longxiaoxia   # 女声,活泼温柔
# 或
voice: longtianyang  # 男声,明朗有力
```

## 注意事项

- ❌ 不支持 `Chelsie` (这是其他模型的语音)
- ✅ 默认推荐使用 `longxiaochun` (女声,效果最好)
- ✅ 如果需要男声,推荐使用 `longyuanqing`

## 测试建议

建议先用短视频测试不同语音的效果,选择最适合您场景的语音。
