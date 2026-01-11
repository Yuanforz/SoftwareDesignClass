#!/usr/bin/env python3
"""测试句子切割的保护逻辑"""

def should_skip_comma_test(text, pos):
    """测试版本的保护逻辑"""
    import re
    
    # 检查是否是markdown标题行
    line_start = text.rfind('\n', 0, pos)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1
    line_content = text[line_start:pos].strip()
    if line_content.startswith('#'):
        return True, "Markdown标题"
    
    # 向后查看，检查逗号后面是否紧跟数字序号
    after_comma = text[pos+1:pos+10].strip()
    if re.match(r'^\s*\d+[.),，\s]', after_comma):
        return False, f"逗号后是序号: {after_comma[:5]} -> 应该切分"
    
    # 检查逗号前是否是数字
    before_comma = text[max(0, pos-10):pos].strip()
    if re.search(r'\d+$', before_comma):
        # 再检查更前面的内容
        before_more = text[max(0, pos-20):pos]
        if re.search(r'\d+[,，]\s*\d+$', before_more):
            return True, f"数字序列: {before_more[-10:]} -> 跳过"
    
    return False, "正常逗号"

# 测试用例
test_cases = [
    # 问题场景：序号应该归属下一句
    ("第一步完成，1. 开始第二步", 5),  # 应该切分，让"1."归到下一句
    ("项目完成，2. 继续下一个", 5),    # 应该切分
    
    # 数字序列：不应该切分
    ("第1, 2, 3项都很重要", 2),  # "1," 不切分
    ("第1, 2, 3项都很重要", 5),  # "2," 不切分
    
    # Markdown标题测试
    ("# 这是标题，不应该切分", 6),
    
    # 普通逗号测试
    ("这是正常的句子，应该在这里切分", 7),
]

print("=" * 70)
print("句子切割保护逻辑测试（修复后）")
print("=" * 70)

for text, pos in test_cases:
    skip, reason = should_skip_comma_test(text, pos)
    char = text[pos] if pos < len(text) else '?'
    print(f"\n文本: {text}")
    print(f"位置: {pos} (字符: '{char}')")
    print(f"结果: {'❌ 跳过' if skip else '✅ 切分'} - {reason}")
    
    # 显示切分效果
    if not skip and pos < len(text):
        part1 = text[:pos+1].strip()
        part2 = text[pos+1:].strip()
        print(f"  → 第一部分: '{part1}'")
        print(f"  → 第二部分: '{part2}'")

print("\n" + "=" * 70)
print("预期结果:")
print("  '第一步完成，1. 开始第二步' → 应切分为:")
print("    1. '第一步完成，'")
print("    2. '1. 开始第二步'")
print("=" * 70)


