"""Editable race plan; browsing a candidate never mutates the committed schedule."""
from dataclasses import dataclass
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel
from race import TYRES

@dataclass(frozen=True)
class Plan:
    start: str="M"
    stops: tuple=((21,"H"),)

def label(text="",name=""):
    x=QLabel(text);x.setObjectName(name);return x

class Strategy(QWidget):
    committed=Signal()
    def __init__(self):
        super().__init__(); self.plan=Plan();self.frame=None;self.cursor=0;self.edit=False;self.draft=None
        self.fields=[]; self.candidates=[];self.note=""
        root=QVBoxLayout(self);root.setContentsMargins(22,6,6,4);root.setSpacing(8)
        root.addWidget(label("PIT WALL   /   02","eyebrow"))
        root.addWidget(label("피트 전략","section"))
        root.addWidget(label("확정된 계획","muted"))
        self.current=label("","plan");root.addWidget(self.current)
        self.schedule=label("","muted");self.schedule.setWordWrap(True);root.addWidget(self.schedule)
        self.mode=label("전략 선택","sub");root.addWidget(self.mode)
        self.list=QVBoxLayout();self.list.setSpacing(5);root.addLayout(self.list)
        self.help=label("","hint");self.help.setWordWrap(True);root.addWidget(self.help)
        root.addStretch(1)
        bottom=QHBoxLayout()
        for txt,key in (("−","left"),("+","right"),("확정","ok"),("취소","back")):
            b=QPushButton(txt);b.clicked.connect(lambda _,k=key:self.act(k));bottom.addWidget(b)
        root.addLayout(bottom)
        self.buttons=[];self.signature=None
    def state(self,f):
        if self.frame and self.frame.scene!=f.scene:
            self.edit=False;self.cursor=0;self.draft=None;self.note=""
        self.frame=f;self.render()
    def preview(self):
        f=self.frame
        if not f.scene:return ["출발 전략 편집"]
        return ["이번 랩 피트","다음 랩 피트","직접 설정"]
    def editfields(self):
        if self.frame.scene:return [("lap",0),("tyre",0),("save",0)]
        vals=[("start",0)]
        for i in range(len(self.draft)):
            vals.extend([("lap",i),("tyre",i)])
        if len(self.draft)<3:vals.append(("add",0))
        if len(self.draft)>1:vals.append(("remove",0))
        return vals+[("save",0)]
    def start_edit(self):
        self.start=self.plan.start
        if self.frame.scene:
            stop=next((s for s in self.plan.stops if s[0]>=self.frame.lap),None)
            self.draft=[list(stop or (self.frame.lap,"H"))]
        else:self.draft=[list(s) for s in self.plan.stops]
        self.edit=True;self.cursor=0;self.note=""
    def cancel(self):
        self.edit=False;self.cursor=0;self.draft=None;self.note="취소됨 · 확정된 계획 유지";self.render()
    def save_stop(self,lap,tyre):
        old=next((s for s in self.plan.stops if s[0]>=self.frame.lap),None)
        rest=[s for s in self.plan.stops if s!=old and (s[0]<self.frame.lap or s[0]>lap)]
        self.plan=Plan(self.plan.start,tuple(sorted(rest+[(lap,tyre)])))
    def act(self,key):
        if not self.frame:return
        if key=="back":self.cancel();return
        entries=self.editfields() if self.edit else self.preview()
        if key in ("up","down") or (not self.edit and key in ("left","right")):
            self.cursor=(self.cursor+(-1 if key in ("up","left") else 1))%len(entries)
            self.note=""
        elif not self.edit and key=="ok":
            if self.frame.scene and self.cursor<2:
                self.save_stop(self.frame.lap+self.cursor,self.next_tyre());self.note="전략 적용됨";self.committed.emit()
            else:self.start_edit()
        elif self.edit:
            kind,i=entries[self.cursor]; step=-1 if key=="left" else 1
            if key in ("left","right") and kind=="lap":
                low=(max(1,self.frame.lap) if i==0 else self.draft[i-1][0]+1)
                high=26 if i+1==len(self.draft) else self.draft[i+1][0]-1
                self.draft[i][0]=max(low,min(high,self.draft[i][0]+step))
            elif key in ("left","right") and kind in ("tyre","start"):
                tyres=list(TYRES);old=self.start if kind=="start" else self.draft[i][1]
                new=tyres[(tyres.index(old)+step)%len(tyres)]
                if kind=="start":self.start=new
                else:self.draft[i][1]=new
            elif key=="ok":
                if kind=="save":
                    if self.frame.scene:self.save_stop(*self.draft[0])
                    else:self.plan=Plan(self.start,tuple(tuple(s) for s in self.draft))
                    self.edit=False;self.draft=None;self.cursor=0;self.note="전략 적용됨";self.committed.emit()
                elif kind=="add":
                    if self.draft[-1][0]<26:self.draft.append([min(26,self.draft[-1][0]+3),"M"])
                    else:self.note="마지막 교체 랩을 앞당기면 스틴트 추가 가능"
                elif kind=="remove":self.draft.pop();self.cursor=0
                else:self.cursor=min(self.cursor+1,len(entries)-1)
        self.render()
    def next_tyre(self):
        return next((t for l,t in self.plan.stops if l>=self.frame.lap),"H")
    def select(self,index):
        self.cursor=index;self.note="";self.render()
    def render(self):
        f=self.frame
        if not f:return
        stop=next((s for s in self.plan.stops if s[0]>=f.lap),None)
        self.current.setText(f"{stop[0]}랩 피트 · {stop[1]} {TYRES[stop[1]]}" if stop else "예정된 피트 없음")
        self.schedule.setText("출발 "+self.plan.start+"   →   "+"   →   ".join(f"L{l} {t}" for l,t in self.plan.stops))
        self.mode.setText("전략 편집   /   ← → 값 변경" if self.edit else "전략 선택")
        rows=[]
        if self.edit:
            for kind,i in self.editfields():
                if kind=="start":s=f"출발 타이어     ‹  {self.start} {TYRES[self.start]}  ›"
                elif kind=="lap":s=f"교체 {i+1}  ·  피트 랩     ‹  L{self.draft[i][0]}  ›"
                elif kind=="tyre":s=f"교체 {i+1}  ·  타이어     ‹  {self.draft[i][1]} {TYRES[self.draft[i][1]]}  ›"
                else:s={"add":"＋  스틴트 추가","remove":"−  마지막 스틴트 삭제","save":"✓  편집한 전략 적용"}[kind]
                rows.append(s)
        else:
            for i,s in enumerate(self.preview()):
                if f.scene and i<2:
                    if f.caution or f.scene==3: detail="분석 대기"
                    else:
                        # Sample pit loss, neutralised/pit laps excluded. Insert YOU in loss-adjusted order.
                        me=f.cars[f.player]; others=[c for c in f.cars if c.code!="YOU"]
                        rank=sum(c.gap<me.gap+(12.1 if i==0 else 10.8) for c in others)
                        before=others[rank-1].code if rank else "—"; after=others[rank].code if rank<len(others) else "—"
                        detail=f"예상 복귀 P{rank+1}  ·  {before} / {after}"
                    s+=f"    L{f.lap+i}\n{detail}"
                rows.append(s)
        signature=(tuple(rows),self.cursor)
        if signature!=self.signature:
            self.signature=signature
            while len(self.buttons)<len(rows):
                b=QPushButton();b.setObjectName("option");j=len(self.buttons)
                b.clicked.connect(lambda _,n=j:self.select(n));self.buttons.append(b);self.list.addWidget(b)
            for i,b in enumerate(self.buttons):
                b.setVisible(i<len(rows))
                if i<len(rows):
                    b.setText(("▸   " if i==self.cursor else "     ")+rows[i])
                    b.setProperty("picked",i==self.cursor);b.style().unpolish(b);b.style().polish(b)
        self.help.setText(self.note or ("↑ ↓ 항목 이동  ·  ← → 값 변경  ·  마지막 항목에서 적용" if self.edit else "선택은 미리보기 · 확정을 눌러야 계획에 반영됨"))

