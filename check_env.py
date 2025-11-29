with open('.env', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    
for i, line in enumerate(lines):
    if 'GIGACHAT_CLIENT_SECRET' in line:
        print(f'Line {i}: {repr(line)}')
        if i+1 < len(lines):
            print(f'Next line {i+1}: {repr(lines[i+1])}')

