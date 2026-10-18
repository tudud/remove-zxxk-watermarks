import re

CHANNEL = r"浙\s*考\s*神\s*[墙墻](?:\s*620)?"
PROMO = r"(?:(?:欢\s*迎|敬\s*请|请)\s*)?(?:关\s*注\s*)?(?:微\s*信\s*)?公\s*众\s*[号器]\s*[:：]?\s*"
MARK_RE = re.compile(r"学\s*科\s*网|(?:www\s*[.．]\s*)?zxxk\s*[.．]\s*com|上\s*好\s*课|(?:" + PROMO + r")?" + CHANNEL, re.I)
PROMO_FRAGMENT_RE = re.compile(r"(?:" + PROMO + r"|(?:欢\s*迎\s*)?关\s*注\s*[:：]?)")


def watermark_spans(lines):
    """Associate separate OCR/text prefix boxes only with a nearby channel mark."""
    spans = [[(m.start(), m.end()) for m in MARK_RE.finditer(text)] for text, _ in lines]
    anchors = [i for i, (text, _) in enumerate(lines) if re.search(CHANNEL, text)]
    prefixes = [i for i, (text, _) in enumerate(lines) if PROMO_FRAGMENT_RE.fullmatch(text.strip())]
    for _ in range(2):
        added = []
        for i in prefixes:
            if spans[i]:
                continue
            a = lines[i][1]
            for j in anchors:
                b = lines[j][1]
                height = max(a[3]-a[1], b[3]-b[1], 1)
                same_row = abs((a[1]+a[3]-b[1]-b[3])/2) < height*.7
                horizontal_gap = max(a[0]-b[2], b[0]-a[2], 0)
                vertical_gap = max(a[1]-b[3], b[1]-a[3], 0)
                overlap = min(a[2], b[2])-max(a[0], b[0])
                if (same_row and horizontal_gap < height*3) or (vertical_gap < height*1.2 and overlap > 0):
                    spans[i] = [(0, len(lines[i][0]))]
                    added.append(i)
                    break
        anchors.extend(added)
    return spans
EXAM = r"(?:一模|二模|三模|中考|期中|期末|模拟|统考|联考|月考|调研|适应性|学业(?:水平|考试)|质检|测试|考试|校考|竞赛|真题)"
SOURCE_RE = re.compile(r"[（(【\[]\s*(?:20\d{2}(?:\s*[-—–~至]\s*20\d{2})?\s*(?:学年|年)?\s*[·•・,，:：—–-]?\s*)?[^（）()【】\[\]\r\n]{0,36}?" + EXAM + r"[^（）()【】\[\]\r\n]{0,12}[）)】\]]")
YEAR_RE = re.compile(r"20\d{2}(?:\s*[-—–~至]\s*20\d{2})?\s*(?:学年|年)?\s*(?:[·•・,，:：—–-]\s*)?")
QUESTION_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、](?!\d)")
PREFIX_RE = re.compile(r"^\s*(?:(?:第?\s*\d{1,3}\s*[.．、:：)）题]?|[①②③④⑤⑥⑦⑧⑨⑩])\s*)?(?:[（(]\s*\d+\s*分\s*[）)]\s*)?(?:[★☆※]\s*)?$")
EDITION_RE = re.compile(r"[（(]\s*(?:原卷版|解析版|学生版|答案|参考答案|答案及评分标准|全解全析)\s*[）)]|(?:原卷版|解析版|参考答案|答案及评分标准|全解全析)\s*$")
ANSWER_MARK_RE = re.compile(r"【(?:答案|分析|解析|解答|详解|点睛)】|(?:^|\s)(?:答案|解析|详解)\s*[:：]")
ANSWER_HEADING_RE = re.compile(r"^\s*(?:参考答案(?:及解析|与解析)?|答案(?:与解析|及解析|解析)?|试题答案|参考解析)\s*[:：]?\s*$")
CONCLUSION_RE = re.compile(r"(?:故\s*(?:选|答案(?:为|是)?)|因此\s*(?:选|选择|答案(?:为|是))|所以\s*(?:选|选择)|正确(?:答案|选项)(?:为|是))\s*[:：]?[\s（(]*([A-DＡ-Ｄ](?:\s*[、,，和及]?\s*[A-DＡ-Ｄ]){0,3})(?=[\s。．.;；）)\r\n]|$)", re.I)
KEY_RE = re.compile(r"(?:【答案】|(?:参考答案|答案)\s*[:：])\s*([A-DＡ-Ｄ](?:\s*[、,，和及]?\s*[A-DＡ-Ｄ]){0,3})(?=[\s。．.;；）)【\r\n]|$)", re.I)


