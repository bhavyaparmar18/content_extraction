"""Test hybrid chunking."""
import requests
import json

BASE = "http://127.0.0.1:8000"

# Upload the multiline test PDF again
with open("test_multiline.pdf", "rb") as f:
    r = requests.post(f"{BASE}/documents/upload", files={"file": f})

u = r.json()
did = u["document_id"]

# Get chunks without semantic refinement
print("=== HIERARCHICAL CHUNKS ONLY ===")
r_h = requests.get(f"{BASE}/documents/{did}/chunks?semantic=false")
d_h = r_h.json()
for c in d_h["chunks"]:
    print(f"Chunk [{c['chunk_type']}]: {c['metadata']['section']}")
    print(f"Content length: {len(c['content'].split())} words")
    print()

# Get chunks WITH semantic refinement
print("=== HYBRID (HIERARCHICAL + SEMANTIC) CHUNKS ===")
r_s = requests.get(f"{BASE}/documents/{did}/chunks?semantic=true")
d_s = r_s.json()
for c in d_s["chunks"]:
    print(f"Chunk [{c['chunk_type']}]: {c['metadata']['section']}")
    print(f"Content length: {len(c['content'].split())} words")
    print(f"Excerpt: {c['content'][:100]}...")
    print()
