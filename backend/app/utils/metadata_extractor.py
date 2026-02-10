import io
import logging

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from docx import Document
except ImportError:
    Document = None

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

import csv

def extract_internal_metadata(file_bytes: bytes, mime_type: str) -> dict:
    """
    파일의 바이트(Bytes) 내용을 분석하여 내부 메타데이터와 텍스트 요약을 추출합니다.
    - PDF: 페이지 수, 저자, 프로듀서 (pypdf)
    - Image: 너비, 높이, 포맷 (Pillow)
    - DOCX: 페이지 수(단락 수 추정), 작성자, 텍스트 요약 (python-docx)
    - XLSX: 시트 수, 시트 이름, 작성자, 텍스트 요약 (openpyxl)
    - CSV: 행/열 수, 텍스트 요약 (csv)
    """
    meta = {}
    
    # 텍스트 요약 (AI용) - 최대 3000자
    text_preview = ""
    
    if not file_bytes:
        return meta
    
    try:
        file_stream = io.BytesIO(file_bytes)

        # 1. PDF
        if "pdf" in mime_type and PdfReader:
            try:
                reader = PdfReader(file_stream)
                meta["page_count"] = len(reader.pages)
                # Text Extraction (First 3 Pages)
                for i in range(min(3, len(reader.pages))):
                    text = reader.pages[i].extract_text() or ""
                    text_preview += text + "\n"
                
                if reader.metadata:
                    info = reader.metadata
                    if info.author: meta["author"] = str(info.author)
                    if info.producer: meta["producer"] = str(info.producer)
            except Exception as pdf_err:
                 print(f"[Metadata] PDF Parse Error: {pdf_err}")

        # 2. Image
        elif "image" in mime_type and Image:
            try:
                img = Image.open(file_stream)
                meta["width"] = img.width
                meta["height"] = img.height
                meta["format"] = img.format
            except Exception as img_err:
                 print(f"[Metadata] Image Parse Error: {img_err}")
                 
        # 3. DOCX (Word)
        elif "wordprocessingml" in mime_type and Document:
            try:
                doc = Document(file_stream)
                meta["author"] = doc.core_properties.author
                meta["last_modified_by"] = doc.core_properties.last_modified_by
                meta["paragraph_count"] = len(doc.paragraphs)
                
                # Text Extraction
                for para in doc.paragraphs[:50]: # First 50 paragraphs
                    text_preview += para.text + "\n"
            except Exception as docx_err:
                print(f"[Metadata] DOCX Parse Error: {docx_err}")

        # 4. XLSX (Excel)
        elif "spreadsheetml" in mime_type and load_workbook:
            try:
                wb = load_workbook(file_stream, read_only=True, data_only=True)
                meta["sheet_names"] = wb.sheetnames
                meta["sheet_count"] = len(wb.sheetnames)
                # meta["author"] = wb.properties.creator # Sometimes works
                
                # Text Extraction (First Sheet)
                if wb.sheetnames:
                    ws = wb[wb.sheetnames[0]]
                    # Read first 20 rows
                    for row in ws.iter_rows(min_row=1, max_row=20, values_only=True):
                        # Filter None
                        cleaned_row = [str(c) for c in row if c is not None]
                        text_preview += ", ".join(cleaned_row) + "\n"
            except Exception as xlsx_err:
                print(f"[Metadata] XLSX Parse Error: {xlsx_err}")

        # 5. CSV
        elif "csv" in mime_type or "comma-separated-values" in mime_type:
            try:
                # CSV can be encoded in various ways. Try UTF-8 usually.
                text_content = file_bytes.decode('utf-8', errors='ignore')
                file_stream_text = io.StringIO(text_content)
                reader = csv.reader(file_stream_text)
                rows = list(reader)
                meta["row_count"] = len(rows)
                if rows:
                    meta["col_count"] = len(rows[0])
                
                # Preview first 20 rows
                for row in rows[:20]:
                    text_preview += ", ".join(row) + "\n"
            except Exception as csv_err:
                print(f"[Metadata] CSV Parse Error: {csv_err}")

        # [Common] Add Text Preview to Meta
        if text_preview:
            # Truncate
            meta["text_preview"] = text_preview[:3000].strip()
            
    except Exception as e:
        print(f"[Metadata] Extraction failed: {e}")
        
    return meta
