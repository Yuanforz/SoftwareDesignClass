// ==================== 全局状态管理 ====================
const AppState = {
    ws: null,
    connected: false,
    micEnabled: true,
    autoScroll: true,
    markdownEnabled: true,
    latexEnabled: true,
    currentHistoryUid: null,
    live2dApp: null,
    live2dModel: null,
    // 新增：待发送的附件列表
    pendingAttachments: [],
    
    // Live2D 模型配置（从后端加载）
    modelConfig: {
        url: null,           // 模型 URL
        name: null,          // 模型名称
        kScale: 0.5,         // 缩放系数
        loaded: false,       // 是否已加载
    },
    
    // 灵犀助教特有设置（与后端 lingxi_settings 同步）
    lingxiSettings: {
        ttsEngine: 'step_tts',        // 'step_tts' 或 'edge_tts'
        audioMergeEnabled: false,      // 音频合并生成
        multimodalAutoSwitch: true,    // 多模态自动切换
    },
    
    // 语音录制状态
    voiceRecording: {
        isRecording: false,           // 是否正在录音
        isPushToTalk: false,          // 是否按键录音模式
        audioContext: null,           // AudioContext
        mediaStream: null,            // MediaStream
        analyser: null,               // AnalyserNode 用于音量检测
        processor: null,              // ScriptProcessor 用于捕获音频
        audioChunks: [],              // 录音数据块
        silenceStart: null,           // 静音开始时间
        lastSpeechTime: null,         // 最后检测到语音的时间
        vadEnabled: true,             // VAD 自动检测是否启用
        vadThreshold: 15,             // VAD 音量阈值 (0-100)
        silenceTimeout: 1500,         // 静音超时时间 (ms)，超过这个时间认为说话结束
        minRecordTime: 500,           // 最小录音时间 (ms)
        // 唤醒词设置
        wakeWordEnabled: false,       // 是否启用唤醒词检测
        wakeWords: ['灵犀', '小灵', '助教'],  // 唤醒词列表
        fuzzyPinyinMatch: true,       // 是否启用模糊拼音匹配
        voicePromptInjection: true,   // 是否启用语音提示词注入
    }
};

// ==================== WebSocket 连接 ====================
function connectWebSocket() {
    const wsUrl = 'ws://127.0.0.1:12393/client-ws';
    
    AppState.ws = new WebSocket(wsUrl);
    
    AppState.ws.onopen = () => {
        console.log('✅ WebSocket 连接成功');
        AppState.connected = true;
        
        // 请求初始配置
        sendMessage({ type: 'request-init-config' });
        
        // 启动麦克风（如果启用）
        if (AppState.micEnabled) {
            sendMessage({ type: 'control', text: 'start-mic' });
        }
    };
    
    AppState.ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (error) {
            console.error('❌ 消息解析失败:', error);
        }
    };
    
    AppState.ws.onerror = (error) => {
        console.error('❌ WebSocket 错误:', error);
    };
    
    AppState.ws.onclose = () => {
        console.log('⚠️ WebSocket 连接关闭，3秒后重连...');
        AppState.connected = false;
        setTimeout(connectWebSocket, 3000);
    };
}

// 发送消息到后端
function sendMessage(message) {
    if (AppState.ws && AppState.ws.readyState === WebSocket.OPEN) {
        const jsonStr = JSON.stringify(message);
        console.log('📤 发送消息:', message);
        console.log('📤 JSON字符串:', jsonStr);
        AppState.ws.send(jsonStr);
    } else {
        console.warn('⚠️ WebSocket 未连接，无法发送消息');
        console.warn('⚠️ WebSocket 状态:', AppState.ws ? AppState.ws.readyState : 'null');
    }
}

// ==================== WebSocket 消息处理 ====================
function handleWebSocketMessage(data) {
    console.log('📩 收到消息:', data);
    
    switch (data.type) {
        case 'full-text':
            // 完整回答
            addMessage('assistant', data.text);
            break;
            
        case 'text-stream':
            // 流式回答（未完成，继续累积）
            updateStreamingMessage(data.text);
            break;
            
        case 'llm-output':
            // LLM 输出（带 display_text）
            if (data.display_text && data.display_text.text) {
                addMessage('assistant', data.display_text.text);
            }
            break;
        
        case 'audio':
            // 音频消息（包含 TTS 和文本）
            if (data.display_text && data.display_text.text) {
                // 移除情感标签（如 [joy], [sad] 等）
                const cleanText = data.display_text.text.replace(/\[\w+\]\s*/g, '');
                console.log('🎤 收到音频消息:', cleanText);
                
                // 检查是否是合并音频消息
                if (data.merge_info && data.merge_info.is_merged) {
                    // 收集合并消息，等全部到齐后再处理
                    AudioQueue.collectMergedMessage(data.audio, cleanText, data.merge_info);
                } else {
                    // 非合并消息：正常处理
                    if (data.audio) {
                        AudioQueue.enqueue(data.audio, cleanText);
                    }
                }
            }
            break;
        
        case 'backend-synth-complete':
            // 后端 TTS 合成完成
            console.log('✅ TTS 合成完成');
            break;
            
        case 'control':
            const controlText = data.text || '';
            console.log('🎮 Control 消息:', controlText);
            
            if (controlText === 'start-mic') {
                updateMicStatus(true);
            } else if (controlText === 'stop-mic') {
                updateMicStatus(false);
            } else if (controlText === 'conversation-chain-start') {
                console.log('🔗 对话链开始');
            } else if (controlText === 'interrupt') {
                // 收到打断信号，停止所有音频
                console.log('🛑 收到打断信号');
                stopAllAudio();
            } else if (controlText === 'mic-audio-end') {
                console.log('🎤 麦克风音频结束');
            }
            break;
            
        case 'error':
            addMessage('assistant', `❌ 错误: ${data.text}`);
            break;
        
        case 'user-input-transcription':
            // 语音识别结果 - 检查唤醒词
            const transcribedText = data.text || '';
            if (transcribedText.trim()) {
                console.log('🗣️ 语音识别结果:', transcribedText);
                
                // 后端已经处理过唤醒词检测（包括拼音模糊匹配），
                // 如果能收到这个消息，说明已经通过了唤醒词检测或未启用唤醒词
                // 前端只需要显示文本即可
                addMessage('user', transcribedText);
            }
            break;
        
        case 'group-update':
            // 群组状态更新（暂不处理）
            console.log('群组状态:', data.members);
            break;
        
        case 'set-model-and-conf':
            // 模型和配置信息
            console.log('角色配置:', data.conf_name);
            
            // 保存模型配置
            if (data.model_info) {
                AppState.modelConfig.url = data.model_info.url;
                AppState.modelConfig.name = data.model_info.name;
                AppState.modelConfig.kScale = data.model_info.kScale || 0.5;
                console.log('🎭 模型配置:', AppState.modelConfig);
                
                // 如果 Live2D 已初始化但模型未加载，现在加载
                if (AppState.live2dApp && !AppState.modelConfig.loaded) {
                    loadLive2DModel();
                }
            }
            
            // 连接成功后，请求获取灵犀设置
            sendMessage({ type: 'fetch-lingxi-settings' });
            break;
        
        case 'lingxi-settings':
            // 收到灵犀设置
            if (data.settings) {
                AppState.lingxiSettings.ttsEngine = data.settings.tts_engine || 'step_tts';
                AppState.lingxiSettings.audioMergeEnabled = data.settings.audio_merge_enabled || false;
                AppState.lingxiSettings.multimodalAutoSwitch = data.settings.multimodal_auto_switch !== false;
                console.log('✅ 灵犀设置已同步:', AppState.lingxiSettings);
            }
            break;
        
        case 'lingxi-settings-updated':
            // 设置更新结果
            if (data.success) {
                console.log('✅ 灵犀设置保存成功');
            } else {
                console.error('❌ 灵犀设置保存失败:', data.error);
                showToast('❌ 设置保存失败');
            }
            break;
            
        default:
            console.log('未处理的消息类型:', data.type);
    }
}

