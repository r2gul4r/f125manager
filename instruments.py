import json
from math import cos, radians
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath
from PySide6.QtWidgets import QWidget, QSizePolicy
from race import COLORS, RINGS, lap_time

WHITE="#f4f5f7"; MUTED="#9a9da8"; GOLD="#ffe05b"
def drawtext(p,x,y,w,h,text,size,color=WHITE,bold=False,left=False,mono=False):
    font=QFont("Consolas" if mono else "Malgun Gothic")
    font.setPixelSize(max(9,int(size)))
    font.setBold(bold)
    p.setFont(font); p.setPen(QColor(color))
    p.drawText(QRectF(x,y,w,h), (Qt.AlignLeft if left else Qt.AlignCenter) | Qt.AlignVCenter, str(text))

class Tower(QWidget):
    def __init__(self, local=False):
        super().__init__()
        self.local=local; self.frame=None
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.setAccessibleName("내 주변 순위표" if local else "전체 순위표")
    def indices(self):
        f=self.frame
        return list(range(max(0,f.player-2),min(len(f.cars),f.player+3))) if self.local else list(range(len(f.cars)))
    def paintEvent(self,e):
        f=self.frame
        if not f:return
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height()
        ids=self.indices()
        headings=["POS","DRIVER","GAP","INT","LAST LAP"] + ([] if self.local else ["S1","S2","S3","TYRE"])
        cols=([.12,.22,.22,.19,.25] if self.local else [.075,.155,.14,.14,.168,.068,.068,.068,.118])
        edges=[0]
        for width in cols: edges.append(edges[-1]+width*w)
        rh=h/(len(ids)+1) if self.local else min(h/(len(ids)+1),54)
        p.fillRect(0,0,w,int(rh),QColor("#25262d"))
        for j,label in enumerate(headings):
            drawtext(p,edges[j]+3,0,cols[j]*w-6,rh,label,min(rh*.43,w*.021),MUTED,True,j==1,True)
        for row,i in enumerate(ids):
            c=f.cars[i]; y=(row+1)*rh
            bg="#37321d" if c.code=="YOU" else ("#17181d" if row%2==0 else "#101115")
            p.fillRect(QRectF(0,y,w,rh+.5),QColor(bg))
            if c.code=="YOU":p.fillRect(QRectF(0,y,3,rh),QColor(GOLD))
            p.fillRect(QRectF(edges[1],y+rh*.21,max(3,w*.004),rh*.58),QColor(COLORS[c.code]))
            vals=[str(i+1),c.code,("—" if f.scene==0 or i==0 else f"+{c.gap:.3f}"),("—" if f.scene==0 or i==0 else f"+{c.gap-f.cars[i-1].gap:.3f}"),lap_time(c.last) if f.scene else "—"]
            for j,val in enumerate(vals):
                inset=10 if j==1 else 0
                drawtext(p,edges[j]+inset,y,cols[j]*w-inset,rh,val,min(rh*.57,w*(.034 if self.local else .025)),GOLD if c.code=="YOU" and j<=1 else WHITE,j<=1,j==1,True)
            if not self.local:
                for k in range(3):
                    cx=edges[5+k]+cols[5+k]*w*.5
                    shades=("#474950","#54d977","#474950","#c56cff","#54d977")
                    col=shades[(i*3+k+f.scene)%5] if f.scene else shades[0]
                    p.setPen(Qt.NoPen);p.setBrush(QColor(col));bw=cols[5+k]*w*.53
                    p.drawRoundedRect(QRectF(cx-bw/2,y+rh*.42,bw,rh*.16),rh*.08,rh*.08)
                r=min(rh*.32,cols[8]*w*.15); cx=edges[8]+cols[8]*w*.30;cy=y+rh*.5
                p.setPen(QPen(QColor(RINGS[c.tyre]),max(1.5,r*.15)));p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx,cy),r,r)
                drawtext(p,cx-r,cy-r,r*2,r*2,c.tyre,r*1.55,RINGS[c.tyre],True,False,True)
                drawtext(p,edges[8]+cols[8]*w*.50,y,cols[8]*w*.43,rh,c.age,min(rh*.50,w*.021),WHITE,False,False,True)
        p.end()

def suzuka():
    source = Path(__file__).parent / "assets" / "f1-circuits" / "jp-1962.geojson"
    feature = json.loads(source.read_text(encoding="utf-8"))["features"][0]
    west, south, east, north = feature["bbox"]
    lon_scale = cos(radians((north + south) / 2))
    width = (east - west) * lon_scale
    height = north - south
    scale = min(1000 / width, 570 / height)
    left = 667.5 - width * scale / 2
    top = 385 - height * scale / 2
    path = QPainterPath()
    for i, (lon, lat) in enumerate(feature["geometry"]["coordinates"]):
        point = QPointF(left + (lon - west) * lon_scale * scale, top + (north - lat) * scale)
        if i == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path

class Circuit(QWidget):
    def __init__(self):
        super().__init__();self.frame=None;self.route=suzuka();self.length=self.route.length()
        self.setMinimumHeight(140);self.setAccessibleName("스즈카 서킷 · 내 차와 앞뒤 차")
    def pos(self,phase):
        return self.route.pointAtPercent(self.route.percentAtLength((phase%1)*self.length))
    def paintEvent(self,event):
        f=self.frame
        if not f:return
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        scale=min(self.width()/1135,self.height()/690)
        p.translate((self.width()-1135*scale)/2,(self.height()-690*scale)/2)
        p.scale(scale,scale);p.translate(-100,-40)
        p.setPen(QPen(QColor("#363841"),16,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.drawPath(self.route)
        p.setPen(QPen(QColor("#c5c6cc"),7,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.drawPath(self.route)
        start=self.pos(0); p.save();p.translate(start);p.rotate(-37)
        for i in range(4):
            for j in range(2):p.fillRect(i*5-10,j*5-5,5,5,QColor(WHITE if (i+j)%2 else "#25262c"))
        p.restore()
        near=range(max(0,f.player-1),min(len(f.cars),f.player+2))
        for i in sorted(range(len(f.cars)),key=lambda i:(i in near,i==f.player)):
            c=f.cars[i];pt=self.pos(c.phase);r=10 if i==f.player else 8
            p.setPen(QPen(QColor(GOLD if i==f.player else "#101114"),3))
            p.setBrush(QColor("#1b1b18" if i==f.player else COLORS[c.code]));p.drawEllipse(pt,r,r)
        points=[self.pos(f.cars[i].phase) for i in near]
        center=points[list(near).index(f.player)]
        left=center.x()>680; bx=center.x()+(-154 if left else 43)
        by=max(72,min(610,center.y()-49))
        for n,(i,pt) in enumerate(zip(near,points)):
            c=f.cars[i];clr=GOLD if c.code=="YOU" else WHITE;yy=by+n*35
            p.setPen(QPen(QColor(clr),1.5));p.drawLine(pt,QPointF(bx+(88 if left else 0),yy+14))
            p.setBrush(QColor("#14151a"));p.drawRoundedRect(QRectF(bx,yy,88,28),4,4)
            drawtext(p,bx,yy,88,28,c.code,20,clr,True,False,True)
        p.end()

