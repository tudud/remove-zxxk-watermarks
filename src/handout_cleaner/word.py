import re
import zipfile
from pathlib import Path
from lxml import etree as ET
from .rules import (MARK_RE, source_edits, ANSWER_MARK_RE, ANSWER_HEADING_RE, QUESTION_RE,
                    KEY_RE, normalized_choice, answer_conclusion)

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'w': W, 'r': R}


def text_of(p):
    return ''.join(p.itertext()) if isinstance(p, str) else ''.join(t.text or '' for t in p.iter('{'+W+'}t'))


def replace_range(p, start: int, end: int, value=''):
    nodes = list(p.iter('{'+W+'}t'))
    offset = 0
    replacements = []
    for node in nodes:
        text = node.text or ''
        node_end = offset+len(text)
        if node_end > start and offset < end:
            left, right = max(start-offset, 0), min(end-offset, len(text))
            replacements.append((node, text[:left]+(value if offset <= start else '')+text[right:]))
        offset = node_end
    for node, text in replacements:
        node.text = text
        node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')


def serialize(root):
    return ET.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)


def rebuild_margins(parts, root):
    for name in list(parts):
        if re.fullmatch(r'word/(?:header|footer)\d+\.xml', name):
            kind = 'hdr' if '/header' in name else 'ftr'
            empty = ET.Element('{'+W+'}'+kind, nsmap={'w': W})
            ET.SubElement(empty, '{'+W+'}p')
            parts[name] = serialize(empty)
    rels = ET.fromstring(parts['word/_rels/document.xml.rels'])
    content = ET.fromstring(parts['[Content_Types].xml'])
    ids = {r.get('Id') for r in rels}
    rid = 'rIdCleanerPage'
    while rid in ids:
        rid += '1'
    filename = 'cleaner-footer.xml'
    ET.SubElement(rels, '{'+REL+'}Relationship', Id=rid, Type=R+'/footer', Target=filename)
    if not any(x.get('PartName') == '/word/'+filename for x in content):
        ET.SubElement(content, '{'+CT+'}Override', PartName='/word/'+filename, ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml')
    footer = ET.fromstring(f'<w:ftr xmlns:w="{W}"><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>'.encode())
    parts['word/'+filename] = serialize(footer)
    for section in root.iter('{'+W+'}sectPr'):
        for ref in list(section):
            if ref.tag == '{'+W+'}footerReference':
                section.remove(ref)
        for typ in ('default', 'first', 'even'):
            ref = ET.Element('{'+W+'}footerReference')
            ref.set('{'+W+'}type', typ)
            ref.set('{'+R+'}id', rid)
            section.insert(0, ref)
    parts['word/_rels/document.xml.rels'] = serialize(rels)
    parts['[Content_Types].xml'] = serialize(content)


def correct_answer_keys(paragraphs, record):
    groups = []
    current = []
    number = None
    for p in paragraphs:
        text = text_of(p)
        q = QUESTION_RE.match(text)
        if q:
            if current:
                groups.append((number, current))
            number, current = q.group(1), []
        current.append(p)
    if current:
        groups.append((number, current))
    conclusions = {}
    for number, block in groups:
        if not number:
            continue
        final, evidence, conflict = answer_conclusion([text_of(p) for p in block])
        if conflict:
            record.warnings.append(f'第{number}题解析结论有多个不同选项，未自动修改')
            continue
        if not final:
            continue
        if number in conclusions and conclusions[number] != final:
            conclusions[number] = None
        else:
            conclusions[number] = final
        keys = [(p, m.start(1), m.end(1), m.group(1)) for p in block for m in KEY_RE.finditer(text_of(p))]
        for p, start, end, original in reversed(keys):
            if normalized_choice(original) != final:
                replace_range(p, start, end, final)
                record.changes.append({'question': number, 'before': original, 'after': final, 'evidence': evidence})
    # Answer tables / short answer lists are handled only by an explicit number.
    after_heading = False
    for p in paragraphs:
        text = text_of(p)
        if ANSWER_HEADING_RE.fullmatch(text):
            after_heading = True
            continue
        if not after_heading:
            continue
        for match in reversed(list(re.finditer(r'(?:^|\s)(\d{1,3})\s*[.．、]\s*([A-DＡ-Ｄ]+)(?=\s|[。;；]|$)', text))):
            number, old = match.group(1), match.group(2)
            final = conclusions.get(number)
            if final and normalized_choice(old) != final:
                replace_range(p, match.start(2), match.end(2), final)
                record.changes.append({'question': number, 'before': old, 'after': final, 'evidence': '同题解析明确的最终选项'})


def strip_answers(root, record):
    body = root.find('w:body', NS)
    paragraphs = list(body.iter('{'+W+'}p'))
    removed = 0
    answer_section = False
    in_explanation = False
    section_heading = re.compile(r'^\s*[一二三四五六七八九十]+\s*[、．.]\s*\S')
    for p in paragraphs:
        text = text_of(p)
        if ANSWER_HEADING_RE.fullmatch(text) and paragraphs.index(p) > 1:
            answer_section = True
        question = QUESTION_RE.match(text)
        automatic_numbering = p.find('w:pPr/w:numPr', NS) is not None
        if (question or automatic_numbering or section_heading.match(text)) and not answer_section:
            in_explanation = False
        marker = ANSWER_MARK_RE.search(text)
        if answer_section or in_explanation:
            parent = p.getparent()
            if parent is not None:
                parent.remove(p)
                removed += 1
            continue
        if marker:
            if marker.start() == 0 or not text[:marker.start()].strip():
                parent = p.getparent()
                parent.remove(p)
            else:
                replace_range(p, marker.start(), len(text), '')
            in_explanation = True
            removed += 1
        elif question:
            for m in reversed(list(re.finditer(r'[（(]\s*[A-DＡ-Ｄ]{1,4}\s*[）)]', text))):
                replace_range(p, m.start()+1, m.end()-1, '    ')
    # Every retained cell needs a paragraph, even after its answer was removed.
    for cell in root.iter('{'+W+'}tc'):
        if cell.find('w:p', NS) is None:
            ET.SubElement(cell, '{'+W+'}p')
    # Empty table rows and answer-only tables should not leave large grid remnants.
    for table in list(root.iter('{'+W+'}tbl')):
        if not text_of(table).strip() and not table.findall('.//w:drawing', NS):
            parent = table.getparent()
            if parent is not None:
                parent.remove(table)
    if not removed:
        record.warnings.append('未找到独立答案段落；习题副本保留原有题目，请核对是否有未标记的行内答案')
    return removed


def clean_docx(source: Path, target: Path, options, record, ocr=None, practice=False, remove_answers=False):
    with zipfile.ZipFile(source) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    root = ET.fromstring(parts['word/document.xml'])
    rebuild_margins(parts, root)
    paragraphs = list(root.iter('{'+W+'}p'))
    for index, p in enumerate(paragraphs):
        text = text_of(p)
        edits = source_edits(text, options.source_mode)
        record.source_count += len(edits)
        edits += [(m.start(), m.end(), '') for m in MARK_RE.finditer(text)]
        record.watermark_count += len(list(MARK_RE.finditer(text)))
        if practice and index < 15:
            edits += [(m.start(), m.end(), '') for m in re.finditer(r'[（(]\s*(?:解析版|原卷版|学生版)\s*[）)]', text)]
        for start, end, value in sorted(edits, reverse=True):
            replace_range(p, start, end, value)
    # Watermark text boxes and drawings carrying platform metadata.
    for node in list(root.iter()):
        if not isinstance(node.tag, str):
            continue
        if ET.QName(node).localname in ('drawing', 'pict'):
            metadata = ' '.join(node.itertext()) + ' ' + ' '.join(str(v) for x in node.iter() for v in x.attrib.values())
            if MARK_RE.search(metadata):
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
                    record.watermark_count += 1
    if options.correct_answers and not practice:
        correct_answer_keys(paragraphs, record)
    if remove_answers:
        strip_answers(root, record)
    if options.ocr and ocr:
        for name in list(parts):
            if re.match(r'word/media/.+\.(png|jpe?g|bmp|tiff?)$', name, re.I):
                cleaned, count = ocr.clean_image(parts[name])
                if count:
                    # Preserve original media codec: Word uses its content type.
                    from PIL import Image
                    from io import BytesIO
                    img = Image.open(BytesIO(cleaned))
                    buf = BytesIO()
                    fmt = 'JPEG' if name.lower().endswith(('.jpg', '.jpeg')) else 'PNG'
                    img.save(buf, format=fmt)
                    parts[name] = buf.getvalue()
                    record.watermark_count += count
    parts['word/document.xml'] = serialize(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items():
            z.writestr(name, content)
    return target


def has_answers(path: Path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    text = '\n'.join(text_of(p) for p in root.iter('{'+W+'}p'))
    return bool(ANSWER_MARK_RE.search(text) or any(ANSWER_HEADING_RE.fullmatch(s) for s in text.splitlines()))


def answer_template(path: Path, title: str):
    from docx import Document
    from docx.shared import Pt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Microsoft YaHei'
    style.font.size = Pt(11)
    doc.add_heading(title+'（答案）', 0)
    doc.add_paragraph('待补充答案：输入资料未包含可识别的参考答案或解析，本文件是答案模板。')
    p = doc.sections[0].footer.paragraphs[0]
    p.alignment = 1
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), ' PAGE ')
    p._p.append(field)
    doc.save(path)
