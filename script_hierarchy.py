"""Test hierarchy tree builder."""
import requests
import json

BASE = "http://127.0.0.1:8000"

# Upload
with open("test_hierarchy.pdf", "rb") as f:
    r = requests.post(f"{BASE}/documents/upload", files={"file": f})

u = r.json()
did = u["document_id"]

# Get tree
r2 = requests.get(f"{BASE}/documents/{did}/tree")
d = r2.json()

def print_tree(node, indent=0):
    space = "  " * indent
    if node.get("heading"):
        print(f"{space}- [{node['heading']['level']}] {node['heading']['content']}")
    else:
        print(f"{space}- [0] ROOT")
        
    for el in node.get("elements", []):
        print(f"{space}  * {el['element_type']}: {el['content'][:50]}")
        
    for child in node.get("children", []):
        print_tree(child, indent + 1)

print_tree(d["root"])
