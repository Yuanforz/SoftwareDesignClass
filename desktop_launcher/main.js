const { app, BrowserWindow, screen, ipcMain, globalShortcut, Tray, Menu, nativeImage } = require('electron');
const path = require('path');

let mainWindow = null;
let tray = null;  // 系统托盘
let isDesktopPetMode = true; // 默认启动为桌宠模式

function createWindow() {
    // 获取屏幕尺寸
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;

    // 桌宠模式：侧边布局，更宽的窗口
    const petWidth = 700;  // Live2D 300px + 对话 400px
    const petHeight = 600;
    
    // 正常模式：更大的窗口，用于设置和详细交互
    const normalWidth = Math.min(1200, width - 100);
    const normalHeight = Math.min(800, height - 100);

    mainWindow = new BrowserWindow({
        width: isDesktopPetMode ? petWidth : normalWidth,
        height: isDesktopPetMode ? petHeight : normalHeight,
        x: isDesktopPetMode ? width - petWidth - 20 : Math.max(0, width - normalWidth - 50),
        y: isDesktopPetMode ? height - petHeight - 20 : Math.max(0, height - normalHeight - 50),
        transparent: true,      // 透明背景
        frame: false,           // 无边框
        alwaysOnTop: true,      // 始终置顶
        hasShadow: false,       // 无阴影
        resizable: !isDesktopPetMode, // 桌宠模式不可调整大小
        movable: true,          // 可拖动
        useContentSize: true,
        minWidth: petWidth,
        minHeight: petHeight,
        skipTaskbar: isDesktopPetMode, // 桌宠模式不显示在任务栏
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            enableRemoteModule: true
        }
    });

    // 加载桌宠模式专用页面（独立实现）
    if (isDesktopPetMode) {
        mainWindow.loadFile(path.join(__dirname, 'desktop_pet.html'));
    } else {
        // 正常模式加载原前端
        mainWindow.loadURL('http://127.0.0.1:12393');
    } 

    // 开发时可打开调试工具（注意：DevTools 的 Elements 面板可能导致崩溃）
    // 如需调试，取消下面这行注释：
    // mainWindow.webContents.openDevTools({ mode: 'detach' });

    // 桌宠模式使用独立页面，不需要注入
    mainWindow.webContents.on('did-finish-load', () => {
        console.log('窗口加载完成');
        
        // 只在正常模式下注入渲染器（桌宠模式已内置）
        if (!isDesktopPetMode) {
            injectMarkdownAndLatexRenderer();
        }
    });

    // 窗口关闭时的处理
    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    // 创建系统托盘
    createTray();

    // 注册全局快捷键
    registerShortcuts();
}

// 创建系统托盘
function createTray() {
    // 从文件加载托盘图标
    const iconPath = path.join(__dirname, 'icon.png');
    let trayIcon;
    
    try {
        trayIcon = nativeImage.createFromPath(iconPath);
        // Windows 需要较小的图标
        if (process.platform === 'win32' && !trayIcon.isEmpty()) {
            trayIcon = trayIcon.resize({ width: 16, height: 16 });
        }
        console.log('托盘图标加载成功:', iconPath);
    } catch (e) {
        console.error('托盘图标加载失败:', e);
        // 创建一个简单的备用图标
        const iconBase64 = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAbwAAAG8B8aLcQwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAEISURBVDiNpZMxTsNAEEX/rO0IpYFGQscRuAI3oOEGnICGhtJHoKGgoKPgBnAESo5AQ0NBQYEEcuxdBmJZsb0JEn9baf7M29kdIwLBz/n7uPP7uYjYsX/E4fHJAXALPItIdF/YdJzLi4vRpyGQxkiI3aG/vn3B0/MzGxsb7O/s0O/3/4YQkeHoasTd/cPcRq8nxuNxSslf4NtbAAaDwdzr8fPzC8PhkMFgMKdx0sDj0+uSMDNarRZlWZJl2dSjhwb66G4pQlEUPL28sLu7C8DHxwfdbne+QKvVIkkSZr/nYW1tnelkwtLPXEXw+fmJJEnm+JIDkySh0+mQpumUyg9PqIiIS0T+q/sNEZZaBYFvfeoAAAAASUVORK5CYII=';
        trayIcon = nativeImage.createFromDataURL('data:image/png;base64,' + iconBase64);
        if (process.platform === 'win32') {
            trayIcon = trayIcon.resize({ width: 16, height: 16 });
        }
    }
    
    tray = new Tray(trayIcon);
    tray.setToolTip('灵犀助教');
    
    // 托盘右键菜单
    const contextMenu = Menu.buildFromTemplate([
        {
            label: '显示窗口',
            click: () => {
                if (mainWindow) {
                    mainWindow.show();
                    mainWindow.focus();
                }
            }
        },
        { type: 'separator' },
        {
            label: '退出',
            click: () => {
                app.quit();
            }
        }
    ]);
    
    tray.setContextMenu(contextMenu);
    
    // 点击托盘图标显示/隐藏窗口
    tray.on('click', () => {
        if (mainWindow) {
            if (mainWindow.isVisible()) {
                mainWindow.hide();
            } else {
                mainWindow.show();
                mainWindow.focus();
            }
        }
    });
    
    console.log('系统托盘已创建');
}

