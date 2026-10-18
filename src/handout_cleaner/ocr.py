from io import BytesIO
import hashlib
import re
from PIL import Image, ImageDraw
import numpy as np
from .rules import MARK_RE, watermark_spans


class OCR:
    def __init__(self):
        self.engine = None
        self.cache = {}
        self.recognition_cache = {}

    def read(self, image):
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
            background = Image.new('RGBA', image.size, 'white')
            background.alpha_composite(image.convert('RGBA'))
            image = background
        rgb = np.asarray(image.convert('RGB'))
        results, _ = self.engine(rgb)
        return [(box, text, score) for box, text, score in (results or []) if score >= 0.65]

    def recognize_image(self, data):
        digest = hashlib.sha256(data).digest()
        if digest not in self.recognition_cache:
            try:
                image = Image.open(BytesIO(data))
                if min(image.size) < 8:
                    return []
                if image.height < 45:
                    image = image.resize((image.width*3, image.height*3))
                results = self.read(image)
                # Return coordinates in the original image, including small logos.
                original = Image.open(BytesIO(data))
                if original.size != image.size:
                    factor = original.width/image.width
                    results = [([[x*factor, y*factor] for x, y in box], text, score) for box, text, score in results]
            except (OSError, ValueError):
                return []
            if len(self.recognition_cache) < 256:
                self.recognition_cache[digest] = results
            return results
        return self.recognition_cache[digest]

    def is_logo(self, data):
        results = self.recognize_image(data)
        text = ' '.join(text for _, text, _ in results)
        return bool(MARK_RE.search(text)) and not re.sub(r'[\s网0O。·:：|｜-]', '', MARK_RE.sub('', text))

    def clean_image(self, data: bytes):
        digest = hashlib.sha256(data).digest()
        if digest in self.cache:
            return self.cache[digest]
        try:
            image = Image.open(BytesIO(data))
            image = image.convert('RGBA' if image.mode in ('RGBA', 'LA') or 'transparency' in image.info else 'RGB')
        except Exception:
            return data, 0
        if min(image.size) < 8:
            return data, 0
        found = []
        results = self.recognize_image(data)
        lines = [(text, (min(p[0] for p in box), min(p[1] for p in box), max(p[0] for p in box), max(p[1] for p in box))) for box, text, _ in results]
        for (text, (x0, y0, x1, y1)), spans in zip(lines, watermark_spans(lines)):
            # Split a mixed line so neighboring exercise content survives.
            for start, end in spans:
                width = x1-x0
                found.append((x0+width*start/len(text)-1, y0-1, x0+width*end/len(text)+1, y1+1))
        if not found:
            if len(self.cache) < 256:
                self.cache[digest] = (data, 0)
            return data, 0
        draw = ImageDraw.Draw(image)
        for rect in found:
            draw.rectangle(rect, fill=(255,255,255,0) if image.mode == 'RGBA' else 'white')
        stream = BytesIO()
        image.save(stream, format='PNG')
        result = (stream.getvalue(), len(found))
        if len(self.cache) < 256:
            self.cache[digest] = result
        return result
