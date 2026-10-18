import argparse
from pathlib import Path
from io import BytesIO
import shutil
import zipfile
import pymupdf as fitz
from docx import Document

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'fixtures'
OUT.mkdir(parents=True,exist_ok=True)

def word_pair():
    for answer in (True,False):
        d=Document()
        d.add_heading('第2节 物质的导电性'+('（解析版）' if answer else '（原卷版）'),0)
        d.sections[0].header.paragraphs[0].text='学科网 · 上好课 www.zxxk.com'
        d.sections[0].footer.paragraphs[0].text='微信公众号：浙考神墙620'
        d.add_paragraph('1．（2024年临平区一模）下列物质中，通常情况下属于导体的是（    ）。')
        d.add_paragraph('A.铜丝    B.玻璃    C.橡胶    D.陶瓷')
        if answer:
            d.add_paragraph('【答案】B')
            d.add_paragraph('【解析】铜丝中存在大量可以自由移动的电荷，故选A。')
        d.add_paragraph('2．（2023·浙江杭州·中考）某实验从2024年开始记录。请比较两组数据。')
        table=d.add_table(rows=3, cols=3)
        for row,values in zip(table.rows,[['组别','电压 / V','电流 / A'],['甲','2','0.2'],['乙','4','0.4']]):
            for cell,text in zip(row.cells,values):cell.text=text
        if answer:
            d.add_paragraph('【答案】电阻相同')
            d.add_paragraph('【解析】根据 R=U/I，甲乙两组电阻均为10欧姆。')
        name='第2节 物质的导电性（分层作业）'+('（解析版）' if answer else '（原卷版）')+'科学浙教版2024八年级上册.docx'
        d.save(OUT/name)
    inner=BytesIO()
    with zipfile.ZipFile(inner,'w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.glob('*.docx'):z.write(p,'分层作业/'+p.name)
    with zipfile.ZipFile(OUT/'学科网测试包.zip','w',zipfile.ZIP_DEFLATED) as z:z.writestr('第一章/导电性作业.zip',inner.getvalue())

def scanned():
    source=fitz.open();p=source.new_page(width=595,height=842)
    for x,y,text,size in [(40,55,'科学复习试卷',20),(40,130,'1．（2024年临平区一模）下列实验操作正确的是',13),(40,170,'A．测量长度   B．测量温度   C．测量电流',13),(140,250,'微信公众号：浙考神墙620',15),(40,350,'2．某物体的质量为620克，求其密度。',13)]:
        p.insert_text((x,y),text,fontname='china-s',fontsize=size)
    pix=p.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
    out=fitz.open();page=out.new_page(width=595,height=842);page.insert_image(page.rect,stream=pix.tobytes('png'))
    out.save(OUT/'浙考神墙扫描测试.pdf');out.close();source.close()

def local_examples(archive=None, original=None):
    if archive:
        shutil.copy2(archive,OUT/'真实学科网样例.zip')
    if original:
        with fitz.open(original) as source:
            out=fitz.open();out.insert_pdf(source,from_page=0,to_page=1)
            out.save(OUT/'真实浙考神墙样例-前两页.pdf');out.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Generate synthetic, shareable test documents.')
    parser.add_argument('--sample-archive',type=Path,help='Optional ZIP to copy into ignored local fixtures.')
    parser.add_argument('--sample-pdf',type=Path,help='Optional PDF to excerpt into ignored local fixtures.')
    args=parser.parse_args()
    word_pair();scanned();local_examples(args.sample_archive,args.sample_pdf)
    print(OUT)
