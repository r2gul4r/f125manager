"""F1 25 Manager · sample race dashboard. Run with Python 3.11."""
import sys
from time import monotonic
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QKeySequence,QShortcut,QFont
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QPushButton,QLabel,
    QStackedWidget,QComboBox,QDialog,QGridLayout,QScrollArea,QFrame)
from instruments import Tower,Circuit
from strategy import Strategy,label
from wheel import Wheel,ACTIONS
from race import snapshot,SCENES,DURATION,TYRES,RINGS,briefing

STYLE="""
QWidget {background:#0c0d10;color:#f4f4f7;font-family:'Malgun Gothic';font-size:15px;}
QPushButton,QComboBox {background:#222329;border:1px solid #383a43;border-radius:4px;padding:6px 12px;font-weight:600;}
QPushButton:hover,QComboBox:hover {background:#30323b;border-color:#999ba4;}
QPushButton:pressed {background:#45474d;} QComboBox QAbstractItemView {background:#24252b;selection-background-color:#45464c;}
#mast,#mast QLabel {background:#bd151e;color:white;} #brand {font:italic bold 32px 'Arial';} #session {font-weight:700;font-size:19px;}
#lap {font:bold 21px 'Consolas';} #flag {font:bold 16px 'Consolas';} #demo {font:bold 15px 'Malgun Gothic';}
#nav {background:#1b1c22;} #nav QPushButton {border:none;border-radius:0;background:transparent;color:#a7a8b1;font-size:16px;padding:7px 16px;}
#nav QPushButton:checked {border-bottom:4px solid #f23842;color:white;}
#nav QPushButton:hover {color:white;} #section {font-size:23px;font-weight:800;} #sub {font-size:18px;font-weight:700;}
#eyebrow {font:bold 13px 'Consolas';color:#e36a71;} #muted,#hint {color:#afb1bb;} #hint {font-size:13px;}
#divider {background:#383940;} #event {background:#191a20;padding:7px 12px;font-size:16px;}
#number {font:bold 48px 'Consolas';} #you {font:bold 56px 'Consolas';color:#ffe05b;}
#plan {font-size:36px;font-weight:bold;} #option {text-align:left;background:#202127;border:1px solid #303138;padding:7px 14px;font-size:17px;}
#option[picked="true"] {background:#303033;border:2px solid #ffe05b;color:#fff0a7;}
#footer,#footer QLabel {background:#18191e;color:#acadb7;font-size:13px;} #ring {font:bold 29px 'Consolas';}
QScrollArea {border:none;} #analysis {font-size:15px;color:#dfdfe6;}"""

def button(text,fn):
    b=QPushButton(text);b.setFocusPolicy(Qt.NoFocus);b.clicked.connect(fn);return b

def line(vertical=False):
    w=QFrame();w.setObjectName("divider")
    if vertical:w.setFixedWidth(1)
    else:w.setFixedHeight(1)
    return w

def box(direction=QVBoxLayout, margins=(0,0,0,0),spacing=8):
    w=QWidget();layout=direction(w);layout.setContentsMargins(*margins);layout.setSpacing(spacing)
    return w,layout

