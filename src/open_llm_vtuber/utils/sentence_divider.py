import re
from typing import List, Tuple, AsyncIterator, Optional, Union, Dict, Any
import pysbd
from loguru import logger
from langdetect import detect
from enum import Enum
from dataclasses import dataclass

# Constants for additional checks
COMMAS = [
    ",",
    "،",
    "，",
    "、",
    "፣",
    "၊",
    ";",
    "΄",
    "‛",
    "।",
    "﹐",
    "꓾",
    "⹁",
    "︐",
    "﹑",
    "､",
    "،",
]

END_PUNCTUATIONS = [".", "!", "?", "。", "！", "？", "...", "。。。"]
ABBREVIATIONS = [
    "Mr.",
    "Mrs.",
    "Dr.",
    "Prof.",
    "Inc.",
    "Ltd.",
    "Jr.",
    "Sr.",
    "e.g.",
    "i.e.",
    "vs.",
    "St.",
    "Rd.",
    "Dr.",
]

# Set of languages directly supported by pysbd
SUPPORTED_LANGUAGES = {
    "am",
    "ar",
    "bg",
    "da",
    "de",
    "el",
    "en",
    "es",
    "fa",
    "fr",
    "hi",
    "hy",
    "it",
    "ja",
    "kk",
    "mr",
    "my",
    "nl",
    "pl",
    "ru",
    "sk",
    "ur",
    "zh",
}


def detect_language(text: str) -> str:
    """
    Detect text language and check if it's supported by pysbd.
    Returns None for unsupported languages.
    """
    try:
        detected = detect(text)
        return detected if detected in SUPPORTED_LANGUAGES else None
    except Exception as e:
        logger.debug(f"Language detection failed, language not supported by pysdb: {e}")
        return None


def is_complete_sentence(text: str) -> bool:
    """
    Check if text ends with sentence-ending punctuation and not abbreviation.

    Args:
        text: Text to check

    Returns:
        bool: Whether the text is a complete sentence
    """
    text = text.strip()
    if not text:
        return False

    if any(text.endswith(abbrev) for abbrev in ABBREVIATIONS):
        return False

    return any(text.endswith(punct) for punct in END_PUNCTUATIONS)


def contains_comma(text: str) -> bool:
    """
    Check if text contains any comma.

    Args:
        text: Text to check

    Returns:
        bool: Whether the text contains a comma
    """
    return any(comma in text for comma in COMMAS)