// ==================== 消息显示 ====================
const messagesContainer = document.getElementById('chat-messages');
let currentStreamingBubble = null;

function addMessage(sender, text, isStreaming = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    
    const content = document.createElement('div');
    content.className = 'bubble-content';
    
    if (isStreaming) {
        content.textContent = text;
        currentStreamingBubble = content;
    } else {
        currentStreamingBubble = null;
        renderMarkdownAndLatex(content, text);
    }
    
    bubble.appendChild(content);
    messageDiv.appendChild(bubble);
    messagesContainer.appendChild(messageDiv);
    
    if (AppState.autoScroll) {
        scrollToBottom();
    }
    
    return content;
}

function updateStreamingMessage(text) {
    if (!currentStreamingBubble) {
        currentStreamingBubble = addMessage('assistant', text, true);
    } else {
        currentStreamingBubble.textContent += text;
        if (AppState.autoScroll) {
            scrollToBottom();
        }
    }
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ==================== 音频播放 ====================
const AudioQueue = {
    queue: [],
    isPlaying: false,
    currentAudio: null,
    
    // 合并消息收集器
    mergedCollector: {
        messages: [],       // 收集到的消息
        expectedCount: 0,   // 期望的总数
        timer: null,        // 超时定时器
    },
    
    // 延迟显示的定时器列表（用于停止时清除）
    pendingDisplayTimers: [],
    
    // 检查是否是Markdown标题（不显示也不播放）
    isMarkdownHeading(text) {
        return /^#+\s+/.test(text.trim());
    },
    
    // 收集合并消息
    collectMergedMessage(audio, text, mergeInfo) {
        // 过滤Markdown标题
        if (this.isMarkdownHeading(text)) {
            console.log(`🚫 过滤合并消息中的Markdown标题: "${text}"`);
            // 减少期望的总数
            mergeInfo.total_sentences = Math.max(1, mergeInfo.total_sentences - 1);
            return;
        }
        
        const collector = this.mergedCollector;
        
        console.log(`🔗 收集合并消息: 句子 ${mergeInfo.sentence_index + 1}/${mergeInfo.total_sentences}, "${text.substring(0, 30)}..."`);
        
        // 存储消息
        collector.messages.push({ audio, text, mergeInfo });
        collector.expectedCount = mergeInfo.total_sentences;
        
        // 清除之前的超时定时器
        if (collector.timer) {
            clearTimeout(collector.timer);
        }
        
        // 检查是否收集完毕
        if (collector.messages.length >= collector.expectedCount) {
            console.log(`✅ 合并消息收集完毕: ${collector.messages.length}/${collector.expectedCount}`);
            this.processMergedMessages();
        } else {
            // 设置超时定时器（500ms 内没有新消息就强制处理）
            collector.timer = setTimeout(() => {
                console.log(`⚠️ 合并消息超时，强制处理: ${collector.messages.length}/${collector.expectedCount}`);
                this.processMergedMessages();
            }, 500);
        }
    },
    
    // 处理收集完毕的合并消息
    processMergedMessages() {
        const collector = this.mergedCollector;
        
        if (collector.timer) {
            clearTimeout(collector.timer);
            collector.timer = null;
        }
        
        if (collector.messages.length === 0) {
            return;
        }
        
        // 按 sentence_index 排序
        const sorted = collector.messages.slice().sort((a, b) => 
            a.mergeInfo.sentence_index - b.mergeInfo.sentence_index
        );
        
        console.log(`🔗 处理合并消息（已排序）:`, sorted.map(m => ({
            index: m.mergeInfo.sentence_index,
            delay: m.mergeInfo.delay_before_show_ms || 0,
            hasAudio: !!m.audio,
            text: m.text.substring(0, 25)
        })));
        
        // 清空收集器
        collector.messages = [];
        collector.expectedCount = 0;
        
        // 找到携带音频的那条（sentence_index=0）
        const audioMessage = sorted.find(m => m.audio);
        if (!audioMessage) {
            console.error('❌ 合并消息中没有找到音频');
            return;
        }
        
        // 入队：携带音频 + 所有句子的显示信息
        this.queue.push({
            base64Audio: audioMessage.audio,
            text: audioMessage.text,
            isMerged: true,
            mergedSentences: sorted  // 所有句子（已排序）
        });
        
        console.log(`📜 合并音频入队，包含 ${sorted.length} 个句子，队列长度: ${this.queue.length}`);
        
        if (!this.isPlaying) {
            this.playNext();
        }
    },
    
    // 添加普通音频到队列
    enqueue(base64Audio, text) {
        // 过滤Markdown标题（不显示也不发声）
        if (this.isMarkdownHeading(text)) {
            console.log(`🚫 过滤Markdown标题: "${text}"`);
            return;
        }
        
        this.queue.push({ base64Audio, text, isMerged: false });
        console.log(`📜 音频入队: "${text}", 队列长度: ${this.queue.length}`);
        
        // 如果没有正在播放，开始播放
        if (!this.isPlaying) {
            this.playNext();
        }
    },
    
    // 播放下一个音频
    async playNext() {
        if (this.queue.length === 0) {
            this.isPlaying = false;
            console.log('✅ 音频队列为空');
            return;
        }
        
        this.isPlaying = true;
        const item = this.queue.shift();
        
        if (item.isMerged && item.mergedSentences) {
            // 合并消息：播放音频 + 按时间显示各句子
            console.log(`🔊 开始播放合并音频，共 ${item.mergedSentences.length} 个句子`);
            
            // 清空之前的延迟显示定时器
            this.clearPendingDisplayTimers();
            
            // 立即显示第一句
            const firstSentence = item.mergedSentences[0];
            console.log(`💬 显示第1句: "${firstSentence.text}"`);
            addMessage('assistant', firstSentence.text);
            
            // 设置后续句子的延迟显示
            for (let i = 1; i < item.mergedSentences.length; i++) {
                const sentence = item.mergedSentences[i];
                const delayMs = sentence.mergeInfo.delay_before_show_ms || 0;
                console.log(`⏱️ 第${i+1}句将在 ${delayMs}ms 后显示: "${sentence.text.substring(0, 30)}..."`);
                
                const timerId = setTimeout(() => {
                    console.log(`💬 延迟显示第${i+1}句: "${sentence.text}"`);
                    addMessage('assistant', sentence.text);
                    // 从待处理列表中移除
                    const idx = this.pendingDisplayTimers.indexOf(timerId);
                    if (idx > -1) this.pendingDisplayTimers.splice(idx, 1);
                }, delayMs);
                
                // 记录定时器ID
                this.pendingDisplayTimers.push(timerId);
            }
            
            // 播放音频
            try {
                await this.playAudioFromBase64(item.base64Audio);
                console.log(`✅ 合并音频播放完成`);
            } catch (error) {
                console.error('❌ 播放失败:', error);
            }
        } else {
            // 普通消息：显示文本 + 播放音频
            console.log(`💬 显示文本: "${item.text}"`);
            addMessage('assistant', item.text);
            
            console.log(`🔊 开始播放: "${item.text}", 剩余: ${this.queue.length}`);
            
            try {
                await this.playAudioFromBase64(item.base64Audio);
                console.log(`✅ 播放完成: "${item.text}"`);
            } catch (error) {
                console.error('❌ 播放失败:', error);
            }
        }
        
        // 播放下一个
        this.playNext();
    },
    
    // 播放单个音频
    playAudioFromBase64(base64Audio) {
        return new Promise((resolve, reject) => {
            try {
                // 解码 Base64
                const binaryString = atob(base64Audio);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                
                // 创建 Blob
                const blob = new Blob([bytes], { type: 'audio/wav' });
                const url = URL.createObjectURL(blob);
                
                // 创建并播放音频
                const audio = new Audio(url);
                audio.volume = 1.0;
                this.currentAudio = audio;
                
                audio.onended = () => {
                    URL.revokeObjectURL(url);
                    this.currentAudio = null;
                    resolve();
                };
                
                audio.onerror = (e) => {
                    console.error('❌ 音频播放错误:', e);
                    URL.revokeObjectURL(url);
                    this.currentAudio = null;
                    reject(e);
                };
                
                audio.play().catch(err => {
                    console.error('❌ 音频播放被阻止:', err);
                    console.log('💡 请点击页面任意位置来激活音频播放');
                    URL.revokeObjectURL(url);
                    this.currentAudio = null;
                    reject(err);
                });
                
            } catch (error) {
                console.error('❌ 音频解码失败:', error);
                reject(error);
            }
        });
    },
    
    // 停止所有音频并清空队列
    stopAll() {
        console.log('🛑 停止所有音频');
        
        // 停止当前播放的音频
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
        
        // 清空队列
        this.queue = [];
        
        // 清空合并消息收集器
        if (this.mergedCollector.timer) {
            clearTimeout(this.mergedCollector.timer);
            this.mergedCollector.timer = null;
        }
        this.mergedCollector.messages = [];
        this.mergedCollector.expectedCount = 0;
        
        // 清除所有待处理的延迟显示定时器
        this.clearPendingDisplayTimers();
        
        this.isPlaying = false;
        
        console.log('✅ 所有音频已停止，延迟显示已取消');
    },
    
    // 清除所有待处理的延迟显示定时器
    clearPendingDisplayTimers() {
        if (this.pendingDisplayTimers.length > 0) {
            console.log(`🧹 清除 ${this.pendingDisplayTimers.length} 个待处理的延迟显示定时器`);
            for (const timerId of this.pendingDisplayTimers) {
                clearTimeout(timerId);
            }
            this.pendingDisplayTimers = [];
        }
    }
};

// 全局函数入口（保持兼容性）
function stopAllAudio() {
    AudioQueue.stopAll();
}

// ==================== Markdown & LaTeX 渲染 ====================
function renderMarkdownAndLatex(element, text) {
    if (!AppState.markdownEnabled) {
        element.textContent = text;
        return;
    }
    
    try {
        // 1. 提取并保护LaTeX公式（使用唯一标识符）
        const formulas = {
            inline: [],
            block: []
        };
        
        // 生成唯一ID
        const uid = Date.now().toString(36);
        
        // 提取块级公式 $$...$$
        let processedText = text.replace(/\$\$([\s\S]*?)\$\$/g, (match, formula) => {
            const index = formulas.block.length;
            formulas.block.push(formula.trim());
            return `【BLOCK${uid}_${index}】`;
        });
        
        // 提取行内公式 $...$
        processedText = processedText.replace(/\$([^\$\n]+?)\$/g, (match, formula) => {
            const index = formulas.inline.length;
            formulas.inline.push(formula.trim());
            return `【INLINE${uid}_${index}】`;
        });
        
        console.log('📐 提取公式:', { inline: formulas.inline.length, block: formulas.block.length });
        
        // 2. Markdown 渲染
        if (typeof marked !== 'undefined') {
            processedText = marked.parse(processedText);
        }
        
        // 3. 设置HTML
        element.innerHTML = processedText;
        
        // 4. 替换公式占位符为实际的DOM元素
        // 先处理块级公式
        formulas.block.forEach((formula, index) => {
            const placeholder = `【BLOCK${uid}_${index}】`;
            const regex = new RegExp(placeholder, 'g');
            element.innerHTML = element.innerHTML.replace(
                regex,
                `<div class="math-block" data-idx="${index}" data-uid="${uid}"></div>`
            );
        });
        
        // 再处理行内公式
        formulas.inline.forEach((formula, index) => {
            const placeholder = `【INLINE${uid}_${index}】`;
            const regex = new RegExp(placeholder, 'g');
            element.innerHTML = element.innerHTML.replace(
                regex,
                `<span class="math-inline" data-idx="${index}" data-uid="${uid}"></span>`
            );
        });
        
        // 5. 渲染所有公式
        if (AppState.latexEnabled && typeof katex !== 'undefined') {
            // 渲染块级公式
            element.querySelectorAll(`.math-block[data-uid="${uid}"]`).forEach(div => {
                const idx = parseInt(div.dataset.idx);
                const formula = formulas.block[idx];
                if (formula) {
                    try {
                        katex.render(formula, div, { 
                            displayMode: true,
                            throwOnError: false 
                        });
                        console.log('✅ 渲染块级公式:', formula.substring(0, 30));
                    } catch (e) {
                        console.error('❌ KaTeX渲染失败:', e);
                        div.textContent = `$$ ${formula} $$`;
                    }
                }
            });
            
            // 渲染行内公式
            element.querySelectorAll(`.math-inline[data-uid="${uid}"]`).forEach(span => {
                const idx = parseInt(span.dataset.idx);
                const formula = formulas.inline[idx];
                if (formula) {
                    try {
                        katex.render(formula, span, { 
                            displayMode: false,
                            throwOnError: false 
                        });
                        console.log('✅ 渲染行内公式:', formula.substring(0, 30));
                    } catch (e) {
                        console.error('❌ KaTeX渲染失败:', e);
                        span.textContent = `$ ${formula} $`;
                    }
                }
            });
        }
    } catch (error) {
        console.error('❌ 渲染失败:', error);
        element.textContent = text;
    }
}

// ==================== 输入处理 ====================
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const inputArea = document.getElementById('input-area');

// 发送消息
function sendTextMessage() {
    const text = textInput.value.trim();
    const hasAttachments = AppState.pendingAttachments.length > 0;
    
    if (!text && !hasAttachments) {
        console.warn('⚠️ 输入为空且无附件，不发送');
        return;
    }
    
    // 如果有附件但没有文字，提示用户
    if (hasAttachments && !text) {
        console.warn('⚠️ 请输入问题后再发送');
        textInput.placeholder = '请输入您的问题...';
        textInput.focus();
        return;
    }
    
    console.log('📝 准备发送文本消息:', text);
    
    // 构建显示消息
    let displayText = text;
    if (hasAttachments) {
        const imageCount = AppState.pendingAttachments.filter(a => a.type === 'image').length;
        const pdfCount = AppState.pendingAttachments.filter(a => a.type === 'pdf').length;
        const attachInfo = [];
        if (imageCount > 0) attachInfo.push(`${imageCount}张图片`);
        if (pdfCount > 0) attachInfo.push(`${pdfCount}个PDF`);
        displayText = `📎 [${attachInfo.join(', ')}]\n${text}`;
    }
    
    // 显示用户消息
    addMessage('user', displayText);
    
    // 准备图片数据（后端只接受图片格式的base64）
    const images = AppState.pendingAttachments.map(att => att.data);
    
    // 发送到后端
    sendMessage({
        type: 'text-input',
        text: text,
        images: images
    });
    
    // 清空输入框和附件
    textInput.value = '';
    textInput.style.height = 'auto';
    textInput.placeholder = '输入问题... (Ctrl+/ 唤起)';
    clearAllAttachments();
}

sendBtn.addEventListener('click', sendTextMessage);

textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
        e.preventDefault();
        sendTextMessage();
    }
});

