import fitz
import pdfplumber

page_num = 3 # 0-indexed page 4
pdf_path = 'data/uploads/590a0154-eb40-4164-8a9d-d807e6cbbff0.pdf'

doc = fitz.open(pdf_path)
page = doc.load_page(page_num)

images = page.get_images(full=True)
print(f"Embedded images on page 4: {len(images)}")
for img in images:
    print(img)

drawings = page.get_drawings()
print(f"Drawings on page 4: {len(drawings)}")

with pdfplumber.open(pdf_path) as pdf:
    p = pdf.pages[page_num]
    tables = p.find_tables()
    for i, t in enumerate(tables):
        print(f"Table {i}: bbox={t.bbox}")
        for r_idx, row in enumerate(t.rows):
            for c_idx, cell in enumerate(row.cells):
                print(f"  Cell {r_idx},{c_idx}: {cell}")