// 注入 Markdown 和 LaTeX 渲染功能
function injectMarkdownAndLatexRenderer() {
    mainWindow.webContents.executeJavaScript(`
        (function() {
            console.log('Injecting Markdown and LaTeX renderer...');
            
            // 加载 marked.js (Markdown 渲染)
            const markedScript = document.createElement('script');
            markedScript.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
            markedScript.onload = () => console.log('Marked.js loaded');
            document.head.appendChild(markedScript);
            
            // 加载 KaTeX CSS
            const katexCSS = document.createElement('link');
            katexCSS.rel = 'stylesheet';
            katexCSS.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css';
            document.head.appendChild(katexCSS);
            
            // 加载 KaTeX JS
            const katexScript = document.createElement('script');
            katexScript.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js';
            katexScript.onload = () => {
                console.log('KaTeX loaded');
                initRenderer();
            };
            document.head.appendChild(katexScript);
            
            // 添加美化样式
            const style = document.createElement('style');
            style.textContent = \`
                /* Markdown 内容样式 */
                .message-content h1 {
                    font-size: 1.5em !important;
                    font-weight: bold !important;
                    margin: 0.8em 0 0.5em 0 !important;
                    border-bottom: 2px solid #3b82f6 !important;
                    padding-bottom: 0.3em !important;
                    color: #1a1a1a !important;
                }
                
                .message-content h2 {
                    font-size: 1.3em !important;
                    font-weight: bold !important;
                    margin: 0.6em 0 0.4em 0 !important;
                    color: #2a2a2a !important;
                }
                
                .message-content h3 {
                    font-size: 1.1em !important;
                    font-weight: bold !important;
                    margin: 0.5em 0 0.3em 0 !important;
                    color: #3a3a3a !important;
                }
                
                .message-content code {
                    background: rgba(0, 0, 0, 0.05) !important;
                    padding: 0.2em 0.4em !important;
                    border-radius: 3px !important;
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
                    font-size: 0.9em !important;
                    color: #c7254e !important;
                }
                
                .message-content pre {
                    background: #282c34 !important;
                    color: #abb2bf !important;
                    padding: 1em !important;
                    border-radius: 8px !important;
                    overflow-x: auto !important;
                    margin: 1em 0 !important;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1) !important;
                }
                
                .message-content pre code {
                    background: transparent !important;
                    padding: 0 !important;
                    color: #abb2bf !important;
                }
                
                /* LaTeX 公式样式 */
                .message-content .katex-display {
                    margin: 1.5em 0 !important;
                    text-align: center !important;
                }
                
                .message-content .katex {
                    font-size: 1.1em !important;
                }
                
                /* 表格样式 */
                .message-content table {
                    border-collapse: collapse !important;
                    width: 100% !important;
                    margin: 1em 0 !important;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1) !important;
                }
                
                .message-content th,
                .message-content td {
                    border: 1px solid #ddd !important;
                    padding: 12px !important;
                    text-align: left !important;
                }
                
                .message-content th {
                    background-color: #3b82f6 !important;
                    color: white !important;
                    font-weight: bold !important;
                }
                
                .message-content tr:nth-child(even) {
                    background-color: #f8f9fa !important;
                }
                
                /* 列表样式 */
                .message-content ul,
                .message-content ol {
                    margin: 0.8em 0 !important;
                    padding-left: 2em !important;
                }
                
                .message-content li {
                    margin: 0.4em 0 !important;
                    line-height: 1.6 !important;
                }
                
                /* 引用样式 */
                .message-content blockquote {
                    border-left: 4px solid #3b82f6 !important;
                    padding-left: 1em !important;
                    margin: 1em 0 !important;
                    color: #666 !important;
                    background: #f8f9fa !important;
                    padding: 0.5em 1em !important;
                    border-radius: 4px !important;
                }
                
                /* 强调样式 */
                .message-content strong {
                    color: #1a1a1a !important;
                    font-weight: bold !important;
                }
                
                .message-content em {
                    color: #555 !important;
                    font-style: italic !important;
                }
            \`;
            document.head.appendChild(style);
            
            function initRenderer() {
                let renderQueue = [];
                let isRendering = false;
                
                // 渲染函数
                function renderMarkdownAndLatex(element) {
                    if (!element || !element.textContent || element.dataset.rendered === 'true') {
                        return;
                    }
                    
                    let content = element.textContent.trim();
                    if (!content) return;
                    
                    try {
                        // 1. 保护代码块
                        const codeBlocks = [];
                        content = content.replace(/\`\`\`([\\s\\S]*?)\`\`\`/g, (match, code) => {
                            codeBlocks.push(code.trim());
                            return \`__CODE_BLOCK_\${codeBlocks.length - 1}__\`;
                        });
                        
                        // 2. 处理数学公式
                        const mathBlocks = [];
                        // 块级公式 $$...$$
                        content = content.replace(/\\$\\$([\\s\\S]+?)\\$\\$/g, (match, formula) => {
                            mathBlocks.push({ type: 'block', formula: formula.trim() });
                            return \`__MATH_BLOCK_\${mathBlocks.length - 1}__\`;
                        });
                        // 行内公式 $...$
                        content = content.replace(/\\$([^$\\n]+?)\\$/g, (match, formula) => {
                            mathBlocks.push({ type: 'inline', formula: formula.trim() });
                            return \`__MATH_INLINE_\${mathBlocks.length - 1}__\`;
                        });
                        
                        // 3. Markdown 渲染
                        if (window.marked) {
                            content = marked.parse(content, {
                                breaks: true,
                                gfm: true
                            });
                        }
                        
                        // 4. 恢复数学公式
                        if (window.katex) {
                            mathBlocks.forEach((item, index) => {
                                const placeholder = item.type === 'block' 
                                    ? \`__MATH_BLOCK_\${index}__\` 
                                    : \`__MATH_INLINE_\${index}__\`;
                                
                                try {
                                    const rendered = katex.renderToString(item.formula, {
                                        displayMode: item.type === 'block',
                                        throwOnError: false,
                                        trust: true
                                    });
                                    content = content.replace(placeholder, rendered);
                                } catch (e) {
                                    console.error('KaTeX render error:', e, item.formula);
                                    const fallback = item.type === 'block' 
                                        ? \`<div class="math-error">$$\${item.formula}$$</div>\`
                                        : \`<span class="math-error">$\${item.formula}$</span>\`;
                                    content = content.replace(placeholder, fallback);
                                }
                            });
                        }
                        
                        // 5. 恢复代码块
                        codeBlocks.forEach((code, index) => {
                            const lang = code.split('\\n')[0];
                            const codeContent = code.includes('\\n') ? code.split('\\n').slice(1).join('\\n') : code;
                            const highlighted = \`<pre><code>\${codeContent}</code></pre>\`;
                            content = content.replace(\`__CODE_BLOCK_\${index}__\`, highlighted);
                        });
                        
                        // 更新元素内容
                        element.innerHTML = content;
                        element.dataset.rendered = 'true';
                        
                    } catch (e) {
                        console.error('Render error:', e);
                        element.dataset.rendered = 'true';
                    }
                }
                
                // 批处理渲染
                async function processRenderQueue() {
                    if (isRendering || renderQueue.length === 0) return;
                    
                    isRendering = true;
                    while (renderQueue.length > 0) {
                        const element = renderQueue.shift();
                        renderMarkdownAndLatex(element);
                        await new Promise(resolve => setTimeout(resolve, 10));
                    }
                    isRendering = false;
                }
                
                // MutationObserver 监听新消息
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        mutation.addedNodes.forEach((node) => {
                            if (node.nodeType === 1) {
                                // 查找所有可能包含消息内容的元素
                                const messageElements = node.querySelectorAll 
                                    ? node.querySelectorAll('.message-content, .chat-message, [class*="message"]')
                                    : [];
                                
                                if (node.classList && (
                                    node.classList.contains('message-content') || 
                                    node.classList.contains('chat-message') ||
                                    node.className.includes('message')
                                )) {
                                    renderQueue.push(node);
                                }
                                
                                messageElements.forEach(el => {
                                    if (el.dataset.rendered !== 'true') {
                                        renderQueue.push(el);
                                    }
                                });
                            }
                        });
                    });
                    
                    processRenderQueue();
                });
                
                // 开始观察
                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                    characterData: true
                });
                
                // 初始渲染已存在的消息
                setTimeout(() => {
                    const existingMessages = document.querySelectorAll('.message-content, .chat-message, [class*="message"]');
                    existingMessages.forEach(el => {
                        if (el.textContent && el.dataset.rendered !== 'true') {
                            renderQueue.push(el);
                        }
                    });
                    processRenderQueue();
                }, 500);
                
                console.log('Markdown and LaTeX renderer initialized!');
            }
        })();
    `).catch(err => {
        console.error('Failed to inject renderer:', err);
    });
}