// 自动调整输入框高度
textInput.addEventListener('input', () => {
    textInput.style.height = 'auto';
    textInput.style.height = textInput.scrollHeight + 'px';
});

// ==================== 快捷键管理 ====================
document.addEventListener('keydown', (e) => {
    // Ctrl + / - 显示/隐藏输入框
    if (e.ctrlKey && e.key === '/') {
        e.preventDefault();
        toggleInputArea();
    }
    
    // ESC - 隐藏输入框和菜单
    if (e.key === 'Escape') {
        inputArea.classList.add('hidden');
        hideContextMenu();
    }
});

function toggleInputArea() {
    const isHidden = inputArea.classList.contains('hidden');
    if (isHidden) {
        inputArea.classList.remove('hidden');
        textInput.focus();
    } else {
        inputArea.classList.add('hidden');
    }
}

// 鼠标悬停在对话区域时显示输入框
const chatSection = document.getElementById('chat-section');
chatSection.addEventListener('mouseenter', () => {
    inputArea.classList.remove('hidden');
});

// ==================== Live2D 交互 ====================
const live2dCanvas = document.getElementById('live2d-canvas');
const live2dSection = document.getElementById('live2d-section');

// 左键点击 - 打断回答（绑定到section而不是canvas）
live2dSection.addEventListener('click', (e) => {
    if (e.button === 0) { // 左键
        console.log('🛑 发送打断信号');
        sendMessage({ type: 'interrupt-signal' });
        // 立即停止所有音频
        stopAllAudio();
    }
});

