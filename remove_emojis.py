"""
移除Backend和Frontend中日志打印的所有表情符号
"""
import os
import re

# 定义需要移除的表情符号映射
EMOJI_REPLACEMENTS = {
    '🔥': '',
    '📊': '',
    '📅': '',
    '🏷️': '',
    '🆔': '',
    '❌': '',
    '✅': '',
    '⚠️': '',
    '🚀': '',
    '📌': '',
    '✨': '',
    '📈': '',
    '📉': '',
    '🔮': '',
    '🎯': '',
    '💡': '',
    '🔍': '',
    '📝': '',
    '🔄': '',
    '🆕': '',
    '📥': '',
    '👮': '',
    '🧐': '',
    '🌐': '',
    '🧩': '',
    '🧹': '',
    '⏭️': '',
    '💾': '',
    '📄': '',
    '⚡': '',
    '🎨': '',
    '🔧': '',
    '📦': '',
    '🗂️': '',
    '📋': '',
    '🤖': '',
    '🧠': '',
    '👀': '',
    '🎭': '',
    '🌟': '',
    '⭐': '',
    '🔒': '',
    '🔓': '',
    '📎': '',
    '📁': '',
    '🏗️': '',
    '🎪': '',
    '🌈': '',
    '☀️': '',
    '🌙': '',
    '⛅': '',
    '🌧️': '',
    '❄️': '',
    '⚡': '',
    '🔥': '',
    '💧': '',
    '🌊': '',
    '🍀': '',
    '🌸': '',
    '🌺': '',
    '🌻': '',
    '🌼': '',
    '🌷': '',
    '🌹': '',
    '🎀': '',
    '🎁': '',
    '🎈': '',
    '🎉': '',
    '🎊': '',
    '🎵': '',
    '🎶': '',
    '🎹': '',
    '🎸': '',
    '🎺': '',
    '🎻': '',
    '🥁': '',
    '💿': '',
    '📱': '',
    '📲': '',
    '📞': '',
    '📟': '',
    '📠': '',
    '📺': '',
    '📻': '',
    '🎙️': '',
    '🎚️': '',
    '🎛️': '',
    '🧭': '',
}

def remove_emojis_from_file(file_path):
    """移除文件中的表情符号"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # 替换所有表情符号
        for emoji, replacement in EMOJI_REPLACEMENTS.items():
            content = content.replace(emoji, replacement)

        # 如果内容有变化，写回文件
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"处理文件失败 {file_path}: {e}")
        return False

def process_directory(directory, file_extensions):
    """处理目录中的所有文件"""
    changed_files = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(file.endswith(ext) for ext in file_extensions):
                file_path = os.path.join(root, file)
                if remove_emojis_from_file(file_path):
                    changed_files.append(file_path)

    return changed_files

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 处理Backend目录
    backend_dir = os.path.join(base_dir, "Backend")
    print("正在处理Backend目录...")
    backend_changes = process_directory(backend_dir, ['.py'])
    print(f"Backend: 修改了 {len(backend_changes)} 个文件")

    # 处理Frontend目录
    frontend_dir = os.path.join(base_dir, "Frontend")
    print("正在处理Frontend目录...")
    frontend_changes = process_directory(frontend_dir, ['.ts', '.tsx', '.js', '.jsx'])
    print(f"Frontend: 修改了 {len(frontend_changes)} 个文件")

    total = len(backend_changes) + len(frontend_changes)
    print(f"\n总计: 修改了 {total} 个文件")

    if total > 0:
        print("\n修改的文件列表:")
        for f in backend_changes + frontend_changes:
            print(f"  - {f}")
