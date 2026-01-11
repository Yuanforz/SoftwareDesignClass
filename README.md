# 灵犀助教 LingXi Assistant

![灵犀助教](assets/banner.png)

<h1 align="center">灵犀助教</h1>
<h3 align="center">基于多模态交互的个性化知识自学软件</h3>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue" alt="version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
  <img src="https://img.shields.io/badge/python-3.10+-orange" alt="python">
</p>

---

## 🎓 项目简介

**灵犀助教**是一个创新的 AI 学习助手，通过可爱的 Live2D 数字人形象、智能语音交互和强大的视觉理解能力，为学生和自学者提供个性化的知识讲解与学习辅导服务。

### ✨ 核心特点

- 🎤 **实时语音对话** - 基于 FunASR 的高精度中文语音识别
- 🗣️ **自然语音合成** - Edge TTS 提供流畅自然的语音输出
- 👁️ **视觉理解能力** - 支持图片、截图等学习资料的智能分析
- 💬 **智能知识讲解** - 基于大语言模型的耐心细致讲解
- 🖥️ **桌宠模式** - 可爱的桌面伴侣，随时陪伴学习
- 📝 **Markdown 渲染** - 结构化清晰的回答展示
- 🔢 **LaTeX 公式** - 完美支持数学公式渲染
- 🎨 **Live2D 形象** - 生动的数字人表情和动作

## 🚀 快速开始

### 系统要求

- Windows 10/11
- Python 3.10+
- Node.js 16+
- NVIDIA GPU (推荐，用于 CUDA 加速)

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone [your-repo-url]
   cd LingXi-Assistant
   ```

2. **配置 API 密钥**
   
   编辑 `conf.yaml`，填入你的 StepFun API 密钥：
   ```yaml
   llm_api_key: 'your-api-key-here'
   ```

3. **一键启动**
   ```powershell
   .\启动灵犀助教.ps1
   ```

启动脚本会自动完成：
- 检查 uv 和 Node.js 环境
- 同步 Python 依赖
- 启动后端服务
- 启动桌宠客户端

### 快捷键

- `Ctrl+Shift+L` - 切换桌宠/正常模式
- `Ctrl+Shift+H` - 隐藏/显示窗口  
- `Ctrl+Shift+Q` - 退出应用

### 首次使用

1. 等待模型加载（首次需下载约 500MB）
2. 开始与灵犀助教对话！

## 📖 功能详解

### 1. 语音交互

灵犀助教支持流畅的语音对话：
- 实时语音识别，低延迟响应
- 自然的中文语音合成
- 支持打断和重新开始

### 2. 图片理解

上传学习资料，AI 自动分析：
- 课件截图理解
- 习题图片解答
- 笔记内容提炼

**使用方式**：
- 网页版：点击图片上传按钮
- 桌面版：拖拽图片到窗口

### 3. 智能讲解

专业的教学风格：
- 循序渐进的知识讲解
- 清晰的结构化回答
- 丰富的例子和类比
- 知识点拓展和关联

### 4. 桌宠模式

可爱的桌面伴侣：
- 透明背景，可悬浮在桌面
- 鼠标悬停显示控制面板
- 全局快捷键快速操作

**快捷键**：
- `Ctrl+Shift+L` - 切换桌宠/正常模式
- `Ctrl+Shift+H` - 隐藏/显示窗口
- `Ctrl+Shift+Q` - 退出应用

## 🎯 使用场景

### 📚 课程学习
> 上传课件截图 → 语音询问疑问 → 获得详细讲解

### 📝 习题解答
> 拍摄题目照片 → 请求解题思路 → 理解知识要点

### 🔍 知识探索
> 提出学习目标 → 系统化讲解 → 推荐学习路径

### 📊 学习规划
> 描述学习需求 → 制定学习计划 → 跟踪学习进度

## ⚙️ 配置说明

### 基础配置

主要配置文件：`conf.yaml`

```yaml
character_config:
  character_name: '灵犀'      # AI 助教名称
  human_name: '同学'          # 对用户的称呼
  
  agent_config:
    llm_provider: 'openai_compatible_llm'  # LLM 提供商
    
  asr_config:
    asr_model: 'fun_asr'      # 语音识别模型
    
  tts_config:
    tts_model: 'edge_tts'     # 语音合成模型
```

### 高级配置

详细配置请参考：[使用指南.md](使用指南.md)

## 🛠️ 技术架构

```
灵犀助教
├── 前端
│   ├── Live2D 渲染引擎
│   ├── WebSocket 通信
│   └── Markdown + LaTeX 渲染
├── 后端
│   ├── FastAPI 服务器
│   ├── FunASR 语音识别
│   ├── Edge TTS 语音合成
│   └── StepFun LLM API
└── 桌面客户端
    └── Electron 框架
```

### 技术栈

- **前端**: HTML, CSS, JavaScript, Live2D Cubism SDK
- **后端**: Python, FastAPI, WebSocket
- **桌面**: Electron
- **ASR**: FunASR (SenseVoiceSmall)
- **TTS**: Microsoft Edge TTS
- **LLM**: StepFun step-2-16k (支持视觉)
- **渲染**: Marked.js, KaTeX

## 📊 性能优化

### GPU 加速

如果你有 NVIDIA GPU：

```yaml
# conf.yaml
asr_config:
  fun_asr:
    device: 'cuda:0'  # 使用 GPU 加速
```

### 内存优化

调整并发线程数：

```yaml
fun_asr:
  ncpu: 2  # 减少 CPU 线程
```

## 🐛 常见问题

### Q: 首次启动很慢？
A: 需要下载 FunASR 模型（约 500MB），请耐心等待。

### Q: 语音识别不准确？
A: 确保麦克风权限已开启，尽量在安静环境使用。

### Q: 图片上传没反应？
A: 检查 API 密钥是否正确，网络连接是否正常。

### Q: 数学公式无法显示？
A: 刷新页面，或检查网络连接（需要加载 KaTeX 库）。

更多问题请查看：[使用指南.md](使用指南.md#常见问题)

## 📁 项目结构

```
LingXi-Assistant/
├── conf.yaml              # 主配置文件
├── run_server.py          # 后端启动脚本
├── 启动灵犀助教.ps1        # 一键启动脚本
├── 使用指南.md            # 详细使用文档
├── src/                   # 源代码
│   └── open_llm_vtuber/  # 核心模块
├── desktop_launcher/      # 桌面客户端
├── frontend/              # 前端资源
├── prompts/               # 提示词模板
├── models/                # 模型文件
├── logs/                  # 日志文件
└── docs/                  # 文档
```

## 🤝 参与贡献

本项目基于 [Open-LLM-VTuber](https://github.com/t41372/Open-LLM-VTuber) 进行修改和优化，专注于教育学习场景。

## 📄 开源协议

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE)

### Live2D 模型声明

本项目包含的 Live2D 样本模型由 Live2D Inc. 提供，遵循其独立的使用许可。

## 🎉 致谢

- [Open-LLM-VTuber](https://github.com/t41372/Open-LLM-VTuber) - 原始项目
- [FunASR](https://github.com/alibaba-damo-academy/FunASR) - 语音识别
- [Live2D](https://www.live2d.com/) - 数字人渲染
- [StepFun](https://www.stepfun.com/) - 大语言模型 API

---

<p align="center">
  <strong>让学习变得更有趣、更高效！</strong><br>
  Made with ❤️ for students and learners
</p>

<p align="center">
  ⭐ 如果这个项目对你有帮助，请给个 Star 吧！
</p>