// 右键点击 - 显示圆形菜单（绑定到section而不是canvas）
live2dSection.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    console.log('🖱️ 右键点击 Live2D 区域');
    showContextMenu(e.clientX, e.clientY);
});

// ==================== 圆形右键菜单 ====================
const contextMenu = document.getElementById('context-menu');

function showContextMenu(x, y) {
    contextMenu.classList.remove('hidden');
    contextMenu.classList.add('visible');
    
    // 菜单居中在鼠标位置
    contextMenu.style.left = (x - 100) + 'px';
    contextMenu.style.top = (y - 100) + 'px';
}

function hideContextMenu() {
    contextMenu.classList.remove('visible');
    contextMenu.classList.add('hidden');
}

// 点击页面其他地方隐藏菜单
document.addEventListener('click', (e) => {
    if (!contextMenu.contains(e.target) && !live2dSection.contains(e.target)) {
        hideContextMenu();
    }
});

// 菜单项点击处理
document.querySelectorAll('.menu-item').forEach(item => {
    item.addEventListener('click', () => {
        const action = item.dataset.action;
        handleMenuAction(action);
        hideContextMenu();
    });
});

function handleMenuAction(action) {
    switch (action) {
        case 'toggle-mic':
            toggleMicrophone();
            break;
        case 'history':
            showHistoryModal();
            break;
        case 'settings':
            showSettingsModal();
            break;
        case 'clear':
            clearMessages();
            break;
        case 'upload':
            triggerFileUpload();
            break;
        case 'quit':
            quitApplication();
            break;
    }
}

// 退出应用程序
function quitApplication() {
    if (confirm('确定要退出灵犀助教吗？')) {
        // 尝试通过 Electron IPC 退出
        if (window.electronAPI && window.electronAPI.quit) {
            window.electronAPI.quit();
        } else if (typeof require !== 'undefined') {
            // 直接使用 electron remote
            try {
                const { ipcRenderer } = require('electron');
                ipcRenderer.send('quit-app');
            } catch (e) {
                // 如果无法使用 IPC，尝试关闭窗口
                window.close();
            }
        } else {
            // 普通浏览器环境，尝试关闭窗口
            window.close();
        }
    }
}

// ==================== 功能实现 ====================

// ==================== 唤醒词检测 ====================

/**
 * 检查文本是否包含唤醒词
 * @param {string} text - 要检查的文本
 * @returns {object} - { hasWakeWord: boolean, matchedWord: string, cleanText: string }
 */
function checkWakeWord(text) {
    const vr = AppState.voiceRecording;
    const normalizedText = text.toLowerCase().trim();
    
    for (const wakeWord of vr.wakeWords) {
        const normalizedWakeWord = wakeWord.toLowerCase().trim();
        
        // 检查文本是否以唤醒词开头
        if (normalizedText.startsWith(normalizedWakeWord)) {
            // 去掉唤醒词和可能的分隔符（逗号、空格等）
            let cleanText = text.substring(wakeWord.length).trim();
            // 去掉开头的标点符号
            cleanText = cleanText.replace(/^[,，、。.!！?？\s]+/, '').trim();
            
            return {
                hasWakeWord: true,
                matchedWord: wakeWord,
                cleanText: cleanText
            };
        }
        
        // 也检查文本中间是否包含唤醒词（可能用户说"嗯灵犀"）
        const wakeWordIndex = normalizedText.indexOf(normalizedWakeWord);
        if (wakeWordIndex !== -1) {
            // 去掉唤醒词及其之前的内容
            let cleanText = text.substring(wakeWordIndex + wakeWord.length).trim();
            cleanText = cleanText.replace(/^[,，、。.!！?？\s]+/, '').trim();
            
            return {
                hasWakeWord: true,
                matchedWord: wakeWord,
                cleanText: cleanText
            };
        }
    }
    
    return {
        hasWakeWord: false,
        matchedWord: '',
        cleanText: text
    };
}

/**
 * 从 localStorage 加载唤醒词设置
 */
function loadWakeWordSettings() {
    const vr = AppState.voiceRecording;
    
    // 加载唤醒词启用状态
    const savedEnabled = localStorage.getItem('wakeWordEnabled');
    if (savedEnabled !== null) {
        vr.wakeWordEnabled = savedEnabled === 'true';
    }
    
    // 加载唤醒词列表
    const savedWords = localStorage.getItem('wakeWords');
    if (savedWords) {
        try {
            const words = JSON.parse(savedWords);
            if (Array.isArray(words) && words.length > 0) {
                vr.wakeWords = words;
            }
        } catch (e) {
            console.warn('加载唤醒词设置失败:', e);
        }
    }
    
    // 加载模糊拼音匹配设置
    const savedFuzzyPinyin = localStorage.getItem('fuzzyPinyinMatch');
    if (savedFuzzyPinyin !== null) {
        vr.fuzzyPinyinMatch = savedFuzzyPinyin === 'true';
    }
    
    // 加载语音提示词注入设置
    const savedVoicePrompt = localStorage.getItem('voicePromptInjection');
    if (savedVoicePrompt !== null) {
        vr.voicePromptInjection = savedVoicePrompt === 'true';
    }
    
    console.log(`🎤 唤醒词设置: ${vr.wakeWordEnabled ? '启用' : '禁用'}, 词汇: ${vr.wakeWords.join('/')}`);
    console.log(`🎤 模糊拼音: ${vr.fuzzyPinyinMatch ? '启用' : '禁用'}, 语音注入: ${vr.voicePromptInjection ? '启用' : '禁用'}`);
}