class Mapping(QDialog):
    def __init__(self,wheel,parent):
        super().__init__(parent);self.w=wheel;self.target=None;self.setWindowTitle("휠 입력 매핑")
        self.resize(660,450);v=QVBoxLayout(self);v.addWidget(label("휠 입력 매핑","section"))
        self.device=label("","muted");v.addWidget(self.device);self.message=label("동작 선택 → 휠 버튼을 누르거나 다이얼을 해당 위치로 돌려.","hint");v.addWidget(self.message)
        self.grid=QGridLayout();v.addLayout(self.grid);self.rows={}
        for i,(code,title) in enumerate(ACTIONS.items()):
            self.grid.addWidget(label(title),i,0);self.rows[code]=label("","muted");self.grid.addWidget(self.rows[code],i,1)
            self.grid.addWidget(button("입력 등록",lambda _,a=code:self.listen(a)),i,2)
            self.grid.addWidget(button("해제",lambda _,a=code:self.clear(a)),i,3)
        v.addWidget(button("닫기",self.accept));wheel.pulse.connect(self.receive);wheel.status.connect(self.refresh)
        self.refresh()
    def refresh(self):
        self.device.setText(self.w.description())
        for code,l in self.rows.items():
            vals=[k.split("/")[-1] for k,v in self.w.bindings.items() if v==code]
            l.setText(", ".join(vals) or "미지정");l.setToolTip(", ".join(k for k,v in self.w.bindings.items() if v==code))
    def listen(self,action):
        self.target=action;self.w.listening=True;self.message.setText(ACTIONS[action]+" · 지금 입력할 휠 버튼을 눌러.")
    def clear(self,action):
        self.w.listening=False;self.target=None
        try:self.w.persist({k:v for k,v in self.w.bindings.items() if v!=action})
        except OSError as e:self.message.setText("저장 실패: "+str(e))
        self.refresh()
    def receive(self,key):
        if not self.target:return
        try:self.w.assign(key,self.target);self.message.setText(ACTIONS[self.target]+" · 저장됨")
        except OSError as e:self.message.setText("저장 실패: "+str(e))
        self.target=None;self.w.listening=False;self.refresh()
    def done(self,result):
        self.w.listening=False;self.w.pulse.disconnect(self.receive);self.w.status.disconnect(self.refresh);super().done(result)

