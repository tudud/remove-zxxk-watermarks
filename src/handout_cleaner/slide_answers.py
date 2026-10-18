"""Conservative, format-preserving answer checks for editable slide text."""
from dataclasses import dataclass, field
import re
from .rules import (QUESTION_RE, KEY_RE, CONCLUSION_RE, ANSWER_MARK_RE,
                    ANSWER_HEADING_RE, normalized_choice, answer_conclusion)

NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
EXAMPLE_RE = re.compile(r'^\s*[【\[]?\s*(?:典例|例题|例|变式(?:训练)?|练习)\s*([0-9一二三四五六七八九十]+)?\s*[】\].．、:：]?')
CHOICES = r'[A-DＡ-Ｄ](?:\s*[、,，和及]?\s*[A-DＡ-Ｄ]){0,3}'
INLINE_RE = re.compile(r'[（(]\s*('+CHOICES+r')\s*[）)]\s*[。？?]?\s*$')
BLANK_RE = re.compile(r'[（(]\s*[）)]\s*[。？?]?\s*$')
BARE_RE = re.compile(r'^\s*('+CHOICES+r')\s*$')
CHOICE_CUE_RE = re.compile(r'(?:是|为|选|有|规律|选项|结论|顺序|结果|关系|做法|说法|现象|原因)[^（）()\n]{0,12}$')
SUMMARY_RE = re.compile(r'(?:^|\s)(\d{1,3})\s*[.．、]\s*('+CHOICES+r')(?=\s|[。;；]|$)')


@dataclass
class Line:
    paragraph: object
    shape: object
    index: int
    page: int
    rect: tuple
    text: str


@dataclass
class Question:
    number: str
    anchor: Line
    lines: list = field(default_factory=list)


def shape_rect(shape):
    transform = shape.find('p:spPr/a:xfrm', NS)
    if transform is None:
        transform = shape.find('p:xfrm', NS)
    if transform is None:
        return (0., 0., 1., 1.)
    off, ext = transform.find('a:off', NS), transform.find('a:ext', NS)
    if off is None or ext is None:
        return (0., 0., 1., 1.)
    x, y, w, h = (float(off.get('x')), float(off.get('y')), float(ext.get('cx')), float(ext.get('cy')))
    for parent in shape.iterancestors():
        if parent.tag != '{'+NS['p']+'}grpSp':
            continue
        group = parent.find('p:grpSpPr/a:xfrm', NS)
        if group is None:
            continue
        go, ge, co, ce = [group.find('a:'+tag, NS) for tag in ('off','ext','chOff','chExt')]
        if any(v is None for v in (go,ge,co,ce)):
            continue
        sx, sy = float(ge.get('cx'))/max(1,float(ce.get('cx'))), float(ge.get('cy'))/max(1,float(ce.get('cy')))
        x, y = float(go.get('x'))+(x-float(co.get('x')))*sx, float(go.get('y'))+(y-float(co.get('y')))*sy
        w, h = w*sx, h*sy
    return x, y, w, h


def slide_lines(root, page):
    lines = []
    for shape in root.xpath('.//p:sp|.//p:graphicFrame', namespaces=NS):
        x,y,w,h = shape_rect(shape)
        paragraphs = shape.xpath('.//a:p', namespaces=NS)
        for index,p in enumerate(paragraphs):
            text = ''.join(p.xpath('.//a:t/text()', namespaces=NS))
            if text.strip():
                lines.append(Line(p,shape,index,page,(x,y+h*index/max(1,len(paragraphs)),w,h/max(1,len(paragraphs))),text))
    return sorted(lines,key=lambda line:(line.rect[1],line.rect[0],line.index))


def question_number(text):
    match = EXAMPLE_RE.match(text)
    if match:
        return match.group(1) or '未编号'
    match = QUESTION_RE.match(text)
    if match and not BARE_RE.fullmatch(text[match.end():]):
        return match.group(1)
    return None


def replace_range(paragraph, start, end, value):
    offset = 0
    for node in paragraph.xpath('.//a:t',namespaces=NS):
        text = node.text or ''
        right = offset+len(text)
        if right > start and offset < end:
            node.text = text[:max(0,start-offset)]+(value if offset <= start else '')+text[min(len(text),end-offset):]
        offset = right


def joined(lines):
    text, mapping = '', []
    for line in lines:
        mapping.append((len(text),len(text)+len(line.text),line))
        text += line.text+'\n'
    return text,mapping


def is_red(line):
    for color in line.paragraph.xpath('.//a:srgbClr/@val',namespaces=NS):
        if len(color)==6:
            r,g,b = (int(color[i:i+2],16) for i in (0,2,4))
            if r >= 150 and r-g > 60 and r-b > 60:
                return True
    return False


def answer_overlay(line, anchor):
    if line.page!=anchor.page or not BARE_RE.fullmatch(line.text) or not BLANK_RE.search(anchor.text) or not is_red(line):
        return False
    x,y,w,h = line.rect
    ax,ay,aw,ah = anchor.rect
    return ax+aw*.45 <= x+w/2 <= ax+aw+max(w,aw*.02) and ay-h*.5 <= y <= ay+max(h,ah)*1.5


