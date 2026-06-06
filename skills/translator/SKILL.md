---
name: translator
description: 专业小说/文档翻译工具。支持中文↔英文、中文↔日文、多语言互译。使用GLM-5系列模型API进行高质量翻译，支持批量章节翻译、术语一致性检查、截断检测与分块重试。当用户要求翻译小说、文档、文章时触发。
---

# 专业翻译工具

使用GLM-5系列模型API进行高质量小说/文档翻译。

## 模型API配置

- **API地址**：`https://api.z.ai/api/coding/paas/v4/chat/completions`
- **API Key**：`1168df057642498d943008d1f7f7f573.eg4gego9qJV6KoAF`
- **模型优先级**：`glm-5.1` > `glm-5-turbo` > `glm-5` > `glm-5v-turbo`
- **请求方式**：POST，标准OpenAI兼容格式
- **限流策略**：如遇HTTP 429错误，等待60秒后重试，最多重试4次

### 模型选择指南

| 模型 | 适用场景 | 速度 | 质量 |
|------|---------|------|------|
| `glm-5.1` | 高质量翻译、文学性要求高 | 中 | 最高 |
| `glm-5-turbo` | 批量翻译、长篇翻译（推荐默认） | 快 | 高 |
| `glm-5` | 高质量但速度慢，易429 | 慢 | 高 |
| `glm-5v-turbo` | 含图片的文档翻译 | 快 | 高 |

### API调用示例

```python
import urllib.request, json

def translate(text, source_lang="中文", target_lang="英文", model="glm-5-turbo"):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": f"你是一位专业翻译家，擅长将{source_lang}翻译为{target_lang}。保持原文的文学风格、人物语气和情感表达。直接输出翻译结果，不要加任何解释。"
            },
            {
                "role": "user", 
                "content": f"请将以下{source_lang}文本翻译为{target_lang}：\n\n{text}"
            }
        ],
        "temperature": 0.3,
        "max_tokens": 8192
    }
    
    req = urllib.request.Request(
        "https://api.z.ai/api/coding/paas/v4/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer 1168df057642498d943008d1f7f7f573.eg4gego9qJV6KoAF"
        },
        method="POST"
    )
    
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                content = result['choices'][0]['message']['content']
                finish = result['choices'][0].get('finish_reason', 'stop')
                return content, (finish == 'length')
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 60 * (attempt + 1)
                time.sleep(wait)
            else:
                time.sleep(30)
        except Exception:
            time.sleep(30)
    return None, False
```

## 工作流程

### 1. 接收翻译任务
确认以下信息：
- **源文件/目录**：待翻译的文件路径
- **目标目录**：翻译结果保存路径
- **语言方向**：如 中文→英文、英文→中文
- **模型选择**：默认 `glm-5-turbo`（批量翻译），高质量需求用 `glm-5.1`
- **文件格式**：txt / md / 其他

### 2. 翻译前准备
- 扫描源目录，统计文件数量和总字符数
- 检查目标目录，跳过已翻译的文件（>2000字符视为已完成）
- 生成术语表（如为人名、地名等专有名词建立统一译法）
- 估算翻译时间：每章约2-3分钟（含API间隔）

### 3. 批量翻译

对每个文件执行：

1. 读取源文件内容
2. 检查文件长度：
   - **< 8000字符**：整篇翻译
   - **≥ 8000字符**：分块翻译（按段落拆分为2-3块）
3. 调用API翻译
4. 检测截断：
   - `finish_reason == "length"` → 该块被截断，需继续翻译剩余部分
   - 翻译结果长度 < 源文本长度 × 1.5 → 可能截断，重试
5. 保存翻译结果到目标目录
6. API请求间隔：10秒（避免429限流）

### 4. 翻译质量检查
每10章检查一次：
- 翻译长度与源文本比例（英文/中文通常2.0-3.0倍字符比）
- 是否有明显的截断（句子不完整）
- 术语一致性（人名、地名翻译是否统一）

### 5. 完成后处理
- 统计翻译章节数、总字符数
- 打包为 tar.gz 和/或全文合并 txt.gz
- 发送邮件报告给用户

## 翻译Prompt模板

### 小说翻译
```
你是一位专业文学翻译家，擅长将中文网络小说翻译为英文。

翻译要求：
1. 保持原文的叙事风格和节奏
2. 人物对话要自然、符合角色性格
3. 保留专有名词的音译（人名、地名用拼音）
4. 修炼/功法术语使用统一译法
5. 文学性描写要优美，不要机械翻译
6. 直接输出翻译结果，不要加任何解释

专有名词对照：
[根据具体小说补充]

请翻译以下内容：
```

### 通用文档翻译
```
你是一位专业翻译家。请将以下内容从{源语言}翻译为{目标语言}。

要求：
1. 准确传达原文含义
2. 语言流畅自然
3. 保持专业术语的准确性
4. 直接输出翻译结果
```

### 分块翻译
当源文本超过8000字符时，按以下方式分块：
1. 按空行/段落拆分
2. 每块不超过8000字符
3. 在块结尾添加提示："[续上块] 已翻译前半部分，请继续翻译以下内容："
4. 合并各块翻译结果

## 限流与错误处理

| 错误 | 处理方式 |
|------|---------|
| HTTP 429 | 等待60×重试次数秒后重试，最多4次 |
| 超时（300s）| 等待30秒后重试 |
| 截断（finish_reason=length）| 分块重试 |
| 翻译过短（<源文本×1.5）| 重试一次 |
| 连续3次失败 | 跳过该章节，记录到失败列表 |

## 输出格式

- 每个翻译文件与源文件同名（如 ch001.txt → ch001.txt）
- 保存到目标目录
- 翻译完成后生成报告（HTML格式邮件附件）

## 支持的语言对

- 中文 ↔ 英文（主要）
- 中文 ↔ 日文
- 中文 ↔ 韩文
- 英文 ↔ 日文
- 其他语言对按需支持
