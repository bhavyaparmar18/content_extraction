import fitz

doc = fitz.open('data/uploads/b6db819e-4a78-4e24-861b-7f406ed63832.pdf')
page = doc[1]
blocks = page.get_text('dict')['blocks']

for b in blocks:
    if b['type'] == 0:
        sizes = [s['size'] for l in b.get('lines', []) for s in l.get('spans', [])]
        max_size = max(sizes) if sizes else 0
        text = b.get('lines', [{}])[0].get('spans', [{}])[0].get('text', '')[:50]
        print(f"SZ: {max_size:.1f}, TXT: {text.encode('utf-8', 'ignore').decode('utf-8')}")