def comma_splitter(text: str) -> Tuple[str, str]:
    """
    Process text and split it at the first comma.
    Protects markdown syntax (**, __, *, _, `, etc.) from being split.
    Returns the split text (including the comma) and the remaining text.

    Args:
        text: Text to split

    Returns:
        Tuple[str, str]: (split text with comma, remaining text)
    """
    if not text:
        return [], ""

    # 检查是否在markdown语法内部（简单保护）
    def is_inside_markdown(text, pos):
        """检查位置pos是否在markdown标记内部"""
        # 检查**bold**, __bold__
        before = text[:pos]
        # 统计之前出现的**和__
        bold_stars = before.count('**')
        bold_underscores = before.count('__')
        # 如果是奇数个，说明在标记内部
        if bold_stars % 2 == 1 or bold_underscores % 2 == 1:
            return True
        
        # 检查*italic*, _italic_
        single_stars = before.count('*') - bold_stars * 2
        single_underscores = before.count('_') - bold_underscores * 2
        if single_stars % 2 == 1 or single_underscores % 2 == 1:
            return True
        
        # 检查`code`和```code block```
        backticks = before.count('`')
        triple_backticks = before.count('```')
        if (backticks - triple_backticks * 3) % 2 == 1 or triple_backticks % 2 == 1:
            return True
        
        return False
    
    def should_skip_comma(text, pos):
        """检查是否应该跳过这个逗号"""
        # 1. 检查是否在markdown标记内部
        if is_inside_markdown(text, pos):
            return True
        
        # 2. 检查是否是markdown标题行（# 开头）
        line_start = text.rfind('\n', 0, pos)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1
        line_content = text[line_start:pos].strip()
        if line_content.startswith('#'):
            return True
        
        # 3. 检查是否在数字序号后（1, 2, 3, 或 1. 2. 3.）
        # 向后查看，检查逗号后面是否紧跟数字序号
        after_comma = text[pos+1:pos+10].strip()  # 查看逗号后10个字符
        
        # 如果逗号后面是：数字开头，可能是序号列表
        # 例如："第一步，2. 第二步" 或 "项目1, 2, 3"
        import re
        if re.match(r'^\s*\d+[.)，,\s]', after_comma):
            # 逗号后面跟着数字序号，应该切分（让序号归属下一句）
            return False
        
        # 检查逗号前是否是数字（如"1, 2, 3"）
        before_comma = text[max(0, pos-10):pos].strip()
        if re.search(r'\d+$', before_comma):
            # 前面是数字，但后面不是序号，可能是数字列举
            # 再检查更前面的内容
            before_more = text[max(0, pos-20):pos]
            # 如果前面有其他数字+逗号，说明是序号列表
            if re.search(r'\d+[,，]\s*\d+$', before_more):
                return True  # 跳过，保持"1, 2, 3"不切分
        
        return False

    for comma in COMMAS:
        if comma in text:
            # 找到所有逗号的位置
            pos = 0
            while True:
                pos = text.find(comma, pos)
                if pos == -1:
                    break
                
                # 检查这个逗号是否应该被跳过
                if not should_skip_comma(text, pos):
                    # 安全的逗号位置，可以切分
                    split_text = text[:pos+len(comma)].strip(), text[pos+len(comma):].strip()
                    return split_text[0], split_text[1]
                
                pos += len(comma)
    
    return text, ""


def has_punctuation(text: str) -> bool:
    """
    Check if the text is a punctuation mark.

    Args:
        text: Text to check

    Returns:
        bool: Whether the text is a punctuation mark
    """
    for punct in COMMAS + END_PUNCTUATIONS:
        if punct in text:
            return True
    return False


def contains_end_punctuation(text: str) -> bool:
    """
    Check if text contains any sentence-ending punctuation.

    Args:
        text: Text to check

    Returns:
        bool: Whether the text contains ending punctuation
    """
    return any(punct in text for punct in END_PUNCTUATIONS)


def segment_text_by_regex(text: str) -> Tuple[List[str], str]:
    """
    Segment text into complete sentences using regex pattern matching.
    More efficient but less accurate than pysbd.

    Args:
        text: Text to segment into sentences

    Returns:
        Tuple[List[str], str]: (list of complete sentences, remaining incomplete text)
    """
    if not text:
        return [], ""

    complete_sentences = []
    remaining_text = text.strip()

    # Create pattern for matching sentences ending with any end punctuation
    escaped_punctuations = [re.escape(p) for p in END_PUNCTUATIONS]
    pattern = r"(.*?(?:[" + "|".join(escaped_punctuations) + r"]))"

    while remaining_text:
        match = re.search(pattern, remaining_text)
        if not match:
            break

        end_pos = match.end(1)
        potential_sentence = remaining_text[:end_pos].strip()

        # Skip if sentence ends with abbreviation
        if any(potential_sentence.endswith(abbrev) for abbrev in ABBREVIATIONS):
            remaining_text = remaining_text[end_pos:].lstrip()
            continue

        complete_sentences.append(potential_sentence)
        remaining_text = remaining_text[end_pos:].lstrip()

    return complete_sentences, remaining_text


