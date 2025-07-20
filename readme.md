# 多模态AI助手 (multimodal-ai)

[![version](https://img.shields.io/badge/version-2.1-blue)](https://github.com/zhiyu1998/multimodal-ai)
[![license](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![adapter](https://img.shields.io/badge/adapter-OneBot%20v11-orange)](https://github.com/botuniverse/onebot-11)
[![Python](https://img.shields.io/badge/python-3.8+-blue)](https://www.python.org/)
[![NoneBot](https://img.shields.io/badge/nonebot-2.0+-red)](https://github.com/nonebot/nonebot2)

**一个为 Zhenxun Bot 打造的、功能强大的多模态AI插件，将先进的对话、绘图与联网搜索能力无缝集成到您的聊天机器人中。**

`multimodal-ai` 插件基于 `zhenxun.services.llm` 模块构建，旨在提供一个统一、智能且可扩展的AI交互体验。它不仅仅是一个聊天插件，更是一个能够理解多种媒体、执行复杂任务的AI助手。

## 📋 目录

- [✨ 核心功能](#-核心功能)
- [🔧 安装与前置要求](#-安装与前置要求)
- [⚙️ 详细配置](#️-详细配置)
- [📖 使用指令](#-使用指令)
- [📋 模型兼容性说明](#-模型兼容性说明)
- [🎨 Markdown主题预览](#-markdown主题预览)
- [🚀 特色功能详解](#-特色功能详解)
- [🧪 实验性功能](#-实验性功能)
- [❓ 常见问题](#-常见问题)
- [📄 许可证](#-许可证)

---

## ✨ 核心功能

*   **🤖 智能多模态对话**:
    *   支持文本、图片、音频、视频等多种格式的输入。
    *   具备上下文记忆能力，可在设定时间内进行连续对话。
    *   自动检测并利用模型的多模态能力，当模型不支持某种媒体时会给出友好提示。

*   **🎨 高级AI绘图**:
    *   集成豆包（Doubao）AI绘图，支持文生图和图生图。
    *   内置强大的**绘图队列系统**，在高并发请求下能稳定、有序地处理任务，避免资源冲突和崩溃。
    *   包含**浏览器冷却机制**，智能管理浏览器生命周期，提升服务器稳定性和资源利用率。
    *   可选的**AI提示词优化**功能，利用辅助LLM润色用户的绘图描述，以生成更惊艳的作品。

*   **🌐 联网搜索**:
    *   当检测到需要实时信息的意图时，可自动调用模型的联网搜索能力，提供最新、最准确的回答。

*   **🖼️ 优雅的Markdown渲染**:
    *   自动将包含复杂格式（如代码块、列表、表格）的AI回复渲染成精美的图片。
    *   内置多种CSS主题（如 `light`, `dark`, `cyber`），并支持用户自定义主题，让AI的回复更具观赏性。

*   **⚙️ 灵活的模型与配置管理**:
    *   所有核心功能均可通过机器人指令进行开关和配置。
    *   超级管理员可以动态查看和切换当前使用的AI对话模型。

## 🔧 安装与前置要求

### 安装

推荐通过 Zhenxun Bot 的 **WebUI -> 插件市场** 进行安装。这是最简单、最可靠的方式。


### ⚠️ 重要：前置要求

本插件**强依赖** `Zhenxun Bot` 框架内置的 `LLM服务`。在使用本插件前，**您必须首先正确配置 `zhenxun.services.llm`**。

请确保您已经在 `data/config.yaml` 的 `AI` 配置组中，至少配置了一个可用的 `PROVIDERS`，并填入了正确的 `api_key`。

```yaml
# data/config.yaml 示例
AI:
  # ... 其他配置
  PROVIDERS:
    - name: Gemini  # 提供商名称
      api_key:
        - "AIzaSy...YOUR_GEMINI_API_KEY" # 你的API Key
      api_base: https://generativelan...
      api_type: gemini
      models:
        - model_name: gemini-2.5-flash # 至少配置一个模型
# ...
```

## ⚙️ 详细配置

所有配置项均可在 Zhenxun Bot 的 **WebUI -> 配置管理** 页面中找到，也可以直接编辑 `data/config.yaml` 文件中的 `multimodal-ai` 部分。

| Key                               | 说明                                                                                                                        | 默认值                    |
| :-------------------------------- | :-------------------------------------------------------------------------------------------------------------------------- | :------------------------ |
| `MODEL_NAME`                      | **核心配置**。当前激活的对话模型，格式为 `提供商名/模型名`。支持任何PROVIDERS中配置的模型。**推荐Gemini系列以获得完整多模态支持**。 | `Gemini/gemini-2.5-flash` |
| `enable_md_to_pic`                | 是否启用Markdown转图片功能。                                                                                                | `True`                    |
| `THEME`                           | Markdown转图片使用的主题。对应 `css` 目录下的文件名（无需后缀）。可选：`light`, `dark`, `cute`, `cyber`, `dracula`, `sun`。详见[主题预览](#-markdown主题预览)。 | `light`                   |
| `enable_ai_draw`                  | 是否启用AI绘图功能。                                                                                                        | `True`                    |
| `DOUBAO_COOKIES`                  | **绘图核心配置**。豆包AI绘图的Cookies。**这是绘图功能正常工作的关键。**                                                     | `""`                      |
| `HEADLESS_BROWSER`                | 是否使用无头浏览器模式进行AI绘图。服务器部署**必须**设为 `True`，本地调试可设为 `False` 以便观察浏览器操作。                | `True`                    |
| `enable_draw_prompt_optimization` | 是否启用AI绘图描述优化。开启后会使用辅助LLM润色描述，效果更好，但会消耗额外API额度。                                        | `False`                   |
| `auxiliary_llm_model`             | 辅助LLM模型名称，用于意图检测、绘图描述优化等功能。                                                                         | `Gemini/gemini-2.5-flash` |
| `enable_ai_intent_detection`      | 是否启用AI进行意图识别。关闭时，将使用简单的关键词匹配。                                                                    | `False`                   |
| `context_timeout_minutes`         | 会话上下文超时时间（分钟）。超时后，新对话将开启新的上下文。设置为`0`则关闭上下文对话功能。                                 | `5`                       |
| `enable_mcp_tools`                | **[实验性]** 是否启用MCP工具。此功能目前处于实验阶段，可能不稳定。                                                          | `False`                   |
| `AGENT_MODEL_NAME`                | **[实验性]** 用于Agent工具调用功能的模型名称。                                                                              | `Gemini/gemini-2.5-flash` |

<details>
<summary><strong>👉 如何获取 DOUBAO_COOKIES (点击展开)</strong></summary>

AI绘图功能依赖于通过浏览器自动化访问豆包网站。为了免于登录，需要提供您的登录Cookies。

1.  在您的电脑浏览器（推荐Chrome或Edge）中，登录豆包官网：[https://www.doubao.com/](https://www.doubao.com/)
2.  登录成功后，按 `F12` 打开开发者工具。
3.  切换到 **“网络 (Network)”** 选项卡。
4.  在页面上随便进行一些操作（例如，发送一条消息），确保网络监控区域出现新的网络请求。
5.  在过滤框中输入 `chat`，找到一个名为 `chat` 或 `completion` 的请求。
6.  右键点击该请求，选择 **“复制 (Copy)” -> “以cURL(bash)格式复制 (Copy as cURL (bash))”**。
7.  将复制的内容粘贴到记事本或任何文本编辑器中。内容会很长，类似这样：
    ```bash
    curl 'https://www.doubao.com/api/chat/completion' \
      -H 'accept: text/event-stream' \
      -H 'cookie: s_v_web_id=...; ttwid=...; other_cookie=...' \
      ... (其他内容)
    ```
8.  找到 `-H 'cookie: ...'` 这一行，**复制引号内 `cookie:` 后面的所有内容**。
    例如，从 `s_v_web_id=...` 一直复制到最后一个 `...`。
9.  将这串长长的文本粘贴到 `DOUBAO_COOKIES` 配置项的值中即可。

</details>

---

## 📖 使用指令

### 🤖 智能对话功能

**命令格式**:
- `ai [你的问题]`
- 引用任意消息并发送 `ai [你的问题]` (支持引用图片、视频、文档等)

**功能说明**: 与AI进行智能对话，支持各种问题咨询、代码编写、知识问答等。

**使用示例**:
```bash
ai 你好，介绍一下你自己
ai 帮我写一段Python代码，实现快速排序
```

**引用消息示例**:
```bash
(引用一张图片) ai 这张图片里有什么？
(引用一段文字) ai 帮我总结一下这段话
```

**效果展示**:

![智能对话示例](./assets/chat-1.png)
*完整对话界面*

![AI回复详情](./assets/chat-2.png)
*AI回复内容展示*

---

### 🌐 联网搜索功能

**命令格式**: `ai 搜索 [关键词]` 或 `ai [包含搜索意图的问题]`

**功能说明**: 当需要获取实时信息时，AI会自动调用联网搜索能力，提供最新、最准确的回答。

**使用示例**:
```bash
ai 搜索 今天有什么科技新闻？
ai 搜索 最新的AI技术发展
```

**效果展示**:

![联网搜索示例](./assets/search_1.png)
*搜索功能完整对话*

![搜索结果详情](./assets/search_2.png)
*搜索结果展示*

---

### 🖼️ 多模态图片识别

**命令格式**: 发送 `图片` 并附带或回复 `ai [你的问题]`

**功能说明**: 上传图片让AI进行分析，支持图片内容识别、场景描述、文字提取等多种功能。

**使用示例**:
```bash
(发送一张风景照) ai 这是哪里？
(发送一张截图) ai 帮我分析这个图表
```

**效果展示**:

![图片识别示例](./assets/multimodal_image-1.png)
*图片识别完整对话*

![图片分析结果](./assets/multimodal_image-2.png)
*AI图片分析结果*

---

### 🎬 多模态视频分析

**命令格式**: 发送 `视频文件` 并附带或回复 `ai [你的问题]`

**功能说明**: 上传视频让AI进行分析，支持视频内容总结、场景识别、动作分析等功能。

**使用示例**:
```bash
(发送一段视频) ai 总结一下这个视频的内容
(发送一段教学视频) ai 这个视频在讲什么？
(发送一段运动视频) ai 分析一下这个动作
```

**效果展示**:

![视频分析示例](./assets/multimodal_video-1.png)
*视频分析完整对话*

![视频分析结果](./assets/multimodal_video-2.png)
*AI视频分析结果*

---

### 🎨 AI绘图功能

#### 📝 文生图 (Text-to-Image)

**命令格式**: `ai绘图 [描述]` 或 `ai绘画 [描述]`

**功能说明**: 根据文字描述生成精美的AI图片，支持各种风格和主题。

**使用示例**:
```bash
ai绘图 一只穿着宇航服的猫在月球上喝咖啡，动漫风格
ai绘画 赛博朋克风格的未来城市，霓虹灯闪烁
ai绘图 中国古典美女，水墨画风格
```

**效果展示**:

![文生图示例](./assets/Text-to-Image.png)
*AI文生图效果展示*

#### 🖼️ 图生图 (Image-to-Image)

**命令格式**: 发送 `图片` 并附带 `ai绘图 [描述]`

**功能说明**: 基于现有图片进行风格转换或内容修改，创造全新的艺术作品。

**使用示例**:
```bash
(发送一张人物照片) ai绘图 转换成赛博朋克风格
(发送一张风景照) ai绘图 改成动漫风格
```

**引用消息示例**:
```bash
(引用包含图片的消息) ai绘图 转换成赛博朋克风格
(引用一张照片) ai绘图 改成动漫风格
```

**效果展示**:

![图生图示例](./assets/Image-to-Image.png)
*AI图生图效果展示*

---

### ⚙️ 模型与配置管理 (限超级管理员)

**模型管理**:
- **查看可用模型**: `ai模型 列表`
- **切换对话模型**: `ai模型 切换 [提供商名/模型名]`
  ```bash
  ai模型 切换 Gemini/gemini-2.5-pro
  ai模型 切换 DeepSeek/deepseek-reasoner
  ai模型 切换 GLM/glm-4v-plus
  ai模型 切换 Doubao/doubao-seed-1-6-250615
  ```

### 📋 模型兼容性说明

本插件支持通过 `ai模型 切换` 命令切换到任何在 `PROVIDERS` 中配置的模型，包括但不限于：

#### 🟢 完全支持多模态的推荐模型
- **Gemini系列** (推荐)
  - `Gemini/gemini-2.5-flash` - 速度快，成本低
  - `Gemini/gemini-2.5-pro` - 能力强，适合复杂任务
  - `Gemini/gemini-2.5-flash-lite-preview-06-17`
- **Doubao系列**
  - `Doubao/doubao-seed-1-6-250615` - 支持图片、视频、音频分析

#### 🟡 部分支持多模态的模型
- **GLM系列**
  - `GLM/glm-4v-plus` - 支持图片分析，不支持视频/音频

#### 🔴 仅支持文本对话的模型
- **DeepSeek系列**
  - `DeepSeek/deepseek-reasoner` - 仅文本对话，不支持多模态
  - `DeepSeek/deepseek-chat` - 仅文本对话，不支持多模态

> **💡 提示**:
> - 使用不支持多模态的模型时，插件会自动提取图片/视频中的文字内容进行分析
> - 为了获得最佳的多模态体验，强烈推荐使用 **Gemini系列** 模型
> - 可以随时通过 `ai模型 切换` 命令在不同模型间切换，无需重启机器人

**功能开关**:
- **开关Markdown转图片**: `ai配置 md on/off`
- **开关AI绘图功能**: `ai配置 绘图 on/off`

**主题管理**:
- **查看Markdown主题**: `ai主题 列表`
- **切换Markdown主题**: `ai主题 切换 [主题名]`
  ```bash
  ai主题 切换 dark
  ```

### 🎨 Markdown主题预览

插件内置了多种精美的Markdown渲染主题，让AI的回复更具观赏性。以下是各主题的效果预览：

#### 🌞 Light 主题 (默认)
清新明亮的浅色主题，适合日常使用。

![Light主题预览](./assets/light.png)

#### 🚀 Cyber 主题
未来感十足的赛博朋克风格，科技感满满。

![Cyber主题预览](./assets/cyber.png)

#### 🧛 Dracula 主题
经典的Dracula配色方案，深受程序员喜爱。

![Dracula主题预览](./assets/dracula.png)

#### ☀️ Sun 主题
温暖明亮的阳光主题，活力四射。

![Sun主题预览](./assets/sun.png)

#### 🎀 Cute 主题
可爱温馨的粉色系主题，萌系风格。

![Cute主题预览](./assets/cute.png)

**切换主题示例**:
```bash
ai主题 切换 cyber    # 切换到赛博朋克主题
ai主题 切换 dracula  # 切换到Dracula主题
ai主题 切换 cute     # 切换到可爱主题
```

---

## 🚀 特色功能详解

### AI绘图队列与稳定性保障

为了应对多用户同时请求绘图的场景，插件内置了先进的绘图任务队列。

*   **有序处理**: 所有绘图请求会进入一个队列排队，由一个专门的后台处理器逐一执行，确保系统稳定。
*   **状态反馈**: 当用户提交的请求进入队列时，机器人会告知其当前排队位置和预计等待时间。
*   **资源保护**: 浏览器冷却机制避免了因过于频繁地启动/关闭浏览器进程而导致的服务器高负载和不稳定，这是保障7x24小时稳定运行的关键。

### 意图识别与智能路由

插件内置了意图识别引擎，可以根据用户的输入，智能地判断用户的目的。

*   **关键词模式**: 默认情况下，通过`搜索`等关键词将请求路由到联网搜索功能。
*   **AI模式 (可选)**: 开启 `enable_ai_intent_detection` 后，会使用一个轻量级LLM来更智能地分析用户意图，可以更准确地判断用户是想闲聊还是想搜索实时信息。

---

## 🧪 实验性功能

本插件包含一些前沿但尚不完全稳定的实验性功能，您可以按需开启。

*   **工具调用 (Agent)**:
    *   **功能**: 允许AI调用外部工具（如地图API）来完成特定任务。
    *   **现状**: 此功能依赖于 `MCP` 协议和外部工具服务，目前实现较为初级，可能无法在所有场景下稳定工作。
    *   **开启方式**: 设置 `enable_mcp_tools: True`，并按照 `data/llm/mcp_tools.json.example` 配置您的工具服务。

---

## ❓ 常见问题

1.  **AI绘图功能无法使用，提示失败？**
    *   **反爬验证问题**: 不配置Cookies时，有概率触发豆包反爬验证导致功能失效。建议配置 `DOUBAO_COOKIES` 提高稳定性。
    *   **检查 `DOUBAO_COOKIES`**: 如已配置Cookies，请确保Cookies正确填写且未过期。过期后请按上述教程重新获取。
    *   **检查 `HEADLESS_BROWSER`**: 在服务器上，此项必须为 `True`。


2.  **AI没有任何回复？**
    *   **检查前置要求**: 确保 `zhenxun.services.llm` 服务已正确配置并且API Key有效、有额度。
    *   **检查模型名称**: 确保 `MODEL_NAME` 配置项填写的模型在您的 `PROVIDERS` 列表中存在。


3.  **如何添加新的AI模型？**
    本插件的模型管理依赖于Zhenxun框架的LLM服务。请前往 `data/config.yaml` 文件，在 `AI.PROVIDERS` 列表中添加或修改模型信息，然后使用 `ai模型 切换` 指令即可。

4.  **为什么发送图片/视频后AI无法识别内容？**
    *   **检查模型支持**: 确保当前使用的模型支持多模态功能。推荐使用Gemini系列或doubao-seed-1-6-250615。
    *   **模型限制**: DeepSeek等模型仅支持文本对话，无法直接分析图片/视频内容。
    *   **切换模型**: 使用 `ai模型 切换 Gemini/gemini-2.5-flash` 切换到支持多模态的模型。

5.  **不同模型有什么区别？**
    *   **Gemini系列**: 完整支持文本、图片、视频、音频分析，推荐日常使用。
    *   **Doubao系列**: 支持多模态，在中文理解方面表现优秀。
    *   **GLM系列**: 支持图片分析，但不支持视频/音频。
    *   **DeepSeek系列**: 仅支持文本对话，推理能力强但无多模态功能。

---

## 📄 许可证

本项目使用 [MIT License](./LICENSE) 开源。