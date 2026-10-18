from io import BytesIO
from pathlib import Path
import posixpath
import zipfile
from lxml import etree as ET
from PIL import Image
from .rules import MARK_RE, source_edits
from .slide_answers import correct_slide_answers

NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def serialize(root):
    return ET.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)


def relationships(parts, name):
    path = posixpath.join(posixpath.dirname(name), '_rels', posixpath.basename(name)+'.rels')
    if path not in parts:
        return {}
    return {node.get('Id'): posixpath.normpath(posixpath.join(posixpath.dirname(name), node.get('Target', ''))).lstrip('/')
            for node in ET.fromstring(parts[path]) if node.get('TargetMode') != 'External'}


def remove_last_slide(parts, record):
    name = 'ppt/presentation.xml'
    root = ET.fromstring(parts[name])
    slides = root.find('p:sldIdLst', NS)
    if slides is None or len(slides) < 2:
        record.warnings.append('PPT 只有一页，已保留该页并仅清理标识')
        return
    last = slides[-1]
    rid = last.get('{'+NS['r']+'}id')
    slide_id = last.get('id')
    slide_path = relationships(parts, name)[rid]
    removed = {slide_path, posixpath.join(posixpath.dirname(slide_path), '_rels', posixpath.basename(slide_path)+'.rels')}
    for target in relationships(parts, slide_path).values():
        if target.startswith('ppt/notesSlides/notesSlide'):
            removed.add(target)
            removed.add(posixpath.join(posixpath.dirname(target), '_rels', posixpath.basename(target)+'.rels'))
    slides.remove(last)
    for node in list(root.iter()):
        if not isinstance(node.tag, str) or node.getparent() is None:
            continue
        if ((ET.QName(node).localname == 'sld' and node.get('{'+NS['r']+'}id') == rid)
                or (ET.QName(node).localname == 'sldId' and node.get('id') == slide_id)):
            node.getparent().remove(node)
    parts[name] = serialize(root)
    for path in list(parts):
        if path in removed:
            del parts[path]
        elif path.endswith('.rels'):
            rels = ET.fromstring(parts[path])
            owner_directory = posixpath.dirname(posixpath.dirname(path))
            for node in list(rels):
                target = posixpath.normpath(posixpath.join(owner_directory, node.get('Target', ''))).lstrip('/')
                if node.get('TargetMode') != 'External' and target in removed:
                    rels.remove(node)
            parts[path] = serialize(rels)
    content_types = ET.fromstring(parts['[Content_Types].xml'])
    for node in list(content_types):
        if node.get('PartName', '').lstrip('/') in removed:
            content_types.remove(node)
    parts['[Content_Types].xml'] = serialize(content_types)
    if 'docProps/app.xml' in parts:
        app = ET.fromstring(parts['docProps/app.xml'])
        for node in app.iter():
            if isinstance(node.tag, str) and ET.QName(node).localname == 'Slides':
                node.text = str(len(slides))
        parts['docProps/app.xml'] = serialize(app)
    record.actions.append(f'删除 PPT 第{len(slides)+1}页（原最后一页）')


def clean_pptx(source: Path, target: Path, options, record, ocr):
    with zipfile.ZipFile(source) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    if options.remove_last_slide:
        remove_last_slide(parts, record)
    presentation = ET.fromstring(parts['ppt/presentation.xml'])
    size = presentation.find('p:sldSz', NS)
    slide_area = int(size.get('cx'))*int(size.get('cy'))
    logos = set()
    for name in list(parts):
        if not name.startswith(('ppt/slides/', 'ppt/slideMasters/', 'ppt/slideLayouts/')) or not name.endswith('.xml'):
            continue
        root = ET.fromstring(parts[name])
        rels = relationships(parts, name)
        for node in list(root.iter()):
            if not isinstance(node.tag, str):
                continue
            kind = ET.QName(node).localname
            if kind not in ('sp', 'pic'):
                continue
            text = ''.join(node.xpath('.//a:t/text()', namespaces=NS))
            attrs = ' '.join(v for child in node.iter() if isinstance(child.tag, str) for v in child.attrib.values())
            branded = (MARK_RE.search(attrs) or MARK_RE.search(text)) and not MARK_RE.sub('', text).strip()
            if kind == 'pic' and options.ocr and not branded:
                for blip in node.xpath('.//a:blip', namespaces=NS):
                    media = rels.get(blip.get('{'+NS['r']+'}embed'))
                    if not media or media not in parts:
                        continue
                    extent = node.find('.//a:xfrm/a:ext', NS)
                    compact = extent is not None and int(extent.get('cx'))*int(extent.get('cy')) < slide_area*.08
                    if compact and (media in logos or ocr.is_logo(parts[media])):
                        logos.add(media)
                        branded = True
                        break
            if branded and node.getparent() is not None:
                node.getparent().remove(node)
                record.watermark_count += 1
        for p in root.xpath('.//a:p', namespaces=NS):
            nodes = p.xpath('.//a:t', namespaces=NS)
            text = ''.join(t.text or '' for t in nodes)
            edits = source_edits(text, options.source_mode)
            record.source_count += len(edits)
            matches = list(MARK_RE.finditer(text))
            edits.extend((m.start(), m.end(), '') for m in matches)
            record.watermark_count += len(matches)
            for start, end, _ in sorted(edits, reverse=True):
                offset = 0
                for node in nodes:
                    value = node.text or ''
                    right = offset+len(value)
                    if right > start and offset < end:
                        node.text = value[:max(0, start-offset)]+value[min(len(value), end-offset):]
                    offset = right
        parts[name] = serialize(root)
    if options.ocr:
        for name in list(parts):
            if name.startswith('ppt/media/') and name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')) and name not in logos:
                data, count = ocr.clean_image(parts[name])
                if count:
                    image = Image.open(BytesIO(data))
                    buf = BytesIO()
                    image.save(buf, format='JPEG' if name.lower().endswith(('.jpg', '.jpeg')) else image.format or 'PNG')
                    parts[name] = buf.getvalue()
                    record.watermark_count += count
    if options.correct_answers:
        presentation = ET.fromstring(parts['ppt/presentation.xml'])
        rels = relationships(parts, 'ppt/presentation.xml')
        slides = []
        images = {}
        for page,item in enumerate(presentation.findall('p:sldIdLst/p:sldId', NS),1):
            name = rels[item.get('{'+NS['r']+'}id')]
            root = ET.fromstring(parts[name])
            slides.append((page,root))
            if options.ocr:
                media_rels = relationships(parts,name)
                for picture in root.xpath('.//p:pic',namespaces=NS):
                    extent = picture.find('.//a:xfrm/a:ext',NS)
                    if extent is None or int(extent.get('cx'))*int(extent.get('cy')) < slide_area*.12:
                        continue
                    for blip in picture.xpath('.//a:blip',namespaces=NS):
                        media = media_rels.get(blip.get('{'+NS['r']+'}embed'))
                        if media in parts:
                            text = '\n'.join(text for _,text,_ in ocr.recognize_image(parts[media]))
                            images.setdefault(page,[]).append(text)
        correct_slide_answers(slides,record,images)
        for (_,root),item in zip(slides,presentation.findall('p:sldIdLst/p:sldId',NS)):
            parts[rels[item.get('{'+NS['r']+'}id')]] = serialize(root)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items():
            z.writestr(name, content)
