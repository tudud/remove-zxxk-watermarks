from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image
from handout_cleaner.ocr import OCR

root = Path('artifacts/patch-qa')
image = np.asarray(Image.open(root/'taizhou-answer-before.png').convert('RGB'))
low, high = image.min(axis=2), image.max(axis=2)
light = (low >= 185) & (high <= 248) & (high.astype(float)-low < 18)
dark = cv2.dilate((low < 170).astype('uint8'), np.ones((3,3),np.uint8)) > 0
signal = cv2.morphologyEx((light & ~dark).astype('uint8'),cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
mask = np.where(signal, 0, 255).astype('uint8')
engine = OCR()
for angle in (-45, 45):
    h,w = mask.shape
    m = cv2.getRotationMatrix2D((w/2,h/2), angle, 1)
    width = int(h*abs(m[0,1])+w*abs(m[0,0]))
    height = int(h*abs(m[0,0])+w*abs(m[0,1]))
    m[0,2] += width/2-w/2
    m[1,2] += height/2-h/2
    rotated = cv2.warpAffine(mask, m, (width,height), borderValue=255)
    Image.fromarray(rotated).save(root/f'faint-{angle}.png')
    print(angle, json.dumps(engine.read(Image.fromarray(rotated)),ensure_ascii=True),flush=True)
