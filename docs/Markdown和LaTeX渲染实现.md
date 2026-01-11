# Markdown 和 LaTeX 渲染实现方案

## 概述

由于前端代码已经编译，我们需要通过以下两种方式之一来实现 Markdown 和 LaTeX 渲染：

## 方案一：通过 CSS 注入增强（推荐，最快）

在 `desktop_launcher/main.js` 中已经实现了样式注入功能。我们可以通过以下方式增强：

### 1. 在前端注入渲染库

```javascript
// 在 desktop_launcher/main.js 的 did-finish-load 事件中添加
mainWindow.webContents.executeJavaScript(`
    // 注入 marked.js (Markdown 渲染)
    const markedScript = document.createElement('script');
    markedScript.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
    document.head.appendChild(markedScript);
    
    // 注入 KaTeX (LaTeX 渲染)
    const katexCSS = document.createElement('link');
    katexCSS.rel = 'stylesheet';
    katexCSS.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css';
    document.head.appendChild(katexCSS);
    
    const katexScript = document.createElement('script');
    katexScript.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js';
    document.head.appendChild(katexScript);
    
    // 等待库加载完成后，处理消息
    setTimeout(() => {
        // 监听消息更新
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === 1 && node.classList.contains('message-content')) {
                        renderMarkdownAndLatex(node);
                    }
                });
            });
        });
        
        // 开始观察
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        // 渲染函数
        function renderMarkdownAndLatex(element) {
            if (!element || !element.textContent) return;
            
            let content = element.textContent;
            
            // 1. 先处理代码块（避免被 Markdown 解析）
            const codeBlocks = [];
            content = content.replace(/\`\`\`([\\s\\S]*?)\`\`\`/g, (match, code) => {
                codeBlocks.push(code);
                return \`__CODE_BLOCK_\${codeBlocks.length - 1}__\`;
            });
            
            // 2. 处理数学公式
            const mathBlocks = [];
            // 块级公式 $$...$$
            content = content.replace(/\\$\\$([^$]+)\\$\\$/g, (match, formula) => {
                mathBlocks.push({ type: 'block', formula });
                return \`__MATH_BLOCK_\${mathBlocks.length - 1}__\`;
            });
            // 行内公式 $...$
            content = content.replace(/\\$([^$]+)\\$/g, (match, formula) => {
                mathBlocks.push({ type: 'inline', formula });
                return \`__MATH_INLINE_\${mathBlocks.length - 1}__\`;
            });
            
            // 3. Markdown 渲染
            if (window.marked) {
                content = marked.parse(content);
            }
            
            // 4. 恢复数学公式
            mathBlocks.forEach((item, index) => {
                const placeholder = item.type === 'block' 
                    ? \`__MATH_BLOCK_\${index}__\` 
                    : \`__MATH_INLINE_\${index}__\`;
                
                try {
                    const rendered = katex.renderToString(item.formula, {
                        displayMode: item.type === 'block',
                        throwOnError: false
                    });
                    content = content.replace(placeholder, rendered);
                } catch (e) {
                    console.error('KaTeX render error:', e);
                    content = content.replace(placeholder, \`$\${item.formula}$\`);
                }
            });
            
            // 5. 恢复代码块
            codeBlocks.forEach((code, index) => {
                const highlighted = \`<pre><code>\${code}</code></pre>\`;
                content = content.replace(\`__CODE_BLOCK_\${index}__\`, highlighted);
            });
            
            // 更新元素内容
            element.innerHTML = content;
        }
        
        // 初始渲染已存在的消息
        document.querySelectorAll('.message-content').forEach(renderMarkdownAndLatex);
    }, 1000);
`);
```

## 方案二：后端预处理（备选）

如果方案一不起作用，可以在后端进行预处理：

### 修改 `src/open_llm_vtuber/conversations/conversation_utils.py`

```python
import re
import markdown
from markdown.extensions import fenced_code, tables, toc

def preprocess_markdown_response(text: str) -> dict:
    """
    预处理 Markdown 和 LaTeX 响应
    
    Args:
        text: 原始文本
        
    Returns:
        包含 HTML 和元数据的字典
    """
    # 提取数学公式
    math_blocks = []
    
    # 保护块级公式
    def save_block_math(match):
        formula = match.group(1)
        index = len(math_blocks)
        math_blocks.append(('block', formula))
        return f'__MATH_BLOCK_{index}__'
    
    text = re.sub(r'\\$\\$(.*?)\\$\\$', save_block_math, text, flags=re.DOTALL)
    
    # 保护行内公式
    def save_inline_math(match):
        formula = match.group(1)
        index = len(math_blocks)
        math_blocks.append(('inline', formula))
        return f'__MATH_INLINE_{index}__'
    
    text = re.sub(r'\\$(.+?)\\$', save_inline_math, text)
    
    # Markdown 转 HTML
    md = markdown.Markdown(extensions=[
        'fenced_code',
        'tables',
        'toc',
        'nl2br',
    ])
    html = md.convert(text)
    
    # 恢复数学公式（添加标记供前端渲染）
    for i, (math_type, formula) in enumerate(math_blocks):
        if math_type == 'block':
            placeholder = f'__MATH_BLOCK_{i}__'
            html = html.replace(
                placeholder,
                f'<span class="math-block" data-formula="{formula}">$$${formula}$$$</span>'
            )
        else:
            placeholder = f'__MATH_INLINE_{i}__'
            html = html.replace(
                placeholder,
                f'<span class="math-inline" data-formula="{formula}">${formula}$</span>'
            )
    
    return {
        'html': html,
        'has_math': len(math_blocks) > 0,
        'has_code': '<code>' in html
    }
```

然后在发送消息时调用这个函数。

## 方案三：重新编译前端（最彻底）

如果需要完全自定义前端，需要：

1. 找到前端源码项目（通常在独立的 git submodule）
2. 安装前端依赖
3. 修改 React/Vue 组件
4. 重新编译

### 前端依赖安装

```bash
# 假设前端是 React 项目
cd frontend_source
npm install
npm install marked katex react-katex
```

### 组件修改示例

```typescript
import React, { useEffect, useRef } from 'react';
import { marked } from 'marked';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface MessageProps {
    content: string;
}

export const MessageContent: React.FC<MessageProps> = ({ content }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    
    useEffect(() => {
        if (!containerRef.current) return;
        
        // 处理数学公式
        let processed = content;
        
        // 块级公式
        processed = processed.replace(/\\$\\$(.*?)\\$\\$/gs, (_, formula) => {
            try {
                return katex.renderToString(formula, {
                    displayMode: true,
                    throwOnError: false
                });
            } catch {
                return `$$${formula}$$`;
            }
        });
        
        // 行内公式
        processed = processed.replace(/\\$(.*?)\\$/g, (_, formula) => {
            try {
                return katex.renderToString(formula, {
                    displayMode: false,
                    throwOnError: false
                });
            } catch {
                return `$${formula}$`;
            }
        });
        
        // Markdown 渲染
        const html = marked(processed);
        containerRef.current.innerHTML = html;
    }, [content]);
    
    return <div ref={containerRef} className="message-content" />;
};
```

## 推荐实施步骤

由于时间限制，建议采用 **方案一**：

1. ✅ 修改 `desktop_launcher/main.js`（已在之前的修改中预留了注入点）
2. ✅ 添加 CDN 库加载
3. ✅ 实现自动渲染逻辑
4. 测试效果
5. 如果不满意，再考虑方案二或方案三

## 测试用例

### Markdown 测试

```
# 标题
## 二级标题

**粗体** *斜体* `代码`

- 列表项 1
- 列表项 2

1. 有序列表
2. 第二项

\```python
def hello():
    print("Hello World")
\```

| 表头1 | 表头2 |
|-------|-------|
| 内容1 | 内容2 |
```

### LaTeX 测试

```
行内公式：速度 $v = \\frac{s}{t}$

块级公式：
$$
E = mc^2
$$

复杂公式：
$$
\\int_{a}^{b} f(x)dx = F(b) - F(a)
$$

矩阵：
$$
\\begin{bmatrix}
a & b \\\\
c & d
\\end{bmatrix}
$$
```

## 样式优化

添加美化样式（在 CSS 注入中）：

```css
/* Markdown 内容样式 */
.message-content h1 {
    font-size: 1.5em;
    font-weight: bold;
    margin: 0.5em 0;
    border-bottom: 2px solid #3b82f6;
    padding-bottom: 0.3em;
}

.message-content h2 {
    font-size: 1.3em;
    font-weight: bold;
    margin: 0.4em 0;
}

.message-content code {
    background: rgba(0, 0, 0, 0.05);
    padding: 0.2em 0.4em;
    border-radius: 3px;
    font-family: 'Consolas', 'Monaco', monospace;
}

.message-content pre {
    background: #282c34;
    color: #abb2bf;
    padding: 1em;
    border-radius: 5px;
    overflow-x: auto;
}

.message-content pre code {
    background: transparent;
    padding: 0;
}

/* LaTeX 公式样式 */
.math-block {
    display: block;
    margin: 1em 0;
    text-align: center;
}

.math-inline {
    display: inline-block;
    margin: 0 0.2em;
}

/* 表格样式 */
.message-content table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}

.message-content th,
.message-content td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}

.message-content th {
    background-color: #3b82f6;
    color: white;
}

/* 列表样式 */
.message-content ul,
.message-content ol {
    margin: 0.5em 0;
    padding-left: 1.5em;
}

.message-content li {
    margin: 0.3em 0;
}
```

## 注意事项

1. **性能**: 实时渲染可能影响性能，考虑使用防抖
2. **安全性**: 如果使用 `innerHTML`，需要注意 XSS 攻击
3. **离线**: CDN 方案需要网络，考虑本地化库文件
4. **兼容性**: 测试不同 Electron 版本的兼容性

## 本地化库文件（可选）

将库文件下载到本地以支持离线使用：

```bash
# 创建目录
mkdir -p frontend/libs

# 下载 marked.js
curl -o frontend/libs/marked.min.js https://cdn.jsdelivr.net/npm/marked/marked.min.js

# 下载 KaTeX
curl -o frontend/libs/katex.min.js https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js
curl -o frontend/libs/katex.min.css https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css
```

然后修改 main.js 中的路径从 CDN 改为本地文件。
