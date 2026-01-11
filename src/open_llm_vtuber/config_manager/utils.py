# config_manager/utils.py
import yaml
from pathlib import Path
from typing import Union, Dict, Any, TypeVar
from pydantic import BaseModel, ValidationError
import os
import re
import chardet
from loguru import logger

from .main import Config

T = TypeVar("T", bound=BaseModel)


def read_yaml(config_path: str) -> Dict[str, Any]:
    """
    Read the specified YAML configuration file with environment variable substitution
    and guess encoding. Return the configuration data as a dictionary.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Configuration data as a dictionary.

    Raises:
        FileNotFoundError: If the configuration file is not found.
        IOError: If the configuration file cannot be read.
    """

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    content = load_text_file_with_guess_encoding(config_path)
    if not content:
        raise IOError(f"Failed to read configuration file: {config_path}")

    # Replace environment variables
    pattern = re.compile(r"\$\{(\w+)\}")

    def replacer(match):
        env_var = match.group(1)
        return os.getenv(env_var, match.group(0))

    content = pattern.sub(replacer, content)

    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as e:
        logger.critical(f"Error parsing YAML file: {e}")
        raise e


def validate_config(config_data: dict) -> Config:
    """
    Validate configuration data against the Config model.

    Args:
        config_data: Configuration data to validate.

    Returns:
        Validated Config object.

    Raises:
        ValidationError: If the configuration fails validation.
    """
    try:
        return Config(**config_data)
    except ValidationError as e:
        logger.critical(f"Error validating configuration: {e}")
        logger.error("Configuration data:")
        logger.error(config_data)
        raise e


def load_text_file_with_guess_encoding(file_path: str) -> str | None:
    """
    Load a text file with guessed encoding.

    Parameters:
    - file_path (str): The path to the text file.

    Returns:
    - str: The content of the text file or None if an error occurred.
    """
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "ascii", "cp936"]

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue
    # If common encodings fail, try chardet to guess the encoding
    try:
        with open(file_path, "rb") as file:
            raw_data = file.read()
        detected = chardet.detect(raw_data)
        if detected["encoding"]:
            return raw_data.decode(detected["encoding"])
    except Exception as e:
        logger.error(f"Error detecting encoding for config file {file_path}: {e}")
    return None


def save_config(config: BaseModel, config_path: Union[str, Path]):
    """
    Saves a Pydantic model to a YAML configuration file.

    Args:
        config: The Pydantic model to save.
        config_path: Path to the YAML configuration file.
    """
    config_file = Path(config_path)
    config_data = config.model_dump(
        by_alias=True, exclude_unset=True, exclude_none=True
    )

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error writing YAML file: {e}")


def scan_config_alts_directory(config_alts_dir: str) -> list[dict]:
    """
    Scan the config_alts directory and return a list of config information.
    Each config info contains the filename and its display name from the config.

    Parameters:
    - config_alts_dir (str): The path to the config_alts directory.

    Returns:
    - list[dict]: A list of dicts containing config info:
        - filename: The actual config file name
        - name: Display name from config, falls back to filename if not specified
    """
    config_files = []

    # Add default config first
    default_config = read_yaml("conf.yaml")
    config_files.append(
        {
            "filename": "conf.yaml",
            "name": default_config.get("character_config", {}).get(
                "conf_name", "conf.yaml"
            )
            if default_config
            else "conf.yaml",
        }
    )

    # Scan other configs
    for root, _, files in os.walk(config_alts_dir):
        for file in files:
            if file.endswith(".yaml"):
                config: dict = read_yaml(os.path.join(root, file))
                config_files.append(
                    {
                        "filename": file,
                        "name": config.get("character_config", {}).get(
                            "conf_name", file
                        )
                        if config
                        else file,
                    }
                )
    logger.debug(f"Found config files: {config_files}")
    return config_files


def scan_bg_directory() -> list[str]:
    bg_files = []
    bg_dir = "backgrounds"
    for root, _, files in os.walk(bg_dir):
        for file in files:
            if file.endswith((".jpg", ".jpeg", ".png", ".gif")):
                bg_files.append(file)
    return bg_files


def update_lingxi_settings(settings: Dict[str, Any], config_path: str = "conf.yaml") -> bool:
    """
    更新 conf.yaml 中的 lingxi_settings 配置。
    
    Args:
        settings: 要更新的设置字典，包含以下键：
            - tts_engine: 'step_tts' 或 'edge_tts'
            - audio_merge_enabled: bool
            - multimodal_auto_switch: bool
        config_path: 配置文件路径
    
    Returns:
        bool: 更新是否成功
    """
    try:
        # 读取当前配置
        content = load_text_file_with_guess_encoding(config_path)
        if not content:
            logger.error(f"无法读取配置文件: {config_path}")
            return False
        
        config_data = yaml.safe_load(content)
        if not config_data:
            logger.error(f"配置文件为空: {config_path}")
            return False
        
        # 确保 lingxi_settings 存在
        if "lingxi_settings" not in config_data:
            config_data["lingxi_settings"] = {}
        
        # 更新设置
        lingxi_settings = config_data["lingxi_settings"]
        if "tts_engine" in settings:
            lingxi_settings["tts_engine"] = settings["tts_engine"]
        if "audio_merge_enabled" in settings:
            lingxi_settings["audio_merge_enabled"] = settings["audio_merge_enabled"]
        if "multimodal_auto_switch" in settings:
            lingxi_settings["multimodal_auto_switch"] = settings["multimodal_auto_switch"]
        
        # 同时更新 tts_config.tts_model 以保持同步
        if "tts_engine" in settings:
            if "character_config" in config_data and "tts_config" in config_data["character_config"]:
                config_data["character_config"]["tts_config"]["tts_model"] = settings["tts_engine"]
        
        # 保存配置
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        logger.info(f"灵犀设置已更新: {settings}")
        return True
        
    except Exception as e:
        logger.error(f"更新灵犀设置失败: {e}")
        return False


def get_lingxi_settings(config_path: str = "conf.yaml") -> Dict[str, Any]:
    """
    获取 conf.yaml 中的 lingxi_settings 配置。
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        dict: lingxi_settings 配置，如果不存在则返回默认值
    """
    default_settings = {
        "tts_engine": "step_tts",
        "audio_merge_enabled": False,
        "audio_merge_max_sentences": 3,
        "progressive_merge_enabled": True,  # 渐进式合并：首句立即响应，缓冲逐渐增加
        "multimodal_auto_switch": True,
        "multimodal_base_model": "step-2-16k",
        "multimodal_vision_model": "step-1o-turbo-vision"
    }
    
    try:
        config_data = read_yaml(config_path)
        if config_data and "lingxi_settings" in config_data:
            # 合并默认设置和用户设置
            return {**default_settings, **config_data["lingxi_settings"]}
        return default_settings
    except Exception as e:
        logger.error(f"读取灵犀设置失败: {e}")
        return default_settings