// ==================== 麦克风录音模块 ====================
const VoiceRecorder = {
    // 初始化音频录制
    async init() {
        const vr = AppState.voiceRecording;
        
        try {
            // 请求麦克风权限
            vr.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            
            // 创建 AudioContext
            vr.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });
            
            // 创建分析器用于检测音量
            vr.analyser = vr.audioContext.createAnalyser();
            vr.analyser.fftSize = 2048;
            vr.analyser.smoothingTimeConstant = 0.3;
            
            // 连接音频流到分析器
            const source = vr.audioContext.createMediaStreamSource(vr.mediaStream);
            source.connect(vr.analyser);
            
            // 创建 ScriptProcessor 用于捕获原始音频数据
            vr.processor = vr.audioContext.createScriptProcessor(4096, 1, 1);
            source.connect(vr.processor);
            vr.processor.connect(vr.audioContext.destination);
            
            // 处理音频数据
            vr.processor.onaudioprocess = (e) => {
                if (!AppState.micEnabled) return;
                
                const inputData = e.inputBuffer.getChannelData(0);
                const volume = this.getVolume();
                
                // 更新音量指示器
                this.updateVolumeIndicator(volume);
                
                if (vr.vadEnabled) {
                    this.handleVAD(inputData, volume);
                }
            };
            
            console.log('✅ 麦克风初始化成功');
            updateMicStatus(true);
            return true;
            
        } catch (error) {
            console.error('❌ 麦克风初始化失败:', error);
            showToast('❌ 无法访问麦克风，请检查权限');
            return false;
        }
    },
    
    // 获取当前音量 (0-100)
    getVolume() {
        const vr = AppState.voiceRecording;
        if (!vr.analyser) return 0;
        
        const dataArray = new Uint8Array(vr.analyser.frequencyBinCount);
        vr.analyser.getByteFrequencyData(dataArray);
        
        // 计算平均音量
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
        }
        return Math.round((sum / dataArray.length) * 100 / 256);
    },
    
    // 更新音量指示器
    updateVolumeIndicator(volume) {
        const volumeBar = document.getElementById('volume-bar');
        if (volumeBar) {
            volumeBar.style.width = `${Math.min(volume * 2, 100)}%`;
            
            // 根据音量改变颜色
            if (volume > AppState.voiceRecording.vadThreshold) {
                volumeBar.style.backgroundColor = '#4CAF50'; // 绿色 - 检测到语音
            } else {
                volumeBar.style.backgroundColor = '#666'; // 灰色 - 静音
            }
        }
    },
    
    // VAD 自动检测语音
    handleVAD(inputData, volume) {
        const vr = AppState.voiceRecording;
        const now = Date.now();
        
        // 检测到语音
        if (volume > vr.vadThreshold) {
            vr.lastSpeechTime = now;
            vr.silenceStart = null;
            
            // 如果还没开始录音，开始录音
            if (!vr.isRecording) {
                console.log('🎤 VAD: 检测到语音，开始录音');
                this.startRecording();
            }
            
            // 录制音频数据
            if (vr.isRecording) {
                // 转换为 Float32Array 并存储
                const chunk = new Float32Array(inputData.length);
                chunk.set(inputData);
                vr.audioChunks.push(chunk);
            }
        } else {
            // 静音状态
            if (vr.isRecording) {
                // 继续录制静音数据（保持连贯性）
                const chunk = new Float32Array(inputData.length);
                chunk.set(inputData);
                vr.audioChunks.push(chunk);
                
                // 记录静音开始时间
                if (!vr.silenceStart) {
                    vr.silenceStart = now;
                }
                
                // 检查是否静音超时
                const silenceDuration = now - vr.silenceStart;
                const recordingDuration = now - (vr.recordingStartTime || now);
                
                if (silenceDuration > vr.silenceTimeout && recordingDuration > vr.minRecordTime) {
                    console.log(`🎤 VAD: 静音 ${silenceDuration}ms，结束录音`);
                    this.stopRecordingAndSend();
                }
            }
        }
    },
    
    // 开始录音
    startRecording() {
        const vr = AppState.voiceRecording;
        if (vr.isRecording) return;
        
        vr.isRecording = true;
        vr.audioChunks = [];
        vr.recordingStartTime = Date.now();
        vr.silenceStart = null;
        
        // 更新 UI
        const micStatus = document.getElementById('mic-status');
        if (micStatus) {
            micStatus.classList.add('recording');
        }
        
        const micText = document.getElementById('mic-text');
        if (micText) {
            micText.textContent = '🔴 录音中...';
        }
        
        console.log('🎤 开始录音');
    },
    
    // 停止录音并发送
    async stopRecordingAndSend() {
        const vr = AppState.voiceRecording;
        if (!vr.isRecording) return;
        
        vr.isRecording = false;
        
        // 更新 UI
        const micStatus = document.getElementById('mic-status');
        if (micStatus) {
            micStatus.classList.remove('recording');
        }
        
        const micText = document.getElementById('mic-text');
        if (micText) {
            micText.textContent = '处理中...';
        }
        
        // 检查是否有录音数据
        if (vr.audioChunks.length === 0) {
            console.log('⚠️ 没有录音数据');
            if (micText) micText.textContent = '语音监听中...';
            return;
        }
        
        // 合并所有音频块
        const totalLength = vr.audioChunks.reduce((sum, chunk) => sum + chunk.length, 0);
        const mergedAudio = new Float32Array(totalLength);
        let offset = 0;
        for (const chunk of vr.audioChunks) {
            mergedAudio.set(chunk, offset);
            offset += chunk.length;
        }
        
        // 清空缓冲区
        vr.audioChunks = [];
        
        // 检查录音时长是否足够（至少 0.5 秒 = 8000 采样点 @ 16kHz）
        const minSamples = 8000;
        if (totalLength < minSamples) {
            console.log(`⚠️ 录音太短 (${(totalLength / 16000).toFixed(2)}秒)，忽略`);
            if (micText) micText.textContent = '语音监听中...';
            return;
        }
        
        // 检查音频是否有足够的能量（不是纯静音）
        let maxAmplitude = 0;
        let sumSquared = 0;
        for (let i = 0; i < mergedAudio.length; i++) {
            const abs = Math.abs(mergedAudio[i]);
            if (abs > maxAmplitude) maxAmplitude = abs;
            sumSquared += mergedAudio[i] * mergedAudio[i];
        }
        const rms = Math.sqrt(sumSquared / mergedAudio.length);
        
        // RMS 阈值：太小说明基本是静音
        const rmsThreshold = 0.01;
        if (rms < rmsThreshold) {
            console.log(`⚠️ 音频能量太低 (RMS=${rms.toFixed(4)})，可能是静音，忽略`);
            if (micText) micText.textContent = '语音监听中...';
            return;
        }
        
        console.log(`🎤 录音完成，共 ${totalLength} 采样点，约 ${(totalLength / 16000).toFixed(2)} 秒，RMS=${rms.toFixed(4)}`);
        
        // 发送音频数据到后端
        this.sendAudioToBackend(mergedAudio);
        
        if (micText) micText.textContent = '语音监听中...';
    },
    
    // 发送音频数据到后端
    sendAudioToBackend(audioData) {
        if (!AppState.connected) {
            console.warn('⚠️ WebSocket 未连接');
            return;
        }
        
        // 检查数据长度
        if (audioData.length < 8000) {
            console.warn('⚠️ 音频数据太短，不发送');
            return;
        }
        
        const vr = AppState.voiceRecording;
        
        // 发送音频数据（Float32Array 格式）
        const audioArray = Array.from(audioData);
        
        // 先发送音频数据
        sendMessage({
            type: 'mic-audio-data',
            audio: audioArray
        });
        
        // 然后发送结束信号，附带唤醒词设置
        sendMessage({
            type: 'mic-audio-end',
            wake_word_config: {
                enabled: vr.wakeWordEnabled,
                words: vr.wakeWords,
                fuzzy_pinyin: vr.fuzzyPinyinMatch,
                voice_prompt_injection: vr.voicePromptInjection
            }
        });
        
        console.log('📤 已发送音频数据和结束信号');
    },
    
    // 停止录制（不发送）
    cancelRecording() {
        const vr = AppState.voiceRecording;
        vr.isRecording = false;
        vr.audioChunks = [];
        
        const micStatus = document.getElementById('mic-status');
        if (micStatus) {
            micStatus.classList.remove('recording');
        }
        
        const micText = document.getElementById('mic-text');
        if (micText) {
            micText.textContent = '语音监听中...';
        }
    },
    
    // 销毁录制器
    destroy() {
        const vr = AppState.voiceRecording;
        
        if (vr.processor) {
            vr.processor.disconnect();
            vr.processor = null;
        }
        
        if (vr.analyser) {
            vr.analyser.disconnect();
            vr.analyser = null;
        }
        
        if (vr.mediaStream) {
            vr.mediaStream.getTracks().forEach(track => track.stop());
            vr.mediaStream = null;
        }
        
        if (vr.audioContext) {
            vr.audioContext.close();
            vr.audioContext = null;
        }
        
        vr.isRecording = false;
        vr.audioChunks = [];
    }
};

