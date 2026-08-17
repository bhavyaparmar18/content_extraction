"""Quick test script — upload a PDF, extract, and inspect elements."""
import requests
import json

BASE = "http://127.0.0.1:8000"

# 1. Upload
with open("test_sop.pdf", "rb") as f:
    r = requests.post(
        f"{BASE}/documents/upload",
        files={"file": ("SOP_001_Cleaning.pdf", f, "application/pdf")},
    )

upload = r.json()
print("=== UPLOAD ===")
print(json.dumps(upload, indent=2))

doc_id = upload["document_id"]

# 2. Extract
r2 = requests.post(f"{BASE}/documents/extract", json={"document_id": doc_id})
print("\n=== EXTRACT ===")
print(json.dumps(r2.json(), indent=2))

# 3. Get elements
r3 = requests.get(f"{BASE}/documents/{doc_id}/elements")
data = r3.json()
total = data["total_elements"]
print(f"\n=== ELEMENTS ({total} total) ===")
for el in data["elements"]:
    etype = el["element_type"]
    content = el["content"][:90]
    print(f"  [{etype:>10}]  {content}")
