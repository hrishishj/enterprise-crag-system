import pdfplumber

def load_pdf(path: str) -> str:
    text = ""
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            content = page.extract_text()
            if content:
                text += f"\n[Page {i+1}]\n{content}"
    return text