// ==================== 按键录音（Push-to-Talk）====================
const PushToTalk = {
    isHolding: false,
    
    // 初始化按键监听
    init() {
        // 空格键按下开始录音
        document.addEventListener('keydown', (e) => {
            // 如果正在输入文本，不触发按键录音
            if (document.activeElement.tagName === 'INPUT' || 
                document.activeElement.tagName === 'TEXTAREA') {
                return;
            }
            
            if (e.code === 'Space' && !this.isHolding && AppState.micEnabled) {
                e.preventDefault();
                this.isHolding = true;
                
                // 暂时禁用 VAD
                AppState.voiceRecording.vadEnabled = false;
                
                // 开始录音
                VoiceRecorder.startRecording();
                showToast('🎤 按住空格录音...');
            }
        });
        
        // 空格键松开停止录音
        document.addEventListener('keyup', (e) => {
            if (e.code === 'Space' && this.isHolding) {
                e.preventDefault();
                this.isHolding = false;
                
                // 停止并发送录音
                VoiceRecorder.stopRecordingAndSend();
                
                // 恢复 VAD
                setTimeout(() => {
                    AppState.voiceRecording.vadEnabled = true;
                }, 500);
            }
        });
        
        console.log('✅ 按键录音初始化完成 (按住空格键录音)');
    }
};

// 麦克风控制
function toggleMicrophone() {
    AppState.micEnabled = !AppState.micEnabled;
    
    if (AppState.micEnabled) {
        // 启用麦克风
        VoiceRecorder.init();
        sendMessage({ type: 'control', text: 'start-mic' });
    } else {
        // 禁用麦克风
        VoiceRecorder.cancelRecording();
        VoiceRecorder.destroy();
        sendMessage({ type: 'control', text: 'stop-mic' });
    }
    
    updateMicStatus(AppState.micEnabled);
}

function updateMicStatus(enabled) {
    const micStatus = document.getElementById('mic-status');
    const micText = document.getElementById('mic-text');
    
    if (enabled) {
        micStatus.classList.remove('disabled');
        micText.textContent = '语音监听中...';
    } else {
        micStatus.classList.add('disabled');
        micText.textContent = '麦克风已禁用';
    }
}

// 清空对话
function clearMessages() {
    if (confirm('确定要清空当前对话吗？')) {
        // 保留欢迎消息
        const welcomeMsg = messagesContainer.querySelector('.message.welcome');
        messagesContainer.innerHTML = '';
        if (welcomeMsg) {
            messagesContainer.appendChild(welcomeMsg);
        }
        
        // 通知后端清空历史
        sendMessage({ type: 'create-new-history' });
    }
}

// ==================== 模态窗口管理 ====================

// 历史记录
const historyModal = document.getElementById('history-modal');

function showHistoryModal() {
    historyModal.classList.remove('hidden');
    loadHistoryList();
}

function loadHistoryList() {
    sendMessage({ type: 'fetch-history-list' });
    
    // 模拟历史记录（实际需要从后端获取）
    const historyList = document.getElementById('history-list');
    historyList.innerHTML = '<p style="color: #999; text-align: center;">暂无历史记录</p>';
}

// 设置
const settingsModal = document.getElementById('settings-modal');

function showSettingsModal() {
    settingsModal.classList.remove('hidden');
    
    // 同步显示设置状态
    document.getElementById('auto-scroll-toggle').checked = AppState.autoScroll;
    document.getElementById('markdown-toggle').checked = AppState.markdownEnabled;
    document.getElementById('latex-toggle').checked = AppState.latexEnabled;
    
    // 同步灵犀设置状态
    document.getElementById('tts-engine-select').value = AppState.lingxiSettings.ttsEngine;
    document.getElementById('audio-merge-toggle').checked = AppState.lingxiSettings.audioMergeEnabled;
    document.getElementById('multimodal-auto-switch-toggle').checked = AppState.lingxiSettings.multimodalAutoSwitch;
    
    // 同步语音识别设置
    const vr = AppState.voiceRecording;
    document.getElementById('wake-word-toggle').checked = vr.wakeWordEnabled;
    document.getElementById('wake-word-input').value = vr.wakeWords.join(',');
    document.getElementById('fuzzy-pinyin-toggle').checked = vr.fuzzyPinyinMatch;
    document.getElementById('voice-prompt-toggle').checked = vr.voicePromptInjection;
    
    // 根据唤醒词开关状态显示/隐藏输入框
    updateWakeWordInputVisibility();
}

// 模态窗口关闭
document.querySelectorAll('.close-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        btn.closest('.modal').classList.add('hidden');
    });
});

// 显示设置项变更（本地生效）
document.getElementById('auto-scroll-toggle').addEventListener('change', (e) => {
    AppState.autoScroll = e.target.checked;
});

document.getElementById('markdown-toggle').addEventListener('change', (e) => {
    AppState.markdownEnabled = e.target.checked;
});

document.getElementById('latex-toggle').addEventListener('change', (e) => {
    AppState.latexEnabled = e.target.checked;
});

// 唤醒词开关变化
document.getElementById('wake-word-toggle').addEventListener('change', (e) => {
    updateWakeWordInputVisibility();
});

// 更新唤醒词输入框可见性
function updateWakeWordInputVisibility() {
    const container = document.getElementById('wake-word-input-container');
    const isEnabled = document.getElementById('wake-word-toggle').checked;
    if (container) {
        container.style.display = isEnabled ? 'block' : 'none';
    }
}

