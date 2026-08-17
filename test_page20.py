import fitz

doc = fitz.open('data/uploads/590a0154-eb40-4164-8a9d-d807e6cbbff0.pdf')
page = doc.load_page(19) # page 20

drawings = page.get_drawings()
rects = []
page_rect = page.rect
for d in drawings:
    r = d.get("rect")
    if r:
        if r.width > page_rect.width * 0.9 or r.height > page_rect.height * 0.9:
            continue
        rects.append(r)

CLUSTER_MARGIN = 10.0
clusters = []
for r in rects:
    r_expanded = r + (-CLUSTER_MARGIN, -CLUSTER_MARGIN, CLUSTER_MARGIN, CLUSTER_MARGIN)
    matched_clusters = []
    
    for idx, c in enumerate(clusters):
        if r_expanded.intersects(c):
            matched_clusters.append(idx)
            
    if not matched_clusters:
        clusters.append(r)
    else:
        first_idx = matched_clusters[0]
        clusters[first_idx] |= r
        for idx in reversed(matched_clusters[1:]):
            clusters[first_idx] |= clusters[idx]
            clusters.pop(idx)

for i, c in enumerate(clusters):
    print(f"Cluster {i}: width={c.width}, height={c.height}, rect={c}")