def _protect_latex(text: str) -> Tuple[str, dict]:
    """
    保护 LaTeX 公式内容，避免公式中的标点符号被错误分割。
    
    Args:
        text: 原始文本
        
    Returns:
        Tuple[str, dict]: (处理后的文本, 占位符到原内容的映射)
    """
    placeholders = {}
    counter = 0
    
    # 保护行内公式 $...$（但不是 $$）
    # 使用非贪婪匹配，允许公式内包含任意字符（除了 $）
    def replace_inline(match):
        nonlocal counter
        placeholder = f"__LATEX_INLINE_{counter}__"
        placeholders[placeholder] = match.group(0)
        counter += 1
        return placeholder
    
    # 保护块级公式 $$...$$
    def replace_block(match):
        nonlocal counter
        placeholder = f"__LATEX_BLOCK_{counter}__"
        placeholders[placeholder] = match.group(0)
        counter += 1
        return placeholder
    
    # 先处理块级公式（$$...$$），避免与行内公式冲突
    # 使用 [\s\S] 匹配任意字符包括换行符
    protected = re.sub(r'\$\$[\s\S]+?\$\$', replace_block, text)
    # 再处理行内公式（$...$）
    # 使用非贪婪匹配，不匹配换行符（行内公式一般不跨行）
    protected = re.sub(r'\$(?!\$)([^$\n]+?)\$', replace_inline, protected)
    
    return protected, placeholders


def _restore_latex(sentences: List[str], placeholders: dict) -> List[str]:
    """
    恢复 LaTeX 公式内容。
    
    Args:
        sentences: 分割后的句子列表
        placeholders: 占位符到原内容的映射
        
    Returns:
        恢复后的句子列表
    """
    restored = []
    for sentence in sentences:
        for placeholder, original in placeholders.items():
            sentence = sentence.replace(placeholder, original)
        restored.append(sentence)
    return restored


def segment_text_by_pysbd(text: str) -> Tuple[List[str], str]:
    """
    Segment text into complete sentences and remaining text.
    Uses pysbd for supported languages, falls back to regex for others.

    Args:
        text: Text to segment into sentences

    Returns:
        Tuple[List[str], str]: (list of complete sentences, remaining incomplete text)
    """
    if not text:
        return [], ""

    try:
        # 先保护 LaTeX 公式
        protected_text, placeholders = _protect_latex(text)
        
        # Detect language
        lang = detect_language(protected_text)

        if lang is not None:
            # Use pysbd for supported languages
            segmenter = pysbd.Segmenter(language=lang, clean=False)
            sentences = segmenter.segment(protected_text)

            if not sentences:
                return [], text

            # Process all but the last sentence
            complete_sentences = []
            for sent in sentences[:-1]:
                sent = sent.strip()
                if sent:
                    complete_sentences.append(sent)

            # Handle the last sentence
            last_sent = sentences[-1].strip()
            if is_complete_sentence(last_sent):
                complete_sentences.append(last_sent)
                remaining = ""
            else:
                remaining = last_sent
            
            # 恢复 LaTeX 公式
            complete_sentences = _restore_latex(complete_sentences, placeholders)
            if remaining:
                remaining = _restore_latex([remaining], placeholders)[0]

        else:
            # Use regex for unsupported languages
            return segment_text_by_regex(text)

        logger.debug(
            f"Processed sentences: {complete_sentences}, Remaining: {remaining}"
        )
        return complete_sentences, remaining

    except Exception as e:
        logger.error(f"Error in sentence segmentation: {e}")
        # Fallback to regex on any error
        return segment_text_by_regex(text)


class TagState(Enum):
    """State of a tag in text"""

    START = "start"  # <tag>
    INSIDE = "inside"  # text between tags
    END = "end"  # </tag>
    SELF_CLOSING = "self"  # <tag/>
    NONE = "none"  # no tag


@dataclass
class TagInfo:
    """Information about a tag"""

    name: str
    state: TagState

    def __str__(self) -> str:
        """String representation of tag info"""
        if self.state == TagState.NONE:
            return "none"
        return f"{self.name}:{self.state.value}"


@dataclass
class SentenceWithTags:
    """A sentence with its tag information, supporting nested tags"""

    text: str
    tags: List[TagInfo]  # List of tags from outermost to innermost
    tts_text: Optional[str] = None  # 双流输出模式下的TTS文本