// 保存灵犀设置（需要同步到后端）
document.getElementById('save-settings-btn').addEventListener('click', () => {
    // 更新本地状态
    AppState.lingxiSettings.ttsEngine = document.getElementById('tts-engine-select').value;
    AppState.lingxiSettings.audioMergeEnabled = document.getElementById('audio-merge-toggle').checked;
    AppState.lingxiSettings.multimodalAutoSwitch = document.getElementById('multimodal-auto-switch-toggle').checked;
    
    // 更新唤醒词设置
    const vr = AppState.voiceRecording;
    vr.wakeWordEnabled = document.getElementById('wake-word-toggle').checked;
    vr.fuzzyPinyinMatch = document.getElementById('fuzzy-pinyin-toggle').checked;
    vr.voicePromptInjection = document.getElementById('voice-prompt-toggle').checked;
    const wakeWordInput = document.getElementById('wake-word-input').value.trim();
    if (wakeWordInput) {
        vr.wakeWords = wakeWordInput.split(',').map(w => w.trim()).filter(w => w.length > 0);
    }
    
    // 保存唤醒词设置到 localStorage
    localStorage.setItem('wakeWordEnabled', vr.wakeWordEnabled);
    localStorage.setItem('wakeWords', JSON.stringify(vr.wakeWords));
    localStorage.setItem('fuzzyPinyinMatch', vr.fuzzyPinyinMatch);
    localStorage.setItem('voicePromptInjection', vr.voicePromptInjection);
    
    // 发送到后端保存
    sendMessage({
        type: 'update-lingxi-settings',
        settings: {
            tts_engine: AppState.lingxiSettings.ttsEngine,
            audio_merge_enabled: AppState.lingxiSettings.audioMergeEnabled,
            multimodal_auto_switch: AppState.lingxiSettings.multimodalAutoSwitch
        }
    });
    
    // 显示保存成功提示
    const wakeStatus = vr.wakeWordEnabled ? `唤醒词: ${vr.wakeWords.join('/')}` : '直接对话模式';
    showToast(`✅ 设置已保存 (${wakeStatus})`);
    
    // 关闭设置窗口
    settingsModal.classList.add('hidden');
});

// Toast 提示
function showToast(message, duration = 2000) {
    const toast = document.createElement('div');
    toast.className = 'toast-message';
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 10px 20px;
        border-radius: 20px;
        font-size: 14px;
        z-index: 10000;
        animation: fadeInOut ${duration}ms ease-in-out;
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
}

// 点击模态背景关闭
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });
});

// ==================== 文件上传 ====================
const fileInput = document.getElementById('file-input');
const dropIndicator = document.getElementById('drop-indicator');
const attachmentsPreview = document.getElementById('attachments-preview');
const attachmentsList = document.getElementById('attachments-list');
const clearAttachmentsBtn = document.getElementById('clear-attachments-btn');

function triggerFileUpload() {
    fileInput.click();
}

fileInput.addEventListener('change', (e) => {
    handleFiles(e.target.files);
    fileInput.value = ''; // 清空，允许重复上传同一文件
});

// 拖拽上传
live2dSection.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropIndicator.classList.remove('hidden');
});

live2dSection.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dropIndicator.classList.add('hidden');
});

live2dSection.addEventListener('drop', (e) => {
    e.preventDefault();
    dropIndicator.classList.add('hidden');
    handleFiles(e.dataTransfer.files);
});

// 处理上传的文件（图片和PDF）
function handleFiles(files) {
    for (let file of files) {
        if (file.type.startsWith('image/')) {
            // 处理图片
            const reader = new FileReader();
            reader.onload = (e) => {
                addAttachment({
                    type: 'image',
                    name: file.name,
                    data: e.target.result,
                    mimeType: file.type
                });
            };
            reader.readAsDataURL(file);
        } else if (file.type === 'application/pdf') {
            // 处理 PDF - 转换为图片发送给后端
            handlePdfFile(file);
        }
    }
}

// 处理 PDF 文件（转换为图片）
async function handlePdfFile(file) {
    const reader = new FileReader();
    reader.onload = async (e) => {
        const pdfData = e.target.result;
        
        // 检查是否有 PDF.js 库
        if (typeof pdfjsLib !== 'undefined') {
            // 使用 PDF.js 渲染 PDF 为图片
            try {
                const pdf = await pdfjsLib.getDocument({ data: pdfData }).promise;
                const numPages = Math.min(pdf.numPages, 10); // 限制最多10页
                
                for (let i = 1; i <= numPages; i++) {
                    const page = await pdf.getPage(i);
                    const scale = 2;
                    const viewport = page.getViewport({ scale });
                    
                    const canvas = document.createElement('canvas');
                    canvas.width = viewport.width;
                    canvas.height = viewport.height;
                    const ctx = canvas.getContext('2d');
                    
                    await page.render({ canvasContext: ctx, viewport }).promise;
                    
                    const imageData = canvas.toDataURL('image/png');
                    addAttachment({
                        type: 'pdf',
                        name: `${file.name} (第${i}页)`,
                        data: imageData,
                        mimeType: 'image/png'
                    });
                }
            } catch (error) {
                console.error('❌ PDF 解析失败:', error);
                addMessage('assistant', '❌ PDF 解析失败，请尝试上传图片格式的文件');
            }
        } else {
            // 没有 PDF.js，直接将 PDF 作为 base64 发送（后端可能不支持）
            addAttachment({
                type: 'pdf',
                name: file.name,
                data: pdfData,
                mimeType: 'application/pdf'
            });
            console.warn('⚠️ PDF.js 未加载，PDF 将以原始格式发送');
        }
    };
    reader.readAsArrayBuffer(file);
}

// 添加附件到待发送列表
function addAttachment(attachment) {
    // 检查是否已存在相同文件
    const exists = AppState.pendingAttachments.some(a => a.name === attachment.name && a.data === attachment.data);
    if (exists) {
        console.warn('⚠️ 文件已存在:', attachment.name);
        return;
    }
    
    AppState.pendingAttachments.push(attachment);
    updateAttachmentsPreview();
    
    // 显示输入区域，让用户输入问题
    inputArea.classList.remove('hidden');
    textInput.focus();
    textInput.placeholder = '请针对上传的文件提问...';
    
    console.log(`📎 添加附件: ${attachment.name}, 总数: ${AppState.pendingAttachments.length}`);
}

// 更新附件预览UI
function updateAttachmentsPreview() {
    if (AppState.pendingAttachments.length === 0) {
        attachmentsPreview.classList.add('hidden');
        attachmentsList.innerHTML = '';
        return;
    }
    
    attachmentsPreview.classList.remove('hidden');
    attachmentsList.innerHTML = '';
    
    AppState.pendingAttachments.forEach((att, index) => {
        const item = document.createElement('div');
        item.className = `attachment-item ${att.type}`;
        
        if (att.type === 'image') {
            item.innerHTML = `
                <img class="attachment-thumb" src="${att.data}" alt="${att.name}">
                <span class="attachment-name" title="${att.name}">${truncateName(att.name, 12)}</span>
                <button class="attachment-remove" data-index="${index}">×</button>
            `;
        } else {
            item.innerHTML = `
                <span class="attachment-icon">📄</span>
                <span class="attachment-name" title="${att.name}">${truncateName(att.name, 12)}</span>
                <button class="attachment-remove" data-index="${index}">×</button>
            `;
        }
        
        attachmentsList.appendChild(item);
    });
    
    // 绑定删除按钮事件
    attachmentsList.querySelectorAll('.attachment-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const index = parseInt(e.target.dataset.index);
            removeAttachment(index);
        });
    });
}