// 注册快捷键
function registerShortcuts() {
    // Ctrl+Shift+L: 切换桌宠/正常模式
    globalShortcut.register('CommandOrControl+Shift+L', () => {
        toggleMode();
    });

    // Ctrl+Shift+H: 隐藏/显示窗口
    globalShortcut.register('CommandOrControl+Shift+H', () => {
        if (mainWindow) {
            if (mainWindow.isVisible()) {
                mainWindow.hide();
            } else {
                mainWindow.show();
            }
        }
    });

    // Ctrl+Shift+Q: 退出应用
    globalShortcut.register('CommandOrControl+Shift+Q', () => {
        app.quit();
    });
}

// 切换桌宠/正常模式
function toggleMode() {
    if (!mainWindow) return;
    
    isDesktopPetMode = !isDesktopPetMode;
    
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    const petWidth = 400;
    const petHeight = 600;
    const normalWidth = Math.min(1200, width - 100);
    const normalHeight = Math.min(800, height - 100);
    
    // 调整窗口大小和位置
    mainWindow.setSize(
        isDesktopPetMode ? petWidth : normalWidth,
        isDesktopPetMode ? petHeight : normalHeight
    );
    
    mainWindow.setPosition(
        isDesktopPetMode ? width - petWidth - 20 : Math.max(0, width - normalWidth - 50),
        isDesktopPetMode ? height - petHeight - 20 : Math.max(0, height - normalHeight - 50)
    );
    
    mainWindow.setResizable(!isDesktopPetMode);
    mainWindow.setSkipTaskbar(isDesktopPetMode);
    
    // 重新加载以应用新样式
    mainWindow.reload();
}

