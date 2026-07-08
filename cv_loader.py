"""
cv_loader.py — Lecture de CV (PDF, DOCX, TXT) et export DOCX
"""

import os
from pathlib import Path


def load_cv(file_path: str = None, uploaded_file=None) -> str:
    """
    Charge le contenu d'un CV depuis un fichier local ou un fichier uploadé Streamlit.
    Supporte les formats : PDF, DOCX, TXT
    """
    if uploaded_file is not None:
        return _load_from_upload(uploaded_file)
    if file_path:
        return _load_from_path(file_path)
    raise ValueError("Fournissez soit un chemin de fichier soit un fichier uploadé.")


def _load_from_upload(uploaded_file) -> str:
    """Charge depuis un UploadedFile Streamlit."""
    name = uploaded_file.name.lower()
    data = uploaded_file.read()

    if name.endswith(".pdf"):
        return _extract_pdf_bytes(data)
    elif name.endswith(".docx"):
        return _extract_docx_bytes(data)
    elif name.endswith(".txt") or name.endswith(".md"):
        return data.decode("utf-8", errors="ignore")
    else:
        # Tente de décoder en texte brut
        return data.decode("utf-8", errors="ignore")


def _load_from_path(file_path: str) -> str:
    """Charge depuis un chemin local."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {file_path}")

    ext = path.suffix.lower()
    if ext == ".pdf":
        with open(path, "rb") as f:
            return _extract_pdf_bytes(f.read())
    elif ext == ".docx":
        with open(path, "rb") as f:
            return _extract_docx_bytes(f.read())
    elif ext in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    else:
        return path.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf_bytes(data: bytes) -> str:
    """Extrait le texte d'un PDF (bytes)."""
    try:
        import pdfplumber
        import io
        text_parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    try:
        import PyPDF2
        import io
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n\n".join(text_parts)
    except ImportError:
        raise ImportError("Installez pdfplumber ou PyPDF2 : pip install pdfplumber")


def _extract_docx_bytes(data: bytes) -> str:
    """Extrait le texte d'un DOCX (bytes)."""
    try:
        import docx
        import io
        doc = docx.Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except ImportError:
        raise ImportError("Installez python-docx : pip install python-docx")


def export_to_docx(content: str, filename: str = "document.docx") -> bytes:
    """
    Convertit du texte en fichier DOCX et retourne les bytes.
    Le texte peut utiliser des marqueurs Markdown simples (## pour titres, ** pour gras).
    """
    try:
        import docx
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        import io

        doc = docx.Document()

        # Style général
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        lines = content.split("\n")
        for line in lines:
            line_stripped = line.strip()

            if line_stripped.startswith("## "):
                # Titre de niveau 2
                heading = doc.add_heading(line_stripped[3:], level=2)
                heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
            elif line_stripped.startswith("# "):
                # Titre principal
                heading = doc.add_heading(line_stripped[2:], level=1)
                heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif line_stripped.startswith("**") and line_stripped.endswith("**"):
                # Texte en gras
                p = doc.add_paragraph()
                run = p.add_run(line_stripped[2:-2])
                run.bold = True
            elif line_stripped == "---" or line_stripped == "___":
                # Séparateur
                doc.add_paragraph("─" * 60)
            elif line_stripped == "":
                doc.add_paragraph("")
            else:
                # Paragraphe normal, gestion du gras inline
                p = doc.add_paragraph()
                _add_formatted_run(p, line_stripped)

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    except ImportError:
        raise ImportError("Installez python-docx : pip install python-docx")


def _add_formatted_run(paragraph, text: str):
    """Ajoute du texte avec formatage gras inline (**...**)."""
    import re
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        else:
            paragraph.add_run(part)
