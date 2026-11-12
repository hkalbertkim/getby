from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import os
root=Path(__file__).resolve().parents[1]/"web/samples"
def font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.isfile(f):return ImageFont.truetype(f,size)
    return ImageFont.load_default()
for key,name,cost,due in [("electricity","Northline Electric",50,20),("mobile","Harbor Mobile",30,22)]:
    im=Image.new("RGB",(900,700),"#fffdf6");d=ImageDraw.Draw(im)
    for y,t,size in [(48,name,48),(150,"November 2026 statement",32),(245,"Customer: Alex Park",26),(315,"Service period: November 2026",26),(415,f"Amount due: ${cost}.00",42),(510,f"Pay by: 2026-11-{due}",32),(625,"Sample bill for Get By",22)]:
        d.text((55,y),t,font=font(size),fill="#192837")
    d.line((52,213,840,213),fill="#9ba5a2",width=3);im.save(root/(key+".png"))
# Original still life for the example license listing.
im=Image.new("RGB",(720,480),"#e4d5c2");d=ImageDraw.Draw(im)
d.rectangle((0,310,720,480),fill="#c4a38a");d.ellipse((240,338,520,388),fill="#977d6c")
d.rounded_rectangle((288,158,445,355),radius=48,fill="#627f73")
for x,y in [(190,56),(290,35),(420,40),(502,85)]:
 d.line((365,181,x,y),fill="#426553",width=7);d.ellipse((x-38,y-19,x+20,y+16),fill="#6a9479")
im.save(root/"photo.jpg",quality=90)