def reference_ranges(question, text, mapping):
    ranges = {(m.start(1),m.end(1)) for m in KEY_RE.finditer(text)}
    anchor = question.anchor
    for start,_,line in mapping:
        if line is anchor:
            match = INLINE_RE.search(line.text)
            if match and CHOICE_CUE_RE.search(line.text[:match.start()]):
                ranges.add((start+match.start(1),start+match.end(1)))
        elif answer_overlay(line,anchor):
            match = BARE_RE.fullmatch(line.text)
            ranges.add((start+match.start(1),start+match.end(1)))
    return sorted(ranges)


def assign_lines(lines, anchors):
    for line in lines:
        overlays = [q for q in anchors if answer_overlay(line,q.anchor)]
        if len(overlays)==1:
            overlays[0].lines.append(line)
            continue
        same = [q for q in anchors if q.anchor.shape is line.shape and q.anchor.index<=line.index]
        if same:
            owner = max(same,key=lambda q:q.anchor.index)
        else:
            eligible = [q for q in anchors if q.anchor.rect[1] <= line.rect[1]+max(line.rect[3],q.anchor.rect[3])*.6]
            if not eligible:
                continue
            # Separate columns first; then use the nearest preceding question.
            distance = lambda q:abs(q.anchor.rect[0]-line.rect[0])
            nearest = min(distance(q) for q in eligible)
            column = [q for q in eligible if distance(q) <= nearest+q.anchor.rect[2]*.2]
            owner = max(column,key=lambda q:q.anchor.rect[1])
        owner.lines.append(line)


def correct_slide_answers(slides, record, image_texts=None):
    questions, summaries, carry = [], [], None
    pending = {}
    reviewed = 0
    initial_changes = len(record.changes)
    for page,root in slides:
        lines = slide_lines(root,page)
        summary = any(ANSWER_HEADING_RE.fullmatch(line.text.strip()) for line in lines)
        anchors = [Question(number,line) for line in lines if (number:=question_number(line.text))]
        if summary and not anchors:
            summaries.extend(lines)
            carry = None
        elif anchors:
            assign_lines(lines,anchors)
            questions.extend(anchors)
            carry = anchors[0] if len(anchors)==1 else None
        elif carry is not None and any(ANSWER_MARK_RE.search(line.text) for line in lines):
            carry.lines.extend(lines)
        else:
            carry = None
        if image_texts and page in image_texts:
            for text in image_texts[page]:
                if KEY_RE.search(text) or CONCLUSION_RE.search(text) or EXAMPLE_RE.search(text):
                    record.warnings.append(f'第{page}页含图片形式的例题或解析，图片内答案未自动修改，请人工核对')
                    break

    def schedule(lines, text, mapping, ranges, final, evidence, number):
        nonlocal reviewed
        for start,end in ranges:
            reviewed += 1
            old = text[start:end]
            if normalized_choice(old)==final:
                continue
            key_page = None
            for left,right,line in mapping:
                if right>start and left<end:
                    pending.setdefault(line.paragraph,[]).append((max(0,start-left),min(len(line.text),end-left),final if left<=start else ''))
                    key_page = key_page or line.page
            record.changes.append({'question':number,'slide':key_page,'before':old,'after':final,'evidence':evidence})

    conclusions = {}
    for question in questions:
        text,mapping = joined(question.lines)
        ranges = reference_ranges(question,text,mapping)
        final,evidence,conflict = answer_conclusion([text])
        label = f'第{question.anchor.page}页第{question.number}题'
        conclusions.setdefault(question.number,[]).append((final,evidence))
        if conflict:
            record.warnings.append(label+'解析结论有多个不同选项，未自动修改')
        elif ranges and not final:
            record.warnings.append(label+'未找到明确的最终选项结论，参考答案未修改')
        elif ranges and final:
            schedule(question.lines,text,mapping,ranges,final,evidence,question.number)
        elif final:
            record.warnings.append(label+'未识别出可编辑的参考答案，未自动填入答案')

    for line in summaries:
        for match in SUMMARY_RE.finditer(line.text):
            number = match.group(1)
            candidates = conclusions.get(number,[])
            if len(candidates)==1 and candidates[0][0]:
                final,evidence = candidates[0]
                schedule([line],line.text,[(0,len(line.text),line)],[(match.start(2),match.end(2))],final,evidence,number)
            elif candidates:
                record.warnings.append(f'第{line.page}页答案汇总第{number}题无法唯一关联到解析，未自动修改')
    for paragraph,edits in pending.items():
        for start,end,value in sorted(set(edits),reverse=True):
            replace_range(paragraph,start,end,value)
    if questions:
        record.actions.append(f'PPT 答案核对：识别 {len(questions)} 个题号/例题标记，依据明确解析核对 {reviewed} 个参考答案，修正 {len(record.changes)-initial_changes} 处')
