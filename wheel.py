"""SDL joystick input. Mapping keys include the hardware GUID, not a transient index."""
import json
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Signal, QStandardPaths
from wheel_input import WheelInput

ACTIONS = {"A":"A탭 열기", "B":"B탭 열기", "up":"위로", "down":"아래로", "left":"값 감소", "right":"값 증가", "ok":"확정", "back":"취소"}

class Wheel(QObject):
    change = Signal(str)
    pulse = Signal(str)
    status = Signal()
    def __init__(self, settings=None):
        super().__init__()
        self.file = settings or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / "wheel.json"
        try:
            self.bindings = json.loads(self.file.read_text(encoding="utf8"))
            if not isinstance(self.bindings,dict): self.bindings = {}
        except (OSError,ValueError): self.bindings = {}
        self.input = WheelInput()
        self.listening = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(16)
    def assign(self, key, action):
        bindings = dict(self.bindings)
        bindings[key] = action
        self.persist(bindings)
    def persist(self, bindings):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(bindings, indent=2),encoding="utf8")
        tmp.replace(self.file)
        self.bindings = bindings
    def edge(self, iid, guid, control, pressed):
        key = self.input.edge(iid, guid, control, pressed)
        if key: self.handle(key)
    def handle(self, key):
        if self.listening: self.pulse.emit(key)
        elif key in self.bindings: self.change.emit(self.bindings[key])
    def poll(self):
        before = self.description()
        for key in self.input.poll(): self.handle(key)
        if self.description() != before: self.status.emit()
    def description(self):
        return self.input.description()
