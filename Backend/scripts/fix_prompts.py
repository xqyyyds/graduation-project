# -*- coding: utf-8 -*-
"""修复 prompts.py 中的证据链提示词"""

import re

with open("app/core/prompts.py", "r", encoding="utf-8") as f:
    content = f.read()

# 使用正则表达式替换
old_pattern = r'【任务要求】\n1\. \*\*构建证据链 \(evidence_chain\)\*\*：\n   - 必须建立 "原文引用 -> 违规性质 -> 法律依据" 的逻辑闭环。\n   - \*\*格式强制\*\*：必须包含具体的《微博社区公约》条款名称和编号。\n   - \*\*示例\*\*：\n     ❌ 错误："违反了《时政有害-社会秩序》第六条"（数据库标签格式，不适合展现）\n     ✅ 正确："评论#3 使用词汇\'xxx\'（原文），构成了对特定群体的侮辱（性质），违反了《微博社区公约》第十九条：禁止人身攻击（依据）。"\n\n2\. \*\*法规引用 \(cited_laws\)\*\*：\n   - 必须从输入 laws_json 中选择\*\*最相关的一条\*\*作为核心依据，并\*\*必须在 reasoning 中显式引用该条款的原文内容\*\*。\n   - 如果 laws_json 为空或不匹配，请引用"《微博社区公约》关于不良信息的通用规定"。\n\n3\. \*\*综合研判 \(reasoning\)\*\*：\n   - 综合分析违规的严重程度（是偶发的情绪宣泄，还是有组织的恶意攻击？）。\n   - 阐述该内容的潜在危害（如：引发群体对立、损害公信力、传播不良价值观）。\n   - \*\*必须完整写出，不得通过\.\.\.截断\*\*。如果内容过长，请精简为一针见血的核心论断。\n\n4\. \*\*处置建议 \(disposal_suggestion\)\*\*：\n   - 根据违规程度给出建议：如"建议仅删除评论"、"建议禁言账号"、"建议上报网信部门"等。'

new_text = """【任务要求】
1. **构建证据链 (evidence_chain)**：
   - 必须是**简洁有力的要点列表**，每个要点不超过50字。
   - **格式示例**：
     - "评论#3：使用'xxx'侮辱他人，违反《微博社区公约》第十九条"
     - "主贴：散布未经证实信息，违反《微博社区公约》第八条"
   - **严禁**输出长篇大论或被截断的内容。

2. **法规引用 (cited_laws)**：
   - 必须从 laws_json 中选择**最相关的条款**。
   - **条款名称格式**：写成"《微博社区公约》第X条"，不得使用数据库标签（如"时政有害-社会秩序"）。

3. **综合研判 (reasoning)**：
   - **长度限制**：不超过120字。
   - 简明扼要分析违规性质和潜在危害。
   - **禁止省略号截断**，必须完整表达。

4. **处置建议 (disposal_suggestion)**：
   - 简短明确，如："建议删除违规评论"或"建议账号警告"。"""

result = re.sub(old_pattern, new_text, content)

if result != content:
    with open("app/core/prompts.py", "w", encoding="utf-8") as f:
        f.write(result)
    print("SUCCESS: prompts.py updated")
else:
    print("WARNING: Pattern not matched, trying simpler approach...")

    # 简单字符串替换
    if '必须建立 "原文引用 -> 违规性质 -> 法律依据" 的逻辑闭环' in content:
        content = content.replace(
            '必须建立 "原文引用 -> 违规性质 -> 法律依据" 的逻辑闭环',
            "必须是**简洁有力的要点列表**，每个要点不超过50字",
        )
        content = content.replace(
            "**格式强制**：必须包含具体的《微博社区公约》条款名称和编号。",
            "**格式示例**：",
        )
        content = content.replace(
            "综合分析违规的严重程度（是偶发的情绪宣泄，还是有组织的恶意攻击？）。",
            "**长度限制**：不超过120字。",
        )
        content = content.replace(
            "阐述该内容的潜在危害（如：引发群体对立、损害公信力、传播不良价值观）。",
            "简明扼要分析违规性质和潜在危害。",
        )
        content = content.replace(
            "**必须完整写出，不得通过...截断**。如果内容过长，请精简为一针见血的核心论断。",
            "**禁止省略号截断**，必须完整表达。",
        )
        with open("app/core/prompts.py", "w", encoding="utf-8") as f:
            f.write(content)
        print("SUCCESS: prompts.py updated with simple replacements")
    else:
        print("FAILED: Could not find target text")
