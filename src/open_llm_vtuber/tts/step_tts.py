# src/open_llm_vtuber/tts/step_tts.py
"""
Step TTS Engine - 阶跃星辰语音合成
API 文档: https://api.stepfun.com/v1/audio/speech

支持的模型:
    - step-tts-2: 高质量模型
    - step-tts-mini: 快速模型

支持的音色:
    - elegantgentle-female: 气质温婉（女声）
    - cixingnansheng: 磁性男声
    - 更多音色请参考官方文档

支持的输出格式: wav, mp3, flac, opus, pcm (默认 mp3)
支持的语言: 中文、英文、中英混合、日语
"""

import os
import sys
import requests
from pathlib import Path
from typing import Optional
from loguru import logger

from .tts_interface import TTSInterface

# Add the current directory to sys.path for relative imports if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)


class TTSEngine(TTSInterface):
    """
    阶跃星辰 TTS 引擎
    
    使用阶跃星辰的 API 生成高质量语音。
    特别适合教培场景，能够把握教师在不同情绪下的声音特点。
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "step-tts-mini",
        voice: str = "elegantgentle-female",
        base_url: str = "https://api.stepfun.com/v1/audio/speech",
        response_format: str = "mp3",
        speed: float = 1.0,
        volume: float = 1.0,
        **kwargs,
    ):
        """
        初始化阶跃星辰 TTS 引擎。

        Args:
            api_key (str): 阶跃星辰 API 密钥
            model (str): TTS 模型，可选 'step-tts-2' 或 'step-tts-mini'
            voice (str): 语音音色，如 'elegantgentle-female', 'cixingnansheng'
            base_url (str): API 端点 URL
            response_format (str): 输出音频格式，支持 wav, mp3, flac, opus, pcm
            speed (float): 语速，范围 0.5-2.0，1.0 为正常速度
            volume (float): 音量，范围 0.1-2.0，1.0 为正常音量
        """
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.base_url = base_url
        self.speed = max(0.5, min(2.0, speed))  # 限制在 0.5-2.0 范围内
        self.volume = max(0.1, min(2.0, volume))  # 限制在 0.1-2.0 范围内
        
        # 验证和设置输出格式
        self.response_format = response_format.lower()
        if self.response_format not in ["wav", "mp3", "flac", "opus", "pcm"]:
            logger.warning(
                f"不支持的音频格式 '{self.response_format}'，使用默认格式 'mp3'"
            )
            self.response_format = "mp3"
        
        self.file_extension = self.response_format
        self.new_audio_dir = "cache"
        self.temp_audio_file = "temp_step_tts"

        if not os.path.exists(self.new_audio_dir):
            os.makedirs(self.new_audio_dir)

        if not self.api_key:
            logger.warning("Step TTS: API 密钥未配置，请在 conf.yaml 中设置 api_key")
        
        logger.info(
            f"Step TTS 引擎已初始化: 模型={self.model}, 音色={self.voice}, "
            f"语速={self.speed}, 音量={self.volume}, 格式={self.response_format}"
        )

    def generate_audio(self, text: str, file_name_no_ext: Optional[str] = None) -> Optional[str]:
        """
        使用阶跃星辰 TTS 生成语音文件。

        Args:
            text (str): 要合成的文本
            file_name_no_ext (str, optional): 文件名（不含扩展名）

        Returns:
            str: 生成的音频文件路径，失败时返回 None
        """
        if not self.api_key:
            logger.error("Step TTS: API 密钥未配置，无法生成音频")
            return None

        if not text or not text.strip():
            logger.warning("Step TTS: 文本为空，跳过生成")
            return None

        # 生成文件路径
        file_name = self.generate_cache_file_name(file_name_no_ext, self.file_extension)
        speech_file_path = Path(file_name)

        try:
            logger.debug(
                f"Step TTS 生成音频: 文本='{text[:50]}...', 音色='{self.voice}', 模型='{self.model}'"
            )

            # 构建请求
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            payload: dict = {
                "model": self.model,
                "input": text,
                "voice": self.voice,
            }

            # 添加可选参数
            if self.speed != 1.0:
                payload["speed"] = self.speed
            if self.volume != 1.0:
                payload["volume"] = self.volume
            if self.response_format != "mp3":
                payload["response_format"] = self.response_format

            # 发送请求
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=60,  # 60秒超时
            )

            if response.status_code == 200:
                # 保存音频文件
                with open(speech_file_path, "wb") as f:
                    f.write(response.content)
                
                logger.info(f"Step TTS 音频已生成: {speech_file_path}")
                return str(speech_file_path)
            else:
                error_msg = response.text
                try:
                    error_json = response.json()
                    error_msg = error_json.get("error", {}).get("message", response.text)
                except:
                    pass
                logger.error(
                    f"Step TTS API 错误: 状态码={response.status_code}, 错误={error_msg}"
                )
                return None

        except requests.exceptions.Timeout:
            logger.error("Step TTS: 请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Step TTS 请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"Step TTS 生成音频时发生错误: {e}")
            return None


# 测试代码
if __name__ == "__main__":
    # 测试用法
    tts = TTSEngine(
        api_key="your-api-key-here",
        model="step-tts-mini",
        voice="elegantgentle-female",
    )
    result = tts.generate_audio("你好，欢迎使用阶跃星辰语音合成服务。")
    if result:
        print(f"音频已生成: {result}")
    else:
        print("音频生成失败")
