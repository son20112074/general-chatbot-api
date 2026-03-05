# import pdfplumber

# with pdfplumber.open("test.pdf") as pdf:
#     text = ""
#     for page in pdf.pages:
#         text += page.extract_text(x_tolerance=2) + "\n"

# print(text)

import fitz

doc = fitz.open("test.pdf")
text = ""

for page in doc:
    text += page.get_text("text") + "\n"

print(text)