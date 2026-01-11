import re
import unicodedata
import random
from loguru import logger
from ..translate.translate_interface import TranslateInterface


def tts_filter(
    text: str,
    remove_special_char: bool,
    ignore_brackets: bool,
    ignore_parentheses: bool,
    ignore_asterisks: bool,
    ignore_angle_brackets: bool,
    translator: TranslateInterface | None = None,
) -> str:
    """
    Filter or do anything to the text before TTS generates the audio.
    Changes here do not affect subtitles or LLM's memory. The generated audio is
    the only affected thing.

    双流输出设计：
    - 显示文本 (display_text): 保留完整的 Markdown/LaTeX 格式用于渲染
    - TTS 文本 (tts_text): 此函数生成口语化版本用于语音合成

    Args:
        text (str): The text to filter.
        remove_special_char (bool): Whether to remove special characters.
        ignore_brackets (bool): Whether to ignore text within brackets.
        ignore_parentheses (bool): Whether to ignore text within parentheses.
        ignore_asterisks (bool): Whether to ignore text within asterisks.
        translator (TranslateInterface, optional):
            The translator to use. If None, we'll skip the translation. Defaults to None.

    Returns:
        str: The filtered text for TTS (口语化版本).
    """
    # 0. 检查是否是Markdown标题行（#开头），如果是则提取标题内容
    if is_markdown_heading(text):
        # 提取标题内容进行朗读，而不是完全跳过
        title_text = extract_heading_content(text)
        if title_text:
            text = title_text
            logger.debug(f"Extracted heading content for TTS: {text}")
        else:
            logger.debug(f"Filtered out empty markdown heading: {text}")
            return ""
    
    # 1. 处理LaTeX公式（优先，在其他过滤前）
    try:
        text = filter_latex_formulas(text)
    except Exception as e:
        logger.warning(f"Error filtering LaTeX formulas: {e}")
        logger.warning(f"Text: {text}")
    
    # 2. 处理Markdown符号
    try:
        text = filter_markdown_symbols(text)
    except Exception as e:
        logger.warning(f"Error filtering Markdown symbols: {e}")
        logger.warning(f"Text: {text}")
    
    if ignore_asterisks:
        try:
            text = filter_asterisks(text)
        except Exception as e:
            logger.warning(f"Error ignoring asterisks: {e}")
            logger.warning(f"Text: {text}")
            logger.warning("Skipping...")

    if ignore_brackets:
        try:
            text = filter_brackets(text)
        except Exception as e:
            logger.warning(f"Error ignoring brackets: {e}")
            logger.warning(f"Text: {text}")
            logger.warning("Skipping...")
    if ignore_parentheses:
        try:
            text = filter_parentheses(text)
        except Exception as e:
            logger.warning(f"Error ignoring parentheses: {e}")
            logger.warning(f"Text: {text}")
            logger.warning("Skipping...")
    if ignore_angle_brackets:
        try:
            text = filter_angle_brackets(text)
        except Exception as e:
            logger.warning(f"Error ignoring angle brackets: {e}")
            logger.warning(f"Text: {text}")
            logger.warning("Skipping...")
    if remove_special_char:
        try:
            text = remove_special_characters(text)
        except Exception as e:
            logger.warning(f"Error removing special characters: {e}")
            logger.warning(f"Text: {text}")
            logger.warning("Skipping...")
    
    # 3. 移除句尾标点（TTS 不需要朗读）
    text = remove_trailing_sentence_punctuation(text)
    
    if translator:
        try:
            logger.info("Translating...")
            text = translator.translate(text)
            logger.info(f"Translated: {text}")
        except Exception as e:
            logger.critical(f"Error translating: {e}")
            logger.critical(f"Text: {text}")
            logger.warning("Skipping...")

    logger.debug(f"Filtered text for TTS: {text}")
    return text


def remove_trailing_sentence_punctuation(text: str) -> str:
    """
    移除句尾的标点符号，因为 TTS 不需要朗读句号、逗号等。
    
    Args:
        text (str): 待处理的文本
    
    Returns:
        str: 移除句尾标点后的文本
    """
    if not text:
        return text
    
    text = text.strip()
    # 定义需要移除的句尾标点
    trailing_puncts = ['。', '，', '、', '；', '：', '.', ',', ';', ':', '！', '？', '!', '?']
    
    # 循环移除，处理多个连续标点的情况
    while text and text[-1] in trailing_puncts:
        text = text[:-1]
    
    return text.strip()


