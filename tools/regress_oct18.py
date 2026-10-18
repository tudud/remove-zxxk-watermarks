"""Reproduce the user's real slide-logo and scanned PDF regressions."""
import json
import hashlib
from pathlib import Path
import zipfile
import pymupdf as fitz
from pptx import Presentation
from handout_cleaner.models import Options, Record
from handout_cleaner.ocr import OCR
from handout_cleaner.rules import clean_name
from handout_cleaner.slides import clean_pptx
from handout_cleaner.convert import convert_office


def main():
    home=Path.home()
    output=home/'Desktop'/'讲义净化-1.0.1修正验证'
    output.mkdir(exist_ok=True)
    inputs=Path('artifacts/patch-qa/real-inputs');inputs.mkdir(exist_ok=True)
    archive=home/'Downloads'/'【上好课】九年级科学上册同步备课系列（新教材浙教版）-2.zip'
    engine=OCR();records=[]
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if not info.filename.lower().endswith('.pptx'):continue
            name=info.filename
            if not info.flag_bits & 0x800:
                try:name=name.encode('cp437').decode('gb18030')
                except (UnicodeError,LookupError):pass
            name=Path(name).name
            source=inputs/name;source.write_bytes(z.read(info))
            target=output/(clean_name(name,ppt=True)+'.pptx')
            record=Record(str(source))
            if not target.exists():
                clean_pptx(source,target,Options(),record,engine)
            else:
                record.actions.append('复核已处理课件的页数和 Logo 对象')
            before,after=Presentation(source),Presentation(target)
            assert len(after.slides)==len(before.slides)-1
            logo_hash=hashlib.sha1(Path('artifacts/patch-qa/logo.png').read_bytes()).hexdigest()
            assert not any(s.shape_type==13 and s.image.sha1==logo_hash for slide in after.slides for s in slide.shapes)
            record.status='完成';record.outputs=[str(target)];records.append(record.to_dict())
            print(json.dumps({'name':target.name,'slides_before':len(before.slides),'slides_after':len(after.slides),'logos':record.watermark_count},ensure_ascii=True),flush=True)
    target=output/'4.1 生命的起源.pptx'
    rendered=convert_office(target,Path('artifacts/patch-qa/rendered'),'pdf:impress_pdf_Export')
    with fitz.open(rendered) as d:
        for i in (0,len(d)//2,len(d)-1):d[i].get_pixmap(matrix=fitz.Matrix(1,1)).save(f'artifacts/patch-qa/slide-after-{i+1}.png')
    (output/'课件修正记录.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
