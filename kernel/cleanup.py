import os, glob, re

fixed = 0
for f in glob.glob('crates/*/src/lib.rs'):
    with open(f, 'r') as file:
        content = file.read()
    
    # Try finding markdown code block, handling missing closing backticks
    match = re.search(r'```(?:rust)?\s*(.*?)(?:```|$)', content, re.DOTALL)
    
    if match and len(match.group(1)) > 50:
        cleaned = match.group(1).strip()
        if cleaned != content.strip():
            with open(f, 'w') as file:
                file.write(cleaned + '\n')
            fixed += 1

print(f'Fixed {fixed} files')
