import json

with open('data/output/7dfa8c95-df8f-4dfd-b48d-d070e5d1c27b.json', encoding='utf-8') as f:
    data = json.load(f)

chunks = data['chunks']
id_map = {c['chunk_id']: c['heading'].encode('ascii','ignore').decode('ascii') for c in chunks}

# Issue 1: Find chunks whose parent_id doesn't exist in the chunks list
print("=== ORPHANED CHUNKS (parent_id not found in chunks) ===")
for c in chunks:
    pid = c['metadata']['parent_id']
    if pid and pid not in id_map:
        h = c['heading'].encode('ascii','ignore').decode('ascii')
        print(f"  ORPHAN: heading={h!r}, parent_id={pid}")

# Issue 2: Check section 6 structure
print("\n=== SECTION 6 CHUNKS ===")
for c in chunks:
    h = c['heading'].encode('ascii','ignore').decode('ascii')
    if '6.' in h or 'Enterprise' in h or 'Morning Briefing' in h:
        pid = c['metadata']['parent_id']
        parent_h = id_map.get(pid, '** ORPHAN **') if pid else 'ROOT'
        print(f"  heading={h[:50]!r}, parent={parent_h[:30]!r}")

# Also find what IDs are referenced as parent but not in id_map
print("\n=== MISSING PARENT IDs ===")
all_chunk_ids = set(id_map.keys())
for c in chunks:
    pid = c['metadata']['parent_id']
    if pid and pid not in all_chunk_ids:
        # Find out if this was originally a chunk that got semantically split
        print(f"  Missing parent_id: {pid}")
