from pathlib import Path
import zipfile
import pymupdf as fitz
from docx import Document
from handout_cleaner.models import Options
from handout_cleaner.pipeline import Processor


def make_pdf(path, pages=1):
    with fitz.open() as doc:
        for _ in range(pages):
            page=doc.new_page()
            page.insert_text((40,80),'欢迎关注公众号：浙考神墙620',fontname='china-s',fontsize=12)
            page.insert_text((40,150),'参考答案：B。质量620克。',fontname='china-s',fontsize=12)
        doc.save(path)


def test_pdf_pair_only_outputs_two_pdfs_without_conversion(tmp_path,monkeypatch):
    import handout_cleaner.pipeline as pipeline
    def forbidden(*args,**kwargs):raise AssertionError('PDF must not use Office or create Word')
    monkeypatch.setattr(pipeline,'convert_office',forbidden)
    a=tmp_path/'练习（原卷版）.pdf';b=tmp_path/'练习（解析版）.pdf'
    make_pdf(a,2);make_pdf(b,2)
    out=tmp_path/'out'
    records=Processor(Options(ocr=False)).run([a,b],out)
    assert len(records)==2 and all(r.status=='完成' and len(r.outputs)==1 for r in records)
    assert not list(out.rglob('*.docx'))
    assert {Path(r.outputs[0]).name for r in records}=={'练习.pdf','练习（答案）.pdf'}
    for r in records:
        with fitz.open(r.outputs[0]) as doc:
            assert len(doc)==2
            text=''.join(p.get_text() for p in doc)
            assert '浙考' not in text and '欢迎关注' not in text
            assert '参考答案：B' in text and '质量620克' in text


def test_archive_same_title_word_and_pdf_remain_independent(tmp_path,monkeypatch):
    import handout_cleaner.pipeline as pipeline
    def convert(source,output,fmt):
        target=output/(source.stem+'.pdf');make_pdf(target);return target
    monkeypatch.setattr(pipeline,'convert_office',convert)
    pdf=tmp_path/'练习.pdf';make_pdf(pdf)
    word=tmp_path/'练习.docx';doc=Document();doc.add_paragraph('1．质量620克。');doc.save(word)
    archive=tmp_path/'资料.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.write(pdf,pdf.name);z.write(word,word.name)
    records=Processor(Options(ocr=False)).run([archive],tmp_path/'out')
    assert len(records)==2 and all(r.status!='失败' for r in records)
    assert sorted(len(r.outputs) for r in records)==[1,3]
    pdf_record=next(r for r in records if r.source.endswith('.pdf'))
    assert Path(pdf_record.outputs[0]).suffix=='.pdf'


def test_same_normalized_pdf_names_are_not_dropped(tmp_path):
    a=tmp_path/'练习（原卷版）.pdf';b=tmp_path/'练习（分层作业）.pdf'
    make_pdf(a);make_pdf(b)
    records=Processor(Options(ocr=False)).run([a,b],tmp_path/'out')
    assert len(records)==2 and all(len(r.outputs)==1 for r in records)
    assert records[0].outputs[0]!=records[1].outputs[0]
