"""Per-browser plan for the 27-lap demo. Only a confirmed edit changes it."""
from dataclasses import dataclass

from race import TYRES


def demo_conditions(offset: int) -> dict[str, str]:
    """Observed weather and surface on the accelerated race clock, in seconds."""
    if offset < 45:
        rain, surface = "Clear", "Dry"
    elif offset < 54:
        rain, surface = "Light rain", "Dry"
    elif offset < 72:
        rain, surface = "Light rain", "Damp"
    elif offset < 85:
        rain, surface = "Heavy rain", "Standing water"
    elif offset < 99:
        rain, surface = "Clearing", "Damp"
    else:
        rain, surface = "Clear", "Dry"

    return {"rain": rain, "surface": surface, "condition": "Dry" if surface == "Dry" else "Wet"}


@dataclass(frozen=True)
class Plan:
    start: str = "M"
    stops: tuple[tuple[int, str], ...] = ((21, "H"),)

    def wire(self):
        return {"start": self.start, "stops": [{"lap": lap, "tyre": tyre} for lap, tyre in self.stops]}

    def confirm(self, data, lap, total_laps=27, replace_future=False, allow_no_stop=False):
        start = data.get("start")
        stops = data.get("stops")
        if not isinstance(start, str) or start not in TYRES or not isinstance(stops, list):
            raise ValueError("잘못된 전략")
        if allow_no_stop and not stops:
            return Plan(start, tuple(s for s in self.stops if s[0] < lap))
        if not 1 <= len(stops) <= (8 if replace_future else 3 if lap == 0 else 1):
            raise ValueError("교체 횟수 확인")
        parsed = []
        lower = max(1, lap)
        for stop in stops:
            if not isinstance(stop, dict):
                raise TypeError("잘못된 교체")
            at, tyre = stop.get("lap"), stop.get("tyre")
            if type(at) is not int or not lower <= at < total_laps or not isinstance(tyre, str) or tyre not in TYRES:
                raise ValueError("교체 랩·타이어 확인")
            parsed.append((at, tyre))
            lower = at + 1
        if lap == 0:
            return Plan(start, tuple(parsed))
        future = [s for s in self.stops if s[0] >= lap]
        past = [s for s in self.stops if s[0] < lap]
        if replace_future:
            return Plan(self.start, tuple(past + parsed))
        return Plan(self.start, tuple(past + parsed + [s for s in future[1:] if s[0] > parsed[0][0]]))

