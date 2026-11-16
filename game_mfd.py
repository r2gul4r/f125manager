"""Select the next pit compound through the Korean F1 25 pit setup panel."""

import asyncio
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab

from live_timing import COMPOUNDS


@dataclass(frozen=True)
class TyreRow:
    down: int  # Distance from the white selection bar to Next Tyres.
    tyre: str | None


@lru_cache(maxsize=1)
def label_mask():
    data = (Path(__file__).parent / "assets/mfd-next-tyre-ko.png").read_bytes()
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)


def ring_compound(rgb):
    if rgb.shape != (48, 48, 3):
        return None
    h, s, v = cv2.split(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV))
    y, x = np.ogrid[-24:24, -24:24]
    radius = x * x + y * y
    ring = (radius >= 18**2) & (radius <= 23**2)
    if np.mean(v[(radius >= 11**2) & (radius <= 16**2)] < 100) < 0.4:
        return None
    coloured = (s > 90) & (v > 85)
    for tyre, hue in [
        ("S", (h < 10) | (h > 168)),
        ("M", (h >= 14) & (h < 37)),
        ("I", (h >= 37) & (h < 90)),
        ("W", (h >= 91) & (h < 134)),
    ]:
        if np.mean((coloured & hue)[ring]) > 0.40:
            return tyre
    if np.mean(((s < 55) & (v > 140))[ring]) > 0.40:
        return "H"
    return None


def read_pit_panel(rgb):
    white = cv2.inRange(rgb, (230, 230, 230), (255, 255, 255))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 170 or not 13 < w / h < 16 or cv2.contourArea(contour) < 0.84 * w * h:
            continue
        scale = w / 886
        for down in (0, 1, 2):
            cy = round(y + h / 2 + down * 67.5 * scale)
            top, bottom = cy - round(29 * scale), cy + round(29 * scale)
            if top < 0 or bottom > rgb.shape[0]:
                continue
            row = cv2.resize(rgb[top:bottom, x : x + w], (886, 58))
            grey = cv2.cvtColor(row[:, 50:270], cv2.COLOR_RGB2GRAY)
            ink = np.uint8(grey < 110 if down == 0 else grey > 170) * 255
            score = cv2.matchTemplate(ink, label_mask(), cv2.TM_CCOEFF_NORMED)
            if score.max() >= 0.65:
                return TyreRow(down, ring_compound(row[5:53, 589:637]))
    return None


