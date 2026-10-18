import json
from pathlib import Path
import pymupdf as fitz
from PIL import Image
from docx import Document
from handout_cleaner.ocr import OCR
from handout_cleaner.rules import MARK_RE

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'artifacts'/'qa'
QA.mkdir(exist_ok=True)

def main():
    result={}
    for folder in ['word-verified','real-word-verified','pdf-verified']:
        root=ROOT/'artifacts'/folder
        report=root/'处理报告.json'
        if not report.exists():
            result[folder]={'missing_report':True}
            continue
        data=json.loads(report.read_text(encoding='utf-8'))
        result[folder]={'statuses':[r['status'] for r in data['records']], 'warnings':[r['warnings'] for r in data['records']], 'corrections':[r['changes'] for r in data['records']]}
        for pdf in root.glob('*.pdf'):
            with fitz.open(pdf) as doc:
                pages=len(doc)
                texts='\n'.join(p.get_text() for p in doc)
                image=doc[0].get_pixmap(matrix=fitz.Matrix(1.2,1.2),alpha=False)
                image.save(QA/(pdf.stem+'.png'))
                result[folder][pdf.name]={'pages':pages,'watermarks':bool(MARK_RE.search(texts))}
    scan=ROOT/'artifacts/pdf-verified/浙考神墙扫描测试.pdf'
    if scan.exists():
        with fitz.open(scan) as d:
            pix=d[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            text='\n'.join(t for b,t,s in OCR().read(Image.frombytes('RGB',(pix.width,pix.height),pix.samples)))
        result['scan_ocr']={'watermark_absent':not MARK_RE.search(text),'source_absent':'临平' not in text,'numeric_620_retained':'620' in text,'text':text}
    (ROOT/'artifacts/verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
