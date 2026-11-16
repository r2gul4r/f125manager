"""UDP 3's spoken turn shares the GP thread and publishes validated choices to open views."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_live_udp import packets

import f125_core
import gp_advisor
import server
from gp_advisor import AdvisorView, GpAdvisor


def test_radio_follow_up_and_revision(monkeypatch, tmp_path):
    import socket
    import time

    receiver = f125_core.UdpReceiver("127.0.0.1", 0, tmp_path, 20000)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            for p in packets(2026).values():
                sender.sendto(p, ("127.0.0.1", receiver.port))
        until = time.monotonic() + 3
        while receiver.snapshot()["accepted"] < 7 and time.monotonic() < until:
            time.sleep(0.01)
        raw = receiver.snapshot()
    finally:
        receiver.close()
    raw["ageMs"] = 0
    service = GpAdvisor(tmp_path)
    monkeypatch.setattr(server.app.state, "advisor", service, raising=False)
    monkeypatch.setattr(server.app.state, "pit_ms", 20000, raising=False)
    mic = SimpleNamespace(turn_key="fixture")
    monkeypatch.setattr(server.app.state, "microphone", mic, raising=False)
    monkeypatch.setattr(server, "native_snapshot", lambda: raw)
    screen = AdvisorView(service)
    frame = screen.render(raw)
    picks = {
        k: {"lap": n, "tyre": "H", "reason": "fixture"}
        for k, n in zip("ABC", (26, 24, 28))
    }
    observations = []

    class SDK:
        def __init__(self, config):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def thread_start(self, **opts):
            assert not observations
            self.id = "weekend"
            return self

        async def thread_resume(self, ident, **opts):
            assert ident == "weekend"
            self.id = ident
            return self

        async def run(self, prompt, **opts):
            facts = json.loads(prompt)
            observations.append(facts)
            assert facts["canRevise"] and facts["field"] and facts["predictedPitExits"]
            if facts["driverQuestion"] == "late":
                mic.turn_key = None
            return SimpleNamespace(
                error=None,
                final_response=json.dumps(
                    {
                        "speech": "Copy.",
                        "plans": None if len(observations) == 1 else picks,
                    }
                ),
            )

    monkeypatch.setattr(gp_advisor, "AsyncCodex", SDK)

    def turn(q):
        return asyncio.run(
            server.live_radio(
                {
                    "type": "radio",
                    "key": "fixture",
                    "session": frame["session"],
                    "question": q,
                    "wingDamage": [10, 0],
                },
                raw,
                frame,
            )
        )

    assert turn("What if we stay out?") == {"speech": "Copy."}
    assert "id" not in screen.render(raw)["advisor"]
    result = turn("Then revise our plans around that.")
    updated = screen.render(raw)
    assert updated["advisor"]["id"] == result["proposalId"]
    assert [
        (p["stop"]["lap"], p["stop"]["tyre"]) for p in updated["forecast"]["plans"]
    ] == [(26, "H"), (24, "H"), (28, "H")]
    assert not service.saved_plan(gp_advisor.gp_key(raw, False), frame["session"])
    with pytest.raises(ValueError, match="expired"):
        turn("late")
    assert screen.render(raw)["advisor"]["id"] == result["proposalId"]

    # Exercise the actual worker transport with a dashboard already subscribed.
    observations.clear()
    monkeypatch.setenv("F125_UDP_PORT", "0")
    monkeypatch.setenv("F125_RECORDING_DIR", str(tmp_path / "transport"))
    monkeypatch.delenv("F125_HANDOFF_RECORDING", raising=False)
    with TestClient(server.app) as client:
        server.app.state.microphone.turn_key = "fixture"
        with (
            client.websocket_connect("/ws/live") as dashboard,
            client.websocket_connect("/ws/live") as voice,
        ):
            assert "id" not in dashboard.receive_json()["frame"]["advisor"]
            session = voice.receive_json()["frame"]["session"]
            for question in ("Can I win?", "Revise the strategies for that."):
                voice.send_json(
                    {
                        "type": "radio",
                        "key": "fixture",
                        "session": session,
                        "question": question,
                    }
                )
                for _ in range(40):
                    packet = voice.receive_json()
                    if "radio" in packet:
                        break
                assert packet["radio"]["speech"] == "Copy."
            for _ in range(40):
                current = dashboard.receive_json()["frame"]
                if current["advisor"].get("id") == packet["radio"]["proposalId"]:
                    break
            assert [p.get("codexReason") for p in current["forecast"]["plans"]] == [
                "fixture"
            ] * 3
