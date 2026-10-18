from pathlib import Path
import pymupdf as fitz
from handout_cleaner.pdf import clean_pdf
from handout_cleaner.models import Options, Record
from handout_cleaner.ocr import OCR
from handout_cleaner.rules import MARK_RE, watermark_spans
import pytest


def test_searchable_pdf_redacts_source_not_question(tmp_path):
    source=tmp_path/'in.pdf';out=tmp_path/'out.pdf'
    d=fitz.open();p=d.new_page()
    p.insert_text((40,80),'1. (2024 Hangzhou mock test) speed 620 g',fontsize=12)
    p.insert_text((40,140),'1.（2024年临平区一模）某物体质量620克。',fontname='china-s',fontsize=12)
    p.insert_text((200,240),'微信公众号：浙考神墙620',fontname='china-s',fontsize=14)
    d.save(source);d.close()
    r=Record(str(source))
    clean_pdf(source,out,Options(ocr=False),r,OCR())
    with fitz.open(out) as d:text=d[0].get_text()
    assert '临平' not in text and '浙考' not in text
    assert '620' in text and '某物体' in text
    assert r.watermark_count and r.source_count


def test_pdf_year_mode_keeps_location(tmp_path):
    source=tmp_path/'in.pdf';out=tmp_path/'out.pdf'
    d=fitz.open();p=d.new_page();p.insert_text((40,140),'1.（2024年临平区一模）题目',fontname='china-s',fontsize=12);d.save(source);d.close()
    clean_pdf(source,out,Options(ocr=False,source_mode='year'),Record(str(source)),OCR())
    with fitz.open(out) as d:text=d[0].get_text()
    assert '2024' not in text and '临平区一模' in text and '题目' in text


@pytest.mark.parametrize('mark',['浙考神墙620','微信公众号：浙考神墙620','欢迎关注公众号：浙考神墙620','欢迎关注微信公众号：浙考神墙620'])
def test_complete_watermark_phrase(tmp_path,mark):
    source=tmp_path/'in.pdf';out=tmp_path/'out.pdf'
    d=fitz.open();p=d.new_page()
    p.insert_text((40,100),mark,fontname='china-s',fontsize=14)
    p.insert_text((40,150),'质量620克，公众号是传播渠道。',fontname='china-s',fontsize=12)
    d.save(source);d.close()
    clean_pdf(source,out,Options(ocr=False),Record(str(source)),OCR())
    with fitz.open(out) as d:text=d[0].get_text()
    assert '欢迎' not in text and '浙考' not in text
    assert '质量620克' in text and '公众号是传播渠道' in text


def test_split_ocr_prefix_and_distant_unrelated_prefix():
    lines=[('欢迎关注公众号：',(20,20,200,45)),('浙考神墙620',(205,20,350,45)),('欢迎关注公众号：',(20,600,200,625)),('质量620克',(20,100,180,125))]
    assert watermark_spans(lines)==[[(0,8)],[(0,7)],[],[]]