def extract_heading_content(text: str) -> str:
    """
    从 Markdown 标题行提取实际内容。
    
    Args:
        text (str): 可能包含 # 符号的标题行
    
    Returns:
        str: 标题的实际内容（不含 # 符号）
    """
    text = text.strip()
    # 移除开头的 # 符号
    match = re.match(r'^#+\s*(.+)$', text)
    if match:
        return match.group(1).strip()
    return text


def remove_special_characters(text: str) -> str:
    """
    Filter text to remove all non-letter, non-number, and non-punctuation characters.

    Args:
        text (str): The text to filter.

    Returns:
        str: The filtered text.
    """
    normalized_text = unicodedata.normalize("NFKC", text)

    def is_valid_char(char: str) -> bool:
        category = unicodedata.category(char)
        return (
            category.startswith("L")
            or category.startswith("N")
            or category.startswith("P")
            or char.isspace()
        )

    filtered_text = "".join(char for char in normalized_text if is_valid_char(char))
    return filtered_text


def _filter_nested(text: str, left: str, right: str) -> str:
    """
    Generic function to handle nested symbols.

    Args:
        text (str): The text to filter.
        left (str): The left symbol (e.g. '[' or '(').
        right (str): The right symbol (e.g. ']' or ')').

    Returns:
        str: The filtered text.
    """
    if not isinstance(text, str):
        raise TypeError("Input must be a string")
    if not text:
        return text

    result = []
    depth = 0
    for char in text:
        if char == left:
            depth += 1
        elif char == right:
            if depth > 0:
                depth -= 1
        else:
            if depth == 0:
                result.append(char)
    filtered_text = "".join(result)
    filtered_text = re.sub(r"\s+", " ", filtered_text).strip()
    return filtered_text


def filter_brackets(text: str) -> str:
    """
    Filter text to remove all text within brackets, handling nested cases.

    Args:
        text (str): The text to filter.

    Returns:
        str: The filtered text.
    """
    return _filter_nested(text, "[", "]")


def filter_parentheses(text: str) -> str:
    """
    Filter text to remove all text within parentheses, handling nested cases.

    Args:
        text (str): The text to filter.

    Returns:
        str: The filtered text.
    """
    return _filter_nested(text, "(", ")")


def filter_angle_brackets(text: str) -> str:
    """
    Filter text to remove all text within angle brackets, handling nested cases.

    Args:
        text (str): The text to filter.

    Returns:
        str: The filtered text.
    """
    return _filter_nested(text, "<", ">")


def filter_latex_formulas(text: str) -> str:
    """
    将LaTeX公式替换为口语化的表达。
    - 短小公式（如 $x$, $Q$, $\epsilon_0$）-> 提取变量名直接朗读
    - 较长公式 -> 随机选择："这个公式"、"这个式子"等
    - $$...$$（块级公式）-> 随机选择："这个公式"、"这个式子"
    
    Args:
        text (str): 包含LaTeX公式的文本
    
    Returns:
        str: 处理后的文本
    """
    # 公式替代词列表
    formula_replacements = ["这个公式", "这个式子", "这个表达式"]
    
    def process_inline_formula(match):
        """处理行内公式"""
        content = match.group(1)
        
        # 尝试提取简单变量名
        simple_var = extract_simple_variable(content)
        if simple_var:
            return simple_var
        
        # 较长公式用替代词
        return random.choice(formula_replacements)
    
    def process_block_formula(match):
        """处理块级公式"""
        return random.choice(formula_replacements)
    
    # 替换块级公式 $$...$$
    text = re.sub(r'\$\$([^\$]+)\$\$', process_block_formula, text)
    
    # 替换行内公式 $...$
    text = re.sub(r'\$([^\$\n]+)\$', process_inline_formula, text)
    
    return text


