import os
import re

workspace_dir = "/home/yoon/cobot3_ws"

header_pattern = re.compile(
    r"(>\s*\[!IMPORTANT\]\s*\n\s*)?>\s*\*\*AI\s*에이전트\s*가이드\*\*:[^\n]+"
)

standardized_header = (
    "> [!IMPORTANT]\n"
    "> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, "
    "변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다."
)

def standardize_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if the pattern is in the file
    match = header_pattern.search(content)
    if match:
        new_content = header_pattern.sub(standardized_header, content, count=1)
        if new_content != content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Updated header in: {os.path.basename(file_path)}")
        else:
            print(f"Already standardized or no change: {os.path.basename(file_path)}")
    else:
        # If no standard block but we want to prepend/find it
        print(f"Header pattern not matched in: {os.path.basename(file_path)}")

# Find all markdown files
for root, dirs, files in os.walk(workspace_dir):
    if ".git" in root or ".gemini" in root:
        continue
    for file in files:
        if file.endswith(".md"):
            standardize_file(os.path.join(root, file))