@dataclass
class DualStreamPair:
    """双流输出的一对文本：显示文本和TTS文本"""
    display_text: str  # <show>标签内的内容，用于显示
    tts_text: str      # <say>标签内的内容，用于TTS


class SentenceDivider:
    def __init__(
        self,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        valid_tags: List[str] = None,
        dual_stream_mode: bool = True,  # 新增：双流输出模式
    ):
        """
        Initialize the SentenceDivider.

        Args:
            faster_first_response: Whether to split first sentence at commas
            segment_method: Method for segmenting sentences
            valid_tags: List of valid tag names to detect
            dual_stream_mode: Whether to use dual stream mode (show/say tags)
        """
        self.faster_first_response = faster_first_response
        self.segment_method = segment_method
        self.valid_tags = valid_tags or ["think"]
        self.dual_stream_mode = dual_stream_mode
        self._is_first_sentence = True
        self._buffer = ""
        # Replace active_tags dict with a stack to handle nesting
        self._tag_stack = []
        # 双流模式的正则表达式
        self._dual_stream_pattern = re.compile(
            r'<show>(.*?)</show>\s*<say>(.*?)</say>',
            re.DOTALL
        )

    def _get_current_tags(self) -> List[TagInfo]:
        """
        Get all current active tags from outermost to innermost.

        Returns:
            List[TagInfo]: List of active tags
        """
        return [TagInfo(tag.name, TagState.INSIDE) for tag in self._tag_stack]

    def _get_current_tag(self) -> Optional[TagInfo]:
        """
        Get the current innermost active tag.

        Returns:
            TagInfo if there's an active tag, None otherwise
        """
        return self._tag_stack[-1] if self._tag_stack else None

    def _extract_tag(self, text: str) -> Tuple[Optional[TagInfo], str]:
        """
        Extract the first tag from text if present.
        Handles nested tags by maintaining a tag stack.

        Args:
            text: Text to check for tags

        Returns:
            Tuple of (TagInfo if tag found else None, remaining text)
        """
        # Find the first occurrence of any tag
        first_tag = None
        first_pos = len(text)
        tag_type = None
        matched_tag = None

        # Check for self-closing tags
        for tag in self.valid_tags:
            pattern = f"<{tag}/>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.SELF_CLOSING
                matched_tag = tag

        # Check for opening tags
        for tag in self.valid_tags:
            pattern = f"<{tag}>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.START
                matched_tag = tag

        # Check for closing tags
        for tag in self.valid_tags:
            pattern = f"</{tag}>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.END
                matched_tag = tag

        if not first_tag:
            return None, text

        # Handle the found tag
        if tag_type == TagState.START:
            # Push new tag onto stack
            self._tag_stack.append(TagInfo(matched_tag, TagState.START))
        elif tag_type == TagState.END:
            # Verify matching tags
            if not self._tag_stack or self._tag_stack[-1].name != matched_tag:
                logger.warning(f"Mismatched closing tag: {matched_tag}")
            else:
                self._tag_stack.pop()

        return (TagInfo(matched_tag, tag_type), text[first_tag.end() :].lstrip())

    async def _process_buffer(self) -> AsyncIterator[SentenceWithTags]:
        """
        Process the current buffer, yielding complete sentences with tags.
        This is now an async generator.
        It consumes processed parts from self._buffer.
        """
        processed_something = True  # Flag to loop until no more processing can be done
        while processed_something:
            processed_something = False
            original_buffer_len = len(self._buffer)

            if not self._buffer.strip():
                break

            # Find the next tag position
            next_tag_pos = len(self._buffer)
            tag_pattern_found = None
            for tag in self.valid_tags:
                patterns = [f"<{tag}>", f"</{tag}>", f"<{tag}/>"]
                for pattern in patterns:
                    pos = self._buffer.find(pattern)
                    if pos != -1 and pos < next_tag_pos:
                        next_tag_pos = pos
                        tag_pattern_found = pattern  # Store the found pattern

            if next_tag_pos == 0:
                # Tag is at the start of buffer
                tag_info, remaining = self._extract_tag(self._buffer)
                if tag_info:
                    processed_text = self._buffer[
                        : len(self._buffer) - len(remaining)
                    ].strip()
                    # Yield the tag itself, represented as a SentenceWithTags
                    yield SentenceWithTags(text=processed_text, tags=[tag_info])
                    self._buffer = remaining
                    processed_something = True
                    continue  # Restart processing loop for the remaining buffer

            elif next_tag_pos < len(self._buffer):
                # Tag is in the middle - process text before tag first
                text_before_tag = self._buffer[:next_tag_pos]
                current_tags = self._get_current_tags()
                processed_segment = ""

                # Process complete sentences in text before tag
                if contains_end_punctuation(text_before_tag):
                    sentences, remaining_before = self._segment_text(text_before_tag)
                    for sentence in sentences:
                        if sentence.strip():
                            yield SentenceWithTags(
                                text=sentence.strip(),
                                tags=current_tags or [TagInfo("", TagState.NONE)],
                            )
                    # The part consumed includes sentences + what's left before the tag
                    processed_segment = text_before_tag
                    self._buffer = self._buffer[len(processed_segment) :]
                    processed_something = True
                    continue  # Restart processing loop

                elif text_before_tag.strip() and tag_pattern_found:
                    # No sentence end, but content exists AND we found a tag pattern after it.
                    # We can yield this segment because the tag provides a boundary.
                    yield SentenceWithTags(
                        text=text_before_tag.strip(),
                        tags=current_tags or [TagInfo("", TagState.NONE)],
                    )
                    self._buffer = self._buffer[len(text_before_tag) :]
                    processed_something = True
                    continue  # Restart processing loop
                # --- If no tag found after text_before_tag, we wait for more input or end punctuation ---

                # Process the tag itself if we haven't continued
                tag_info, remaining_after_tag = self._extract_tag(self._buffer)
                if tag_info:
                    processed_tag_text = self._buffer[
                        : len(self._buffer) - len(remaining_after_tag)
                    ].strip()
                    yield SentenceWithTags(text=processed_tag_text, tags=[tag_info])
                    self._buffer = remaining_after_tag
                    processed_something = True
                    continue  # Restart processing loop

            # No tags found or tag is not at the beginning/middle of processable segment
            # Process normal text if buffer has changed or punctuation exists
            if original_buffer_len > 0:
                current_tags = self._get_current_tags()

                # Handle first sentence with comma if enabled
                if (
                    self._is_first_sentence
                    and self.faster_first_response
                    and contains_comma(self._buffer)
                ):
                    sentence, remaining = comma_splitter(self._buffer)
                    if sentence.strip():
                        yield SentenceWithTags(
                            text=sentence.strip(),
                            tags=current_tags or [TagInfo("", TagState.NONE)],
                        )
                        self._buffer = remaining
                        self._is_first_sentence = False
                        processed_something = True
                        continue  # Restart processing loop

                # Process normal sentences based on end punctuation
                if contains_end_punctuation(self._buffer):
                    sentences, remaining = self._segment_text(self._buffer)
                    if sentences:  # Only process if segmentation yielded sentences
                        self._buffer = remaining
                        self._is_first_sentence = False
                        processed_something = True
                        for sentence in sentences:
                            if sentence.strip():
                                yield SentenceWithTags(
                                    text=sentence.strip(),
                                    tags=current_tags or [TagInfo("", TagState.NONE)],
                                )
                        continue  # Restart processing loop

            # If we reached here without processing anything, break the loop
            if not processed_something:
                break

    async def _flush_buffer(self) -> AsyncIterator[SentenceWithTags]:
        """
        Process and yield all remaining content in the buffer at the end of the stream.
        """
        logger.debug(f"Flushing remaining buffer: '{self._buffer}'")
        # First, run _process_buffer to yield any standard sentences/tags
        async for sentence in self._process_buffer():
            yield sentence

        # After processing standard structures, if anything is left, yield it as a final fragment
        if self._buffer.strip():
            logger.debug(
                f"Yielding final fragment from buffer: '{self._buffer.strip()}'"
            )
            current_tags = self._get_current_tags()
            yield SentenceWithTags(
                text=self._buffer.strip(),
                tags=current_tags or [TagInfo("", TagState.NONE)],
            )
            self._buffer = ""  # Clear buffer after flushing

    async def process_stream(
        self, segment_stream: AsyncIterator[Union[str, Dict[str, Any]]]
    ) -> AsyncIterator[Union[SentenceWithTags, Dict[str, Any]]]:
        """
        Process a stream of tokens (strings) and dictionaries.
        Yields complete sentences with tags (SentenceWithTags) or dictionaries directly.

        Args:
            segment_stream: An async iterator yielding strings or dictionaries.

        Yields:
            Union[SentenceWithTags, Dict[str, Any]]: Complete sentences/tags or original dictionaries.
        """
        self._full_response = []
        self.reset()  # Ensure state is clean

        async for item in segment_stream:
            if isinstance(item, dict):
                # Before yielding the dict, process and yield any complete sentences formed so far
                if self.dual_stream_mode:
                    async for sentence in self._process_dual_stream_buffer():
                        self._full_response.append(sentence.text)
                        yield sentence
                else:
                    async for sentence in self._process_buffer():
                        self._full_response.append(sentence.text)
                        yield sentence
                # Now yield the dictionary
                yield item
            elif isinstance(item, str):
                self._buffer += item
                # Process the buffer incrementally as string chunks arrive
                if self.dual_stream_mode:
                    async for sentence in self._process_dual_stream_buffer():
                        self._full_response.append(sentence.text)
                        yield sentence
                else:
                    async for sentence in self._process_buffer():
                        self._full_response.append(sentence.text)
                        yield sentence
            else:
                logger.warning(
                    f"SentenceDivider received unexpected type: {type(item)}"
                )

        # After the stream finishes, flush any remaining text in the buffer
        if self.dual_stream_mode:
            async for sentence in self._flush_dual_stream_buffer():
                self._full_response.append(sentence.text)
                yield sentence
        else:
            async for sentence in self._flush_buffer():
                self._full_response.append(sentence.text)
                yield sentence

    async def _process_dual_stream_buffer(self) -> AsyncIterator[SentenceWithTags]:
        """
        处理双流模式的缓冲区，提取 <show>...</show><say>...</say> 对。
        """
        while True:
            # 查找完整的双流对
            match = self._dual_stream_pattern.search(self._buffer)
            if not match:
                break
            
            display_text = match.group(1).strip()
            tts_text = match.group(2).strip()
            
            logger.debug(f"双流输出 - 显示: {display_text}, TTS: {tts_text}")
            
            # 生成带有 TTS 文本的 SentenceWithTags
            yield SentenceWithTags(
                text=display_text,
                tags=[TagInfo("", TagState.NONE)],
                tts_text=tts_text
            )
            
            # 从缓冲区移除已处理的部分
            self._buffer = self._buffer[match.end():]
            self._is_first_sentence = False

    async def _flush_dual_stream_buffer(self) -> AsyncIterator[SentenceWithTags]:
        """
        双流模式下刷新缓冲区，处理剩余内容。
        """
        # 先处理所有完整的双流对
        async for sentence in self._process_dual_stream_buffer():
            yield sentence
        
        # 处理剩余内容（可能是不完整的或非双流格式的文本）
        remaining = self._buffer.strip()
        if remaining:
            # 尝试提取不完整的标签内容
            # 检查是否有未闭合的 <show> 标签
            show_match = re.search(r'<show>(.*?)(?:</show>|$)', remaining, re.DOTALL)
            if show_match:
                display_text = show_match.group(1).strip()
                if display_text:
                    logger.debug(f"双流刷新 - 剩余显示文本: {display_text}")
                    yield SentenceWithTags(
                        text=display_text,
                        tags=[TagInfo("", TagState.NONE)],
                        tts_text=display_text  # 没有TTS版本，使用显示文本
                    )
            elif not remaining.startswith('<'):
                # 非标签格式的剩余文本，可能是 LLM 没有遵循格式
                logger.warning(f"双流模式下收到非标签格式文本: {remaining}")
                yield SentenceWithTags(
                    text=remaining,
                    tags=[TagInfo("", TagState.NONE)],
                    tts_text=remaining
                )
        
        self._buffer = ""

        # After the stream finishes, flush any remaining text in the buffer
        async for sentence in self._flush_buffer():
            self._full_response.append(sentence.text)
            yield sentence

    @property
    def complete_response(self) -> str:
        """Get the complete response accumulated so far"""
        return "".join(self._full_response)

    def _segment_text(self, text: str) -> Tuple[List[str], str]:
        """Segment text using the configured method"""
        # 首先按换行符分割（处理 Markdown 多行内容）
        lines = text.split('\n')
        all_sentences = []
        last_remaining = ""
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # 如果是最后一行，正常处理
            if i == len(lines) - 1:
                if self.segment_method == "regex":
                    sentences, remaining = segment_text_by_regex(line)
                else:
                    sentences, remaining = segment_text_by_pysbd(line)
                all_sentences.extend(sentences)
                last_remaining = remaining
            else:
                # 非最后一行，整行作为完整句子（因为有换行符分隔）
                if self.segment_method == "regex":
                    sentences, remaining = segment_text_by_regex(line)
                else:
                    sentences, remaining = segment_text_by_pysbd(line)
                all_sentences.extend(sentences)
                # 如果还有剩余内容，也作为完整句子
                if remaining.strip():
                    all_sentences.append(remaining.strip())
        
        # 后处理：合并孤立的序号到下一句
        all_sentences = self._merge_isolated_numbers(all_sentences)
        
        # 后处理：去除句尾的句号和逗号
        all_sentences = self._remove_trailing_punctuation(all_sentences)
        
        return all_sentences, last_remaining
    
    def _remove_trailing_punctuation(self, sentences: List[str]) -> List[str]:
        """
        去除句尾的句号和逗号。
        
        Args:
            sentences: 句子列表
            
        Returns:
            处理后的句子列表
        """
        result = []
        for sentence in sentences:
            stripped = sentence.rstrip()
            # 检查并去除句尾的 。 或 ，
            if stripped.endswith('。') or stripped.endswith('，'):
                stripped = stripped[:-1]
            result.append(stripped)
        return result
    
    def _merge_isolated_numbers(self, sentences: List[str]) -> List[str]:
        """
        合并孤立的序号到下一句。
        例如: ["内容，", "1.", "第一步"] → ["内容，", "1. 第一步"]
        
        Args:
            sentences: 切分后的句子列表
            
        Returns:
            合并后的句子列表
        """
        if not sentences:
            return sentences
        
        import re
        merged = []
        pending = ""  # 待合并的序号
        
        for sentence in sentences:
            stripped = sentence.strip()
            
            # 检查是否是孤立序号（如 "1." "2)" "(3)" "①" 等）
            is_isolated_number = bool(re.match(
                r'^(\d+[.)\uff09\u3001]?|\(\d+\)|[\u2460-\u2473])$', 
                stripped
            ))
            
            if is_isolated_number:
                # 这是一个孤立序号，等待与下一句合并
                pending = stripped + " "
            elif pending:
                # 有待合并的序号，合并到当前句子
                merged.append(pending + stripped)
                pending = ""
            else:
                # 普通句子，直接添加
                merged.append(sentence)
        
        # 如果最后还有待合并的序号，单独添加
        if pending:
            merged.append(pending.strip())
        
        return merged

    def reset(self):
        """Reset the divider state for a new conversation"""
        self._is_first_sentence = True
        self._buffer = ""
        self._tag_stack = []