def extract_simple_variable(latex: str) -> str:
    """
    从简单的LaTeX公式中提取可朗读的变量名。
    
    Args:
        latex: LaTeX公式内容（不含$符号）
    
    Returns:
        可朗读的变量名，如果无法提取则返回None
    """
    latex = latex.strip()
    
    # 希腊字母映射
    greek_letters = {
        r'\\alpha': 'α', r'\\beta': 'β', r'\\gamma': 'γ', r'\\delta': 'δ',
        r'\\epsilon': 'ε', r'\\varepsilon': 'ε', r'\\zeta': 'ζ', r'\\eta': 'η',
        r'\\theta': 'θ', r'\\iota': 'ι', r'\\kappa': 'κ', r'\\lambda': 'λ',
        r'\\mu': 'μ', r'\\nu': 'ν', r'\\xi': 'ξ', r'\\pi': 'π',
        r'\\rho': 'ρ', r'\\sigma': 'σ', r'\\tau': 'τ', r'\\phi': 'φ',
        r'\\chi': 'χ', r'\\psi': 'ψ', r'\\omega': 'ω',
        r'\\Phi': 'Φ', r'\\Psi': 'Ψ', r'\\Omega': 'Ω',
        r'\\Delta': 'Δ', r'\\Gamma': 'Γ', r'\\Theta': 'Θ', r'\\Lambda': 'Λ',
        r'\\Xi': 'Ξ', r'\\Pi': 'Π', r'\\Sigma': 'Σ',
    }
    
    # 替换希腊字母
    for cmd, symbol in greek_letters.items():
        latex = re.sub(cmd + r'(?![a-zA-Z])', symbol, latex)
    
    # 移除 \text{...} 包装，保留内容
    latex = re.sub(r'\\text\{([^}]+)\}', r'\1', latex)
    
    # 移除下标 _{...} 但保留简单下标内容
    # 例如 Q_{enc} -> Q_enc, x_0 -> x0
    latex = re.sub(r'_\{([^}]+)\}', r'下标\1', latex)
    latex = re.sub(r'_([a-zA-Z0-9])', r'下标\1', latex)
    
    # 移除上标 ^{...}
    latex = re.sub(r'\^\{([^}]+)\}', '', latex)
    latex = re.sub(r'\^([a-zA-Z0-9])', '', latex)
    
    # 移除其他LaTeX命令
    latex = re.sub(r'\\[a-zA-Z]+', '', latex)
    
    # 移除特殊字符，只保留字母数字和基本符号
    latex = re.sub(r'[{}\\,;:\s]+', '', latex)
    
    # 清理"下标"前后的空格
    latex = latex.strip()
    
    # 如果结果太长（超过15个字符），返回None表示应使用替代词
    if len(latex) > 15:
        return None
    
    # 如果结果为空或只有特殊符号，返回None
    if not latex or not re.search(r'[a-zA-Z0-9α-ωΑ-Ω]', latex):
        return None
    
    return latex


def is_markdown_heading(text: str) -> bool:
    """
    检查文本是否是Markdown标题行（以#开头）
    
    Args:
        text (str): 要检查的文本
    
    Returns:
        bool: 如果是标题行返回True
    """
    text = text.strip()
    # 检查是否以 # 开头（标题）
    if re.match(r'^#+\s+', text):
        return True
    return False


def filter_markdown_symbols(text: str) -> str:
    """
    移除Markdown格式符号，保留实际内容。
    - # ## ### 标题符号 -> 移除#，保留内容
    - **粗体** -> 移除**，保留内容
    - *斜体* -> 移除*，保留内容
    - __下划线__ -> 移除__，保留内容
    - `代码` -> 移除`，保留内容
    - [链接](url) -> 保留"链接"
    - - 列表 -> 移除-，保留内容
    
    Args:
        text (str): 包含Markdown的文本
    
    Returns:
        str: 处理后的文本
    """
    # 移除标题符号 (# ## ###等)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    
    # 移除粗体 **text** 或 __text__
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    
    # 移除斜体 *text* 或 _text_ (需要注意不要误删星号列表)
    text = re.sub(r'(?<!\*)\*(?!\*)([^\*]+)\*(?!\*)', r'\1', text)
    text = re.sub(r'(?<!_)_(?!_)([^_]+)_(?!_)', r'\1', text)
    
    # 移除行内代码 `code`
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # 处理链接 [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # 移除列表符号 (- 或 * 或数字.)
    text = re.sub(r'^[\*\-]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    
    # 移除代码块标记 ```
    text = re.sub(r'```[\s\S]*?```', '这段代码', text)
    
    return text


def filter_asterisks(text: str) -> str:
    """
    Removes text enclosed within asterisks of any length (*, **, ***, etc.) from a string.

    Args:
        text: The input string.

    Returns:
        The string with asterisk-enclosed text removed.
    """
    # Handle asterisks of any length (*, **, ***, etc.)
    filtered_text = re.sub(r"\*{1,}((?!\*).)*?\*{1,}", "", text)

    # Clean up any extra spaces
    filtered_text = re.sub(r"\s+", " ", filtered_text).strip()

    return filtered_text