class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("F1 25 Manager · 샘플 레이스")
        self.resize(1460,850);self.scene=1;self.seconds=0.;self.running=True;self.clock=monotonic()
        self.wheel=Wheel();self.mapping=None
        base,root=box(spacing=0);self.setCentralWidget(base)
        mast,h=box(QHBoxLayout,(20,5,18,5),18);mast.setObjectName("mast")
        for txt,name in (("F1 25","brand"),("│   스즈카 GP   /   결승","session")):h.addWidget(label(txt,name))
        h.addStretch();self.lap=label("","lap");self.flag=label("","flag");h.addWidget(self.lap);h.addWidget(self.flag);h.addWidget(label("●  데모","demo"));root.addWidget(mast)
        nav,n=box(QHBoxLayout,(14,0,12,0),8);nav.setObjectName("nav");self.tabs=[]
        for i,s in enumerate(("A   라이브 타이밍","B   내 레이스")):
            b=button(s,lambda _,k=i:self.tab(k));b.setCheckable(True);n.addWidget(b);self.tabs.append(b)
        n.addStretch();self.sceneBox=QComboBox();self.sceneBox.addItems(SCENES);self.sceneBox.setCurrentIndex(1)
        self.sceneBox.setAccessibleName("샘플 장면");self.sceneBox.setFocusPolicy(Qt.ClickFocus);self.sceneBox.activated.connect(self.scene_to);n.addWidget(self.sceneBox)
        self.play=button("Ⅱ  일시정지",self.toggle);n.addWidget(self.play)
        n.addWidget(button("휠 매핑",self.setup));n.addWidget(button("전체 화면",self.full));root.addWidget(nav)
        self.pages=QStackedWidget();root.addWidget(self.pages,1)
        a,ah=box(QHBoxLayout,(12,12,12,10),14);self.pages.addWidget(a)
        self.tower=Tower();ah.addWidget(self.tower,54);ah.addWidget(line(True))
        track,t=box(margins=(4,2,4,0));ah.addWidget(track,46)
        t.addWidget(label("CIRCUIT   /   01","eyebrow"));t.addWidget(label("실시간 트랙맵","section"))
        self.circuit=Circuit();t.addWidget(self.circuit,1)
        t.addWidget(label("●  내 차      ●  순위상 앞뒤 차에 라벨 표시","muted"));t.addWidget(line())
        t.addWidget(label("레이스 이벤트","sub"));self.events=[label("","event"),label("","event")]
        for x in self.events:t.addWidget(x)
        b,bh=box(QHBoxLayout,(16,12,14,10),12);self.pages.addWidget(b)
        local,l=box(spacing=7);bh.addWidget(local,54);bh.addWidget(line(True))
        stats,sl=box(QHBoxLayout,spacing=12);self.stats=[]
        for i in range(3):
            block,bl=box(spacing=0);cap=label("","muted");val=label("","you" if i==0 else "number")
            bl.addWidget(cap);bl.addWidget(val);sl.addWidget(block,1);self.stats.append((cap,val))
            if i<2:sl.addWidget(line(True))
        l.addWidget(stats);l.addWidget(line());l.addWidget(label("내 주변 순위","sub"))
        self.local=Tower(True);l.addWidget(self.local,1);l.addWidget(line())
        tire,tl=box(QHBoxLayout);self.ring=label("M","ring");self.ring.setFixedSize(54,54);self.ring.setAlignment(Qt.AlignCenter)
        self.tyre=label("","sub");self.pace=label("","muted");tl.addWidget(self.ring);tl.addWidget(self.tyre);tl.addStretch();tl.addWidget(self.pace);l.addWidget(tire)
        self.chase=label("","analysis");self.defend=label("","analysis");l.addWidget(self.chase);l.addWidget(self.defend)
        self.strategy=Strategy();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.strategy);bh.addWidget(scroll,46)
        self.strategyScroll=scroll;self.strategy.committed.connect(self.render)
        foot,fl=box(QHBoxLayout,(18,5,18,5));foot.setObjectName("footer")
        fl.addWidget(label("1 / 2  탭     ·     ↑ ↓  이동     ·     ← →  값     ·     Enter  확정     ·     Esc  취소"));fl.addStretch()
        self.hw=label("");fl.addWidget(self.hw);self.wheel.status.connect(self.hardware);self.hardware();root.addWidget(foot)
        self.wheel.change.connect(self.act);self.shortcuts=[]
        for k,action in (("1","A"),("2","B"),("Up","up"),("Down","down"),("Left","left"),("Right","right"),("Return","ok"),("Enter","ok"),("Escape","back"),("Space","pause"),("F11","full")):
            sc=QShortcut(QKeySequence(k),self);sc.setAutoRepeat(False);sc.activated.connect(lambda a=action:self.act(a));self.shortcuts.append(sc)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(80)
        self.tab(0);self.render()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        scale=min(max(.67,self.width()/1920),max(.67,self.height()/1080),1.2)
        def px(n):return int(scale*n)
        self.setStyleSheet(f"""
        #number {{font-size:{px(83)}px;}} #you {{font-size:{px(97)}px;}}
        #plan {{font-size:{px(58)}px;}} #section {{font-size:{px(33)}px;}}
        #sub {{font-size:{px(28)}px;}} #muted {{font-size:{px(22)}px;}}
        #option {{font-size:{px(28)}px;padding:{px(15)}px {px(20)}px;}}
        #analysis {{font-size:{px(23)}px;padding:{px(3)}px 0;}}
        #event {{font-size:{px(21)}px;padding:{px(12)}px;}}
        #hint {{font-size:{px(18)}px;}} #nav QPushButton {{font-size:{px(22)}px;}}
        #brand {{font-size:{px(43)}px;}} #session,#lap {{font-size:{px(27)}px;}}
        """)
    def hardware(self):
        self.hw.setText(self.wheel.description())
    def setup(self):
        if self.mapping:return
        self.mapping=Mapping(self.wheel,self);self.mapping.exec();self.mapping.deleteLater();self.mapping=None;self.clock=monotonic()
    def full(self):
        if self.isFullScreen():self.showNormal()
        else:self.showFullScreen()
    def tab(self,i):
        old=self.pages.currentIndex()
        if old!=i and old==1:self.strategy.cancel()
        self.pages.setCurrentIndex(i)
        for j,b in enumerate(self.tabs):b.setChecked(i==j)
    def act(self,action):
        if self.mapping:return
        if action in ("A","B"):self.tab(int(action=="B"))
        elif action=="pause":self.toggle()
        elif action=="full":self.full()
        elif self.pages.currentIndex()==1:
            self.strategy.act(action)
            if self.strategy.buttons:self.strategyScroll.ensureWidgetVisible(self.strategy.buttons[self.strategy.cursor])
        elif action=="back" and self.isFullScreen():self.showNormal()
    def toggle(self):
        self.running=not self.running;self.clock=monotonic();self.play.setText("Ⅱ  일시정지" if self.running else "▶  재생")
    def scene_to(self,i):
        self.scene=i;self.seconds=0.;self.clock=monotonic();self.sceneBox.setCurrentIndex(i);self.render()
    def tick(self):
        now=monotonic();dt=now-self.clock;self.clock=now
        if not self.running or self.mapping:return
        if self.scene==0:return
        self.seconds+=dt
        if self.seconds>=DURATION:
            self.scene=self.scene+1 if self.scene<len(SCENES)-1 else 1;self.seconds%=DURATION;self.sceneBox.setCurrentIndex(self.scene)
        self.render()
    def render(self):
        f=snapshot(self.scene,self.seconds,self.strategy.plan.start);self.frame=f
        self.lap.setText(f"LAP  {f.lap:02d} / 27" if f.scene else "PRE-RACE")
        flag={0:"◆  GRID",4:"⚑  SAFETY CAR",5:"⚑  VSC"}.get(f.scene,"⚑  GREEN FLAG")
        self.flag.setText(flag);self.flag.setStyleSheet("background:#231f27;padding:3px 7px;color:"+("#ffe477" if f.caution else "#7af5aa" if f.scene else "#dddddf"))
        for w in (self.tower,self.circuit,self.local):w.frame=f;w.update()
        ev=list(reversed(f.events))
        if f.scene==1:ev.append("L17   OCO 피트 아웃")
        if not f.scene:ev=["GRID   출발 전략 편집 가능"]
        for j,x in enumerate(self.events):x.setText(ev[j] if j<len(ev) else "—")
        idx=f.player;c=f.cars[idx]
        for j,other in enumerate((idx,idx-1,idx+1)):
            cap,val=self.stats[j]
            if j==0:cap.setText("내 순위");val.setText(f"P{idx+1}")
            elif 0<=other<len(f.cars):
                d=f.cars[other];cap.setText(("앞차  " if j==1 else "뒤차  ")+d.code)
                val.setText(f"{abs(c.gap-d.gap):.1f}초" if f.scene else "—")
            else:cap.setText("앞차" if j==1 else "뒤차");val.setText("—")
        chase,defend,pace=briefing(f);self.pace.setText(pace)
        tyre=c.tyre
        self.ring.setText(tyre);self.ring.setStyleSheet(f"border:4px solid {RINGS[tyre]};border-radius:27px;color:{RINGS[tyre]};")
        self.tyre.setText(f"{TYRES[tyre]}  ·  사용 {c.age}랩")
        self.chase.setText("추격   /   "+chase);self.defend.setText("방어   /   "+defend)
        self.strategy.state(f)

def main():
    app=QApplication(sys.argv);app.setOrganizationName("f125manager");app.setApplicationName("PitWall")
    app.setStyle("Fusion");app.setStyleSheet(STYLE)
    w=Dashboard()
    screens=app.screens()
    if len(screens)>1:
        s=next(s for s in screens if s!=app.primaryScreen());w.setScreen(s);w.move(s.availableGeometry().topLeft());w.showFullScreen()
    else:w.show()
    sys.exit(app.exec())
if __name__=="__main__":main()

