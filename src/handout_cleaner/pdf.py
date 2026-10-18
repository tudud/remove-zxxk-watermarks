from io import BytesIO
from pathlib import Path
import re
import pymupdf as fitz
from PIL import Image
from .rules import watermark_spans, source_edits, ANSWER_HEADING_RE, ANSWER_MARK_RE, QUESTION_RE


def char_lines(page):
    lines = []
    for block in page.get_text('rawdict').get('blocks', []):
        for line in block.get('lines', []):
            chars = [c for span in line.get('spans', []) for c in span.get('chars', [])]
            if chars:
                lines.append((''.join(c['c'] for c in chars), chars))
    return lines


def clean_pdf(source: Path, target: Path, options, record, ocr, notify=lambda _: None, check_cancel=lambda: None):
    with fitz.open(source) as doc:
        processed_images = set()
        for index, page in enumerate(doc):
            check_cancel()
            notify(f'OCR / PDF 清理 {index+1}/{len(doc)} 页')
            if options.ocr:
                from .background import clean_faint_background
                for image_info in page.get_images():
                    xref = image_info[0]
                    if xref in processed_images:
                        continue
                    processed_images.add(xref)
                    original = doc.extract_image(xref)
                    if not original:
                        continue
                    cleaned, count = clean_faint_background(original['image'], ocr)
                    if count:
                        page.replace_image(xref, stream=cleaned)
                        record.watermark_count += count
                        record.actions.append(f'第{index+1}页：清理淡色背景水印 {count} 处，保留深色正文')
            rectangles = []
            text_lines = char_lines(page)
            positioned = [(text, (min(c['bbox'][0] for c in chars), min(c['bbox'][1] for c in chars), max(c['bbox'][2] for c in chars), max(c['bbox'][3] for c in chars))) for text, chars in text_lines]
            for (text, chars), ranges in zip(text_lines, watermark_spans(positioned)):
                record.watermark_count += len(ranges)
                edits = source_edits(text, options.source_mode)
                record.source_count += len(edits)
                ranges.extend((start, end) for start, end, _ in edits)
                for start, end in ranges:
                    rect = fitz.Rect()
                    for char in chars[start:end]:
                        rect |= fitz.Rect(char['bbox'])
                    if not rect.is_empty:
                        rectangles.append(rect)
            if options.ocr:
                scale = 2.0
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                results = ocr.read(image)
                positioned = [(text, (min(p[0] for p in box), min(p[1] for p in box), max(p[0] for p in box), max(p[1] for p in box))) for box, text, _ in results]
                for (box, text, score), matches in zip(results, watermark_spans(positioned)):
                    record.watermark_count += len(matches)
                    edits = source_edits(text, options.source_mode)
                    record.source_count += len(edits)
                    matches.extend((a, b) for a, b, _ in edits)
                    x0, x1 = min(p[0] for p in box)/scale, max(p[0] for p in box)/scale
                    y0, y1 = min(p[1] for p in box)/scale, max(p[1] for p in box)/scale
                    for start, end in matches:
                        rect = fitz.Rect(x0+(x1-x0)*start/max(1, len(text)), y0, x0+(x1-x0)*end/max(1, len(text)), y1)
                        rectangles.append(rect)
            for rect in rectangles:
                page.add_redact_annot(rect+(-0.3, -0.3, 0.3, 0.3), fill=(1, 1, 1))
            if rectangles:
                page.apply_redactions(images=2, graphics=0, text=0)
        doc.save(target, garbage=4, deflate=True)


def image_docx(pdf: Path, target: Path, ocr=None, text_mode=False):
    from docx import Document
    from docx.shared import Inches, Pt
    doc = Document()
    section = doc.sections[0]
    with fitz.open(pdf) as pages:
        first = pages[0]
        section.page_width = Inches(first.rect.width/72)
        section.page_height = Inches(first.rect.height/72)
        section.top_margin = section.bottom_margin = Inches(0.1)
        section.left_margin = section.right_margin = Inches(0.1)
        for index, page in enumerate(pages):
            if index:
                doc.add_page_break()
            pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            if text_mode and ocr:
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                lines = ocr.read(image)
                for box, text, score in lines:
                    doc.add_paragraph(text)
            else:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1
                max_width = section.page_width-Inches(0.2)
                max_height = section.page_height-Inches(0.45)
                ratio = min(max_width/page.rect.width, max_height/page.rect.height)
                p.add_run().add_picture(BytesIO(pix.tobytes('png')), width=int(page.rect.width*ratio), height=int(page.rect.height*ratio))
    doc.save(target)


def pdf_to_docx(pdf: Path, target: Path, record, ocr, scan_word='image'):
    with fitz.open(pdf) as doc:
        text_length = sum(len(p.get_text().strip()) for p in doc)
    if text_length > 80:
        try:
            from pdf2docx import Converter
            converter = Converter(str(pdf))
            try:
                converter.convert(str(target), multi_processing=False)
            finally:
                converter.close()
            return
        except Exception as exc:
            record.warnings.append('PDF 版面转换退回图像保版：'+str(exc)[:180])
    image_docx(pdf, target, ocr, text_mode=scan_word == 'text')
    if scan_word == 'text':
        record.warnings.append('扫描 PDF 已 OCR 转为可编辑文字；公式、图形与表格需要核对')
    else:
        record.warnings.append('扫描 PDF 的 Word 采用整页图像保版；图中文字不能逐字编辑')


def practice_pdf_from_answer(source: Path, target: Path, options, ocr, record):
    """Remove an explicit trailing answer section, or explicit answer blocks."""
    cut = None
    masks = []
    with fitz.open(source) as doc:
        for pi, page in enumerate(doc):
            lines = [(t, fitz.Rect(min(c['bbox'][0] for c in cs), min(c['bbox'][1] for c in cs), max(c['bbox'][2] for c in cs), max(c['bbox'][3] for c in cs))) for t, cs in char_lines(page)]
            if not lines and options.ocr:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                lines = [(text, fitz.Rect(min(x[0] for x in b)/1.5, min(x[1] for x in b)/1.5, max(x[0] for x in b)/1.5, max(x[1] for x in b)/1.5)) for b, text, _ in ocr.read(image)]
            for text, box in lines:
                if ANSWER_HEADING_RE.fullmatch(text.strip()) and (pi > 0 or box.y0 > page.rect.height*.25):
                    cut = (pi, box.y0)
                    break
            if cut:
                break
        if cut:
            pi, y = cut
            if pi == 0 and y < doc[0].rect.height*.3:
                record.warnings.append('输入仅含答案，不能还原完整习题')
            if y < 90 and pi > 0:
                doc.delete_pages(pi, len(doc)-1)
            else:
                doc[pi].add_redact_annot(fitz.Rect(0, y-1, doc[pi].rect.width, doc[pi].rect.height), fill=(1,1,1))
                doc[pi].apply_redactions(images=2, graphics=1)
                if pi+1 < len(doc):
                    doc.delete_pages(pi+1, len(doc)-1)
            doc.save(target, garbage=4, deflate=True)
            return True
    return False
