"""Recognize pale scan watermarks without erasing overlaid dark printing."""
from io import BytesIO
import cv2
import numpy as np
from PIL import Image
from .rules import watermark_spans


def clean_faint_background(data, ocr):
    try:
        image = Image.open(BytesIO(data)).convert('RGB')
    except (OSError, ValueError):
        return data, 0
    if min(image.size) < 500:
        return data, 0
    scale = min(1, 1400/max(image.size))
    work = np.asarray(image.resize((round(image.width*scale), round(image.height*scale))))
    low, high = work.min(axis=2), work.max(axis=2)
    if np.mean(low > 250) < .4:
        return data, 0
    light = (low >= 185) & (high <= 250) & (high.astype(float)-low < 18)
    dark = cv2.dilate((low < 170).astype('uint8'), np.ones((3,3),np.uint8)) > 0
    signal = cv2.morphologyEx((light & ~dark).astype('uint8'), cv2.MORPH_OPEN, np.ones((3,3),np.uint8))
    if signal.sum() < work.shape[0]*work.shape[1]*.001:
        return data, 0
    isolated = np.where(signal, 0, 255).astype('uint8')
    pixels = np.asarray(image).copy()
    low, high = pixels.min(axis=2), pixels.max(axis=2)
    pale = (low >= 180) & (high <= 252) & (high.astype(float)-low < 20)
    region = np.zeros(pixels.shape[:2], np.uint8)
    count = 0
    for angle in (-45, 45, 0):
        h, w = isolated.shape
        matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
        width = round(h*abs(matrix[0,1])+w*abs(matrix[0,0]))
        height = round(h*abs(matrix[0,0])+w*abs(matrix[0,1]))
        matrix[0,2] += width/2-w/2
        matrix[1,2] += height/2-h/2
        rotated = cv2.warpAffine(isolated, matrix, (width,height), borderValue=255)
        results = ocr.read(Image.fromarray(rotated))
        lines = [(text, (min(p[0] for p in box), min(p[1] for p in box), max(p[0] for p in box), max(p[1] for p in box))) for box, text, _ in results]
        inverse = cv2.invertAffineTransform(matrix)
        for (text, (x0,y0,x1,y1)), spans in zip(lines, watermark_spans(lines)):
            for start, end in spans:
                left = x0+(x1-x0)*start/len(text)
                right = x0+(x1-x0)*end/len(text)
                pad = max(3, (y1-y0)*.06)
                corners = np.array([[left-pad,y0-pad],[right+pad,y0-pad],[right+pad,y1+pad],[left-pad,y1+pad]],np.float32)
                original = cv2.transform(corners[None], inverse)[0]/scale
                cv2.fillConvexPoly(region, np.round(original).astype(np.int32), 255)
                count += 1
        if count:
            # One confirmed orientation is sufficient; other angles only add noise.
            break
    if not count:
        return data, 0
    pixels[(region > 0) & pale] = 255
    stream = BytesIO()
    Image.fromarray(pixels).save(stream, format='PNG')
    return stream.getvalue(), count