class GameWindow:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.hwnd = self.user.GetForegroundWindow()
        if not self.is_game(self.hwnd):
            raise ValueError("F1 25 창으로 돌아가면 다음 타이어를 설정해")

    @staticmethod
    def is_game(hwnd):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        user = ctypes.WinDLL("user32", use_last_error=True)
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return False
        name = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(name))
        try:
            return bool(kernel.QueryFullProcessImageNameW(
                wintypes.HANDLE(handle), 0, name, ctypes.byref(size)
            ) and Path(name.value).name.lower() == "f1_25.exe")
        finally:
            kernel.CloseHandle(wintypes.HANDLE(handle))

    @classmethod
    def return_from_dashboard(cls):
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetForegroundWindow.restype = wintypes.HWND
        dashboard = user.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(256)
        user.GetWindowTextW(wintypes.HWND(dashboard), title, len(title))
        if not title.value.startswith("F1 25 · Race Engineer"):
            return

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def find_game(hwnd, _):
            if user.IsWindowVisible(wintypes.HWND(hwnd)) and cls.is_game(hwnd):
                if user.GetForegroundWindow() == dashboard:
                    user.SetForegroundWindow(wintypes.HWND(hwnd))
                return False
            return True

        user.EnumWindows(find_game, 0)

    def check(self):
        if self.hwnd != self.user.GetForegroundWindow():
            raise ValueError("게임 창 포커스가 바뀌어 입력 중단")

    def read(self):
        self.check()
        # PIL captures physical screen pixels. Match them on mixed-DPI monitors.
        self.user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        old = self.user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            rect = wintypes.RECT()
            if not self.user.GetWindowRect(
                wintypes.HWND(self.hwnd), ctypes.byref(rect)
            ):
                raise ValueError("게임 창 위치 확인 실패")
            image = ImageGrab.grab(
                bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True
            )
            self.check()
            return read_pit_panel(np.asarray(image.convert("RGB")))
        finally:
            if old:
                self.user.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))

    def key(self, scan, extended, release):
        if not release:
            self.check()

        class Keyboard(ctypes.Structure):
            _fields_ = [
                ("vk", wintypes.WORD),
                ("scan", wintypes.WORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("extra", ctypes.c_size_t),
            ]

        class Payload(ctypes.Union):
            _fields_ = [
                ("keyboard", Keyboard),
                (
                    "mouse",
                    ctypes.c_byte * (32 if ctypes.sizeof(ctypes.c_void_p) == 8 else 24),
                ),
            ]

        class Input(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("payload", Payload)]

        event = Input(
            1,
            Payload(
                keyboard=Keyboard(
                    0, scan, 8 | int(extended) | (2 if release else 0), 0, 0
                )
            ),
        )
        if self.user.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
            raise OSError("게임 키 입력 실패")

    async def press(self, key):
        scan, extended = {
            "panel": (0x3C, False),
            "down": (0x50, True),
            "left": (0x4B, True),
            "right": (0x4D, True),
        }[key]
        self.key(scan, extended, False)
        try:
            await asyncio.sleep(0.065)
        finally:
            self.key(scan, extended, True)


async def set_next_tyre(target, valid, window_factory=GameWindow):
    compounds = ("S", "M", "H", "I", "W")
    if target not in compounds:
        raise ValueError("알 수 없는 타이어")
    requested_focus = False
    for _ in range(15):
        if not valid():
            raise ValueError("실시간 레이스 상태 변경")
        try:
            window = window_factory()
            break
        except ValueError:
            if not requested_focus and window_factory is GameWindow:
                await asyncio.to_thread(GameWindow.return_from_dashboard)
                requested_focus = True
            await asyncio.sleep(0.2)
    else:
        raise ValueError("게임 창 포커스 대기 만료 · 플랜을 다시 확정해")

    async def press(key):
        if not valid():
            raise ValueError("실시간 레이스 상태 변경")
        await window.press(key)

    async def settled(accept):
        previous = object()
        repeats = 0
        for _ in range(12):
            if not valid():
                raise ValueError("실시간 레이스 상태 변경")
            row = await asyncio.to_thread(window.read)
            repeats = repeats + 1 if row == previous else 0
            if repeats >= 2 and accept(row):
                return row
            previous = row
            await asyncio.sleep(0.12)
        raise ValueError("다음 타이어 판독 실패 · 피트 MFD에서 확인해")

    row = await settled(lambda r: r is None or r.tyre in compounds)
    if row is None:
        await press("panel")
        row = await settled(lambda r: r and r.tyre in compounds)
    while row.tyre != target:
        before = row
        if before.down:
            await press("down")
            row = await settled(lambda r, down=before.down - 1: r and r.down == down and r.tyre in compounds)
            continue
        start, end = compounds.index(before.tyre), compounds.index(target)
        step = 1 if start < end else -1
        await press("right" if step == 1 else "left")
        row = await settled(lambda r, old=before: r and r.down == 0 and r.tyre in compounds and r != old)
        if compounds.index(row.tyre) not in range(start + step, end + step, step):
            # The game can skip unavailable sets. Undo this verified step on the same row.
            await press("left" if step == 1 else "right")
            await settled(lambda r, old=before: r == old)
            raise ValueError(f"{target} 선택 경로 이탈 · {before.tyre} 복원 확인")


class RacePitSync:
    def __init__(self, snapshot, send=set_next_tyre):
        self.snapshot = snapshot
        self.send = send
        self.session = None
        self.stops = []
        self.completed = 0
        self.task = None
        self.revision = 0
        self.pending = None
        self.message = ""

    @staticmethod
    def player(raw):
        return next(
            (c for c in raw.get("cars", ()) if c["slot"] == raw.get("player")), None
        )

    def live_car(self, raw):
        if (
            raw.get("handoff")
            or raw.get("spectating")
            or raw.get("paused")
            or raw.get("error")
            or raw.get("ageMs") is None
            or raw["ageMs"] > 2000
            or (raw.get("uid"), raw.get("epoch")) != self.session
        ):
            return None
        car = self.player(raw)
        return car if car and car["result"] == 2 and not car["pit"] else None

    def submit(self, raw, frame, plan):
        if raw.get("handoff") or not frame["isRace"]:
            return
        self.revision += 1
        self.pending = None
        self.session = raw.get("uid"), raw.get("epoch")
        self.stops = [stop for stop in plan.stops if stop[0] >= frame["lap"]]
        car = self.live_car(raw)
        if not car or frame["mode"] != "race":
            self.stops.clear()
            self.message = "게임 입력 대기 · 주행 중 플랜을 다시 확정해"
        elif self.stops:
            self.completed = car["pitStops"]
            self.start()
        else:
            self.message = ""

    def start(self):
        lap, tyre = self.stops[0]
        self.message = f"L{lap} {tyre} · 게임 창에서 다음 타이어 설정 대기"
        self.pending = (self.revision, lap, tyre)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.dispatch())

    async def dispatch(self):
        while self.pending is not None:
            revision, lap, tyre = self.pending
            self.pending = None
            def valid(expected=revision, stop_lap=lap):
                car = self.live_car(self.snapshot())
                return expected == self.revision and car and car["pitStops"] == self.completed and car["lap"] <= stop_lap

            try:
                await self.send(tyre, valid)
                message = f"게임 MFD 확인 · 다음 타이어 {tyre}"
            except (ValueError, OSError, cv2.error) as exc:
                message = f"게임 MFD 미확인 · 목표 {tyre} · {exc}"
            if revision == self.revision:
                self.message = message
            elif self.pending:
                # A superseded key may only become visible after key-up and menu animation.
                await asyncio.sleep(0.25)

    def observe(self, raw):
        if (raw.get("uid"), raw.get("epoch")) != self.session or raw.get("handoff"):
            return ""
        car = self.live_car(raw)
        if car and self.stops and car["pitStops"] > self.completed:
            self.revision += 1
            self.pending = None
            count = car["pitStops"] - self.completed
            self.completed = car["pitStops"]
            _, expected = self.stops.pop(0)
            actual = COMPOUNDS.get(car.get("compound"))
            if count != 1 or not actual:
                self.stops.clear()
                self.message = "정차 기록 변경 · 다음 플랜 확인 필요"
            elif actual != expected:
                self.stops.clear()
                self.message = "실제 장착 타이어가 달라 · 다음 플랜 확인 필요"
            elif self.stops and self.stops[0][0] >= car["lap"]:
                self.start()
            else:
                self.stops.clear()
                self.message = f"실제 장착 확인 · {expected}"
        return self.message