def source_edits(text: str, mode: str = "all") -> list[tuple[int, int, str]]:
    edits = []
    for match in SOURCE_RE.finditer(text):
        if match.start() > 40 or not PREFIX_RE.fullmatch(text[:match.start()]):
            continue
        if not text[:match.start()].strip() and not re.search(r'20\d{2}|省|市|区|县|[·•]', match.group()):
            continue
        if mode == "keep":
            continue
        if mode == "year":
            year = YEAR_RE.search(match.group())
            if year:
                edits.append((match.start()+year.start(), match.start()+year.end(), ""))
        else:
            end = match.end()
            while end < len(text) and text[end] in " \t\u3000":
                end += 1
            edits.append((match.start(), end, ""))
    return edits


def apply_edits(text, edits):
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    return text


def edition(name: str) -> str:
    if re.search(r"解析版|参考答案|答案及评分标准|全解全析|[（(]\s*答案\s*[）)]|答案[\s.]*$", name):
        return "answer"
    if re.search(r"原卷版|学生版", name):
        return "practice"
    return "standard"


def clean_name(name: str, ppt=False) -> str:
    name = re.sub(r"\.(?:docx?|pdf|pptx?)$", "", name, flags=re.I)
    name = EDITION_RE.sub("", name)
    name = re.sub(r"[（(](?:教学课件|分层作业|分层练习|专项训练)[）)]", "", name)
    name = re.sub(r"20\d{2}\s*[-—–]\s*20\d{2}\s*学年", "", name)
    name = re.sub(r"科学(?:新教材)?(?:浙教版|人教版|教科版|华师大版)?(?:20\d{2})?[一二三四五六七八九十\d]+年级[上下]册", "", name)
    name = re.sub(r"(?:浙教版|人教版|教科版|华师大版)(?:20\d{2})?|[一二三四五六七八九十\d]+年级[上下]册", "", name)
    name = re.sub(r"(?i)[\s._+-]*[（(]?cleaned[）)]?", "", name)
    name = re.sub(r"[+_]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .-_+—–")
    name = re.sub(r"^(.*?)(?:\s+\1)+(?=\s*(?:第\d+课时|$))", r"\1", name)
    if ppt:
        keep = re.findall(r"[（(](?:重难点训练|重难点专练)[）)]", name)
        match = re.match(r"(.*?第\s*[一二三四五六七八九十\d]+\s*课时[）)]?)", name)
        if match:
            name = match.group(1)
            for label in keep:
                if label not in name:
                    name += label
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .-_+—–") or "讲义"


def normalized_choice(value: str) -> str:
    return "".join(sorted(set(chr(ord(c)-0xFEE0) if 'Ａ' <= c <= 'Ｄ' else c.upper() for c in value if c.upper() in 'ABCDＡＢＣＤ')))


def answer_conclusion(texts):
    found = [(text, match) for text in texts for match in CONCLUSION_RE.finditer(text)]
    values = {normalized_choice(match.group(1)) for _, match in found}
    if len(values) != 1:
        return None, '', len(values) > 1
    return next(iter(values)), found[-1][0][-200:], False
