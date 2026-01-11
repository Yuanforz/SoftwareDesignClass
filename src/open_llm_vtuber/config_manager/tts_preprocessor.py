# config_manager/translate.py
from typing import Literal, Optional, Dict, ClassVar
from pydantic import ValidationInfo, Field, model_validator
from .i18n import I18nMixin, Description

class TTSPreprocessorConfig(I18nMixin):
    """Configuration for TTS preprocessor."""

    remove_special_char: bool = Field(..., alias="remove_special_char")
    ignore_brackets: bool = Field(default=True, alias="ignore_brackets")
    ignore_parentheses: bool = Field(default=True, alias="ignore_parentheses")
    ignore_asterisks: bool = Field(default=True, alias="ignore_asterisks")
    ignore_angle_brackets: bool = Field(default=True, alias="ignore_angle_brackets")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "remove_special_char": Description(
            en="Remove special characters from the input text",
            zh="从输入文本中删除特殊字符",
        ),
        "ignore_brackets": Description(
            en="Ignore text within brackets () during preprocessing",
            zh="在预处理过程中忽略括号 () 内的文本",
        ),
        "ignore_parentheses": Description(
            en="Ignore text within parentheses [] during preprocessing",
            zh="在预处理过程中忽略方括号 [] 内的文本",
        ),
        "ignore_asterisks": Description(
            en="Ignore text within asterisks ** during preprocessing",
            zh="在预处理过程中忽略星号 ** 内的文本",
        ),
        "ignore_angle_brackets": Description(
            en="Ignore text within angle brackets <> during preprocessing",
            zh="在预处理过程中忽略尖括号 <> 内的文本",
        ),
    }
