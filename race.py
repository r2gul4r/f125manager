"""Deterministic, accelerated presentation fixture; elapsed time is in demo seconds."""
from dataclasses import dataclass
from math import sin, ceil

DRIVERS = "VER NOR PIA RUS LEC HAM ALO YOU GAS SAI ALB ANT HUL OCO BEA HAD LAW LIN BOR COL PER BOT".split()
# 2026 Japanese GP race timing colours: https://api.openf1.org/v1/drivers?session_key=11253
# YOU takes Stroll's seat. Guest is a fictional constructor with a custom violet.
TEAM_GRID = (
    ("Mercedes", "#00D7B6", "RUS ANT"), ("McLaren", "#F47600", "NOR PIA"),
    ("Ferrari", "#ED1131", "LEC HAM"), ("Red Bull", "#4781D7", "VER HAD"),
    ("Aston Martin", "#229971", "ALO YOU"), ("Williams", "#1868DB", "ALB SAI"),
    ("Alpine", "#00A1E8", "GAS COL"), ("Haas", "#9C9FA2", "OCO BEA"),
    ("Audi", "#F50537", "HUL BOR"), ("Racing Bulls", "#6C98FF", "LAW LIN"),
    ("Cadillac", "#909090", "PER BOT"), ("Guest", "#9856EF", "KIM SEO"),
)
COLORS = {code: color for _, color, drivers in TEAM_GRID for code in drivers.split()}
BASE = [0, 3.2, 6.3, 9.5, 12, 13.5, 14.8, 16, 16.8, 18.6, 20.9, 22.4, 24.1, 25.6, 27.2, 28.8, 30.2, 32.1, 33.7, 35.6, 37.8, 39.9]
WEB_GRID = [*DRIVERS, "KIM", "SEO"]
BASE.extend([42.1, 44.0])
SCENES = ["출발 전", "앞차 추격", "앞차 페이스 회복", "알론소 피트 인", "세이프티카", "VSC", "재출발"]
EVENTS = ["그리드 · 출발 전략 편집", "YOU 개인 최고 랩", "ALO 페이스 회복", "ALO 피트 진입", "세이프티카 투입", "가상 세이프티카", "그린 플래그 · ALO 복귀"]
TYRES = {"S":"소프트", "M":"미디엄", "H":"하드", "I":"인터", "W":"웨트"}
RINGS = dict(zip(TYRES, ["#ff555c","#ffe05b","#e8e9ed","#57cb76","#47b3ef"]))
DURATION = 18

@dataclass(frozen=True)
class Car:
    code: str
    gap: float
    last: float
    tyre: str
    age: int
    phase: float
    stints: tuple[tuple[str, int], ...] = ()

@dataclass(frozen=True)
class Frame:
    scene: int
    lap: int
    cars: tuple[Car, ...]
    events: tuple[str, ...]
    @property
    def player(self):
        return next(i for i,c in enumerate(self.cars) if c.code == "YOU")
    @property
    def caution(self):
        return self.scene in (4,5)

def tyre_stints(code, slot, lap, seconds, start_tyre):
    """Mock tyre sets in mounting order. A stint counts completed racing laps."""
    # Each entry is (completed laps at the stop, newly mounted compound).
    opening = "M" if slot % 3 else "S"
    stops = ()
    if code == "YOU":
        opening, stops = start_tyre, ((5, "M"),)
    elif code == "ALO":
        opening, stops = "M", ((4, "S"),)
        if lap > 20 or (lap == 20 and seconds >= 12):
            stops += ((19, "H"),)
    elif code == "SAI":
        opening, stops = "M", ((9, "H"),)
    elif code == "ALB":
        opening, stops = "S", ((10, "M"),)
    elif slot % 4:
        stops = ((7 + slot % 7, "H" if opening == "M" else "M"),)
    completed = max(0, lap - 1)
    result = []
    mounted, since = opening, 0
    for at, compound in stops:
        if at > completed:
            break
        result.append((mounted, at - since))
        mounted, since = compound, at
    return (*result, (mounted, completed - since))


def snapshot(scene, seconds, start_tyre="M", drivers=DRIVERS):
    lap = 0 if scene == 0 else 17 + scene
    elapsed = max(0, scene-1)*DURATION + seconds
    cars = []
    for i, code in enumerate(drivers):
        gap = BASE[i] + (0.06*(sin(elapsed/5+i)-sin(i)) if i and code not in ("YOU","ALO","GAS") else 0)
        if code == "GAS":
            gap -= .025*min(elapsed/DURATION,4)
        if code == "ALO":
            gap += (0.05*seconds/DURATION if scene == 1 else
                    0.05-0.30*seconds/DURATION if scene == 2 else
                    -0.25+min(seconds/10,1)*18.55 if scene == 3 else
                    18.3 if scene >= 4 else 0)
        if scene == 0:
            gap = i*0.17
        stints = tyre_stints(code, i, lap, seconds, start_tyre)
        tyre, age = stints[-1]
        phase = ((0 if scene==0 else .48+elapsed/DURATION) - gap/94) % 1
        last = 92.9+i*0.12+0.18*sin(scene+i)
        if scene in (1, 2):
            # L17/L18 sample splits match the scripted approach, recovery and defence.
            last = {"YOU":93.688, "ALO":93.738 if scene == 1 else 93.388, "GAS":93.663}.get(code, last)
        cars.append(Car(code, gap, last, tyre, age, phase, stints))
    cars.sort(key=lambda c:c.gap)
    events = tuple(f"L{17+j}   {EVENTS[j]}" for j in range(max(1,scene-1),scene+1))
    return Frame(scene,lap,tuple(cars),events)

def briefing(frame):
    if frame.scene == 0 or frame.scene >= 3:
        reason={0:"출발 전",3:"피트 랩 제외",4:"SC 랩 제외",5:"VSC 랩 제외",6:"재출발 표본 수집"}[frame.scene]
        return "분석 대기", "분석 대기", reason+" · 정상 랩 대기"
    if frame.scene == 1:
        gap=frame.cars[frame.player].gap-frame.cars[frame.player-1].gap
        laps=max(0,ceil((gap-1)/.05-1e-6))
        return f"랩당 0.05초 접근 · {laps}랩 뒤 1초 이내 예상", "랩당 0.03초 접근 · 이미 1초 이내", "최근 정상 3랩 평균 · 0.4초 저하"
    return "랩당 0.30초 손실 · 격차 벌어지는 중", "랩당 0.03초 접근 · 이미 1초 이내", "최근 정상 3랩 평균 · 0.2초 저하"

def lap_time(seconds):
    return f"{int(seconds//60)}:{seconds%60:06.3f}"