// 移除单个附件
function removeAttachment(index) {
    AppState.pendingAttachments.splice(index, 1);
    updateAttachmentsPreview();
    
    if (AppState.pendingAttachments.length === 0) {
        textInput.placeholder = '输入问题... (Ctrl+/ 唤起)';
    }
}

// 清除所有附件
function clearAllAttachments() {
    AppState.pendingAttachments = [];
    updateAttachmentsPreview();
    textInput.placeholder = '输入问题... (Ctrl+/ 唤起)';
}

// 清除附件按钮
clearAttachmentsBtn.addEventListener('click', clearAllAttachments);

// 截断文件名
function truncateName(name, maxLen) {
    if (name.length <= maxLen) return name;
    const ext = name.split('.').pop();
    const base = name.substring(0, name.lastIndexOf('.'));
    const truncated = base.substring(0, maxLen - ext.length - 3) + '...';
    return truncated + '.' + ext;
}

// ==================== Live2D 初始化 ====================
let live2dApp = null;
let live2dModel = null;

async function initLive2D() {
    try {
        console.log('🎨 开始初始化 Live2D (PIXI SDK)...');
        
        // 检查 PIXI 是否加载
        if (typeof PIXI === 'undefined') {
            console.error('❌ PIXI.js 未加载');
            showLive2DFallback('缺少 PIXI.js 库');
            return;
        }
        
        // 检查 Live2D SDK
        console.log('🔍 检查 Live2D SDK...');
        console.log('  - window.Live2D:', typeof window.Live2D);
        console.log('  - window.Live2DCubismCore:', typeof window.Live2DCubismCore);
        console.log('  - PIXI.live2d:', typeof PIXI.live2d);
        
        // pixi-live2d-display 在全局暴露为 PIXI.live2d
        if (typeof PIXI.live2d === 'undefined') {
            console.error('❌ pixi-live2d-display 未正确加载');
            console.error('请确保 live2d.min.js 和 live2dcubismcore.min.js 在 pixi-live2d-display.min.js 之前加载');
            showLive2DFallback('Live2D SDK 加载失败');
            return;
        }
        
        // 显示canvas（确保不使用iframe）
        live2dCanvas.style.display = 'block';
        console.log('✅ Canvas 已显示');
        
        // 创建 PIXI 应用
        live2dApp = new PIXI.Application({
            view: live2dCanvas,
            width: 300,
            height: 600,
            backgroundAlpha: 0,
            antialias: true,
            resolution: window.devicePixelRatio || 1,
            autoDensity: true
        });
        
        // 保存到全局状态
        AppState.live2dApp = live2dApp;
        
        console.log('✅ PIXI 应用创建完成，等待模型配置...');
        
        // 如果已经有模型配置（可能 WebSocket 消息先到达），立即加载
        if (AppState.modelConfig.url) {
            await loadLive2DModel();
        }
        
    } catch (error) {
        console.error('❌ Live2D 初始化失败:', error);
        showLive2DFallback('初始化失败: ' + error.message);
    }
}

// 加载 Live2D 模型（从配置动态加载）
async function loadLive2DModel() {
    try {
        if (!live2dApp) {
            console.warn('⚠️ PIXI 应用未创建，无法加载模型');
            return;
        }
        
        if (!AppState.modelConfig.url) {
            console.warn('⚠️ 模型 URL 未配置，无法加载模型');
            return;
        }
        
        if (AppState.modelConfig.loaded) {
            console.log('ℹ️ 模型已加载，跳过');
            return;
        }
        
        // 构建完整的模型 URL
        const baseUrl = 'http://127.0.0.1:12393';
        const modelUrl = baseUrl + AppState.modelConfig.url;
        console.log('📦 加载模型:', modelUrl);
        
        // 使用 Live2DModel.from 加载模型
        const Live2DModel = PIXI.live2d.Live2DModel;
        if (!Live2DModel) {
            throw new Error('Live2DModel 类未找到');
        }
        
        live2dModel = await Live2DModel.from(modelUrl, {
            autoInteract: false
        });
        
        console.log('✅ 模型加载完成');
        
        // 保存到全局状态
        AppState.live2dModel = live2dModel;
        AppState.modelConfig.loaded = true;
        
        // 设置模型大小和位置
        const canvasHeight = live2dApp.screen.height;
        const canvasWidth = live2dApp.screen.width;
        const modelHeight = live2dModel.height;
        const modelWidth = live2dModel.width;
        
        // 计算缩放比例，让模型高度占画布的 90%
        const scale = (canvasHeight * 0.9) / modelHeight;
        
        live2dModel.scale.set(scale);
        live2dModel.anchor.set(0.5, 0.5);  // 中心点定位
        live2dModel.position.set(
            canvasWidth / 2,
            canvasHeight / 2  // 居中显示
        );
        
        // 添加到舞台
        live2dApp.stage.addChild(live2dModel);
        
        // 启用交互
        live2dModel.interactive = true;
        live2dModel.buttonMode = true;
        
        // 点击事件
        live2dModel.on('pointerdown', (e) => {
            console.log('👆 点击 Live2D 模型');
            sendMessage({ type: 'interrupt-signal' });
            stopAllAudio();
        });
        
        console.log('✅ Live2D 模型加载完成');
        console.log('🎭 模型信息:', {
            name: AppState.modelConfig.name,
            width: live2dModel.width,
            height: live2dModel.height,
            scale: scale
        });
        
    } catch (error) {
        console.error('❌ Live2D 模型加载失败:', error);
        showLive2DFallback('模型加载失败: ' + error.message);
    }
}

// 显示备用占位符
function showLive2DFallback(reason) {
    const placeholder = document.createElement('div');
    placeholder.style.cssText = `
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        text-align: center;
        color: rgba(255, 255, 255, 0.6);
        font-size: 14px;
    `;
    placeholder.innerHTML = `
        <div style="font-size: 48px; margin-bottom: 10px;">🎭</div>
        <div>Live2D 角色</div>
        <div style="font-size: 12px; margin-top: 5px; opacity: 0.6;">灵犀助教</div>
        <div style="font-size: 10px; margin-top: 10px; opacity: 0.4;">加载失败</div>
    `;
    live2dSection.appendChild(placeholder);
}

// ==================== 应用初始化 ====================
window.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 灵犀助教 - 桌宠模式启动');
    
    // 加载唤醒词设置
    loadWakeWordSettings();
    
    // 初始化 Live2D
    initLive2D();
    
    // 连接 WebSocket
    connectWebSocket();
    
    // 初始化麦克风录音
    if (AppState.micEnabled) {
        VoiceRecorder.init().then(success => {
            if (success) {
                // 初始化按键录音
                PushToTalk.init();
            }
        });
    }
    
    // 显示输入框（首次启动）
    setTimeout(() => {
        inputArea.classList.remove('hidden');
    }, 500);
    
    console.log('✅ 桌宠模式初始化完成');
    console.log('💡 快捷键: Ctrl+/ 唤起输入框, 空格键按住录音, 右键点击人物打开菜单');
});

// ==================== 错误处理 ====================
window.addEventListener('error', (e) => {
    console.error('💥 全局错误:', e.error);
});

window.addEventListener('unhandledrejection', (e) => {
    console.error('💥 未处理的 Promise 错误:', e.reason);
});
