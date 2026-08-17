"""Test multiline paragraph aggregation."""
import requests
import json

BASE = "http://127.0.0.1:8000"

# Upload
with open("test_multiline.pdf", "rb") as f:
    r = requests.post(f"{BASE}/documents/upload", files={"file": f})

u = r.json()
did = u["document_id"]

# Get elements
r2 = requests.get(f"{BASE}/documents/{did}/elements")
d = r2.json()
print(f"Total elements: {d['total_elements']}")
print()
for el in d["elements"]:
    etype = el["element_type"]
    content = el["content"]
    print(f"  [{etype:>10}]  {content}")
    print()