// IPC 通信处理
ipcMain.on('toggle-mode', () => {
    toggleMode();
});

ipcMain.on('quit-app', () => {
    app.quit();
});

// 获取鼠标位置（用于 Live2D 鼠标跟随）
let cursorLogCounter = 0;
ipcMain.on('get-cursor-position', (event) => {
    const cursorPos = screen.getCursorScreenPoint();
    const winBounds = mainWindow ? mainWindow.getBounds() : { x: 0, y: 0 };
    const posData = {
        screenX: cursorPos.x,
        screenY: cursorPos.y,
        relativeX: cursorPos.x - winBounds.x,
        relativeY: cursorPos.y - winBounds.y
    };
    // 每100次打印一次日志（避免刷屏）
    cursorLogCounter++;
    if (cursorLogCounter % 100 === 1) {
        console.log('🖱️ [Main] 鼠标位置:', posData);
    }
    event.reply('cursor-position', posData);
});

// 最小化窗口（隐藏到托盘）
ipcMain.on('minimize-window', () => {
    if (mainWindow) {
        mainWindow.hide();  // 隐藏到托盘而不是最小化
        console.log('窗口已隐藏到托盘');
    }
});

// 强制窗口获得焦点（修复 confirm 对话框后焦点丢失问题）
ipcMain.on('focus-window', () => {
    if (mainWindow) {
        // 多种方法确保窗口获得焦点
        if (mainWindow.isMinimized()) {
            mainWindow.restore();
        }
        mainWindow.show();
        mainWindow.focus();
        // Windows 特有：使用 setAlwaysOnTop 技巧强制获得焦点
        const wasAlwaysOnTop = mainWindow.isAlwaysOnTop();
        mainWindow.setAlwaysOnTop(true);
        mainWindow.setAlwaysOnTop(wasAlwaysOnTop);
        // 发送消息通知渲染进程聚焦输入框
        mainWindow.webContents.send('do-focus-input');
    }
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

app.on('will-quit', () => {
    // 注销所有快捷键
    globalShortcut.unregisterAll();
});