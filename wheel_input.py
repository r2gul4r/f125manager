"""Raw SDL button and POV edges shared by the Qt demo and web receiver."""
import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
import pygame


class WheelInput:
    def __init__(self):
        self.devices = {}
        self.held = set()
        self.error = ""
        try:
            pygame.display.init()
            pygame.joystick.init()
            for index in range(pygame.joystick.get_count()):
                self.add(index)
        except pygame.error as exc:
            self.error = str(exc)

    def add(self, index):
        joy = pygame.joystick.Joystick(index)
        self.devices[joy.get_instance_id()] = joy

    def edge(self, iid, guid, control, pressed):
        physical = (iid, control)
        if not pressed:
            self.held.discard(physical)
        elif physical not in self.held:
            self.held.add(physical)
            return f"{guid}/{control}"
        return None

    def poll(self):
        keys = []
        if self.error:
            return keys
        try:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED:
                    self.add(event.device_index)
                elif event.type == pygame.JOYDEVICEREMOVED:
                    self.devices.pop(event.instance_id, None)
                    self.held = {k for k in self.held if k[0] != event.instance_id}
                elif event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, pygame.JOYHATMOTION):
                    joy = self.devices.get(event.instance_id)
                    if joy is None:
                        continue
                    if event.type == pygame.JOYHATMOTION:
                        x, y = event.value
                        controls = [(f"hat{event.hat}:{side}", on) for side, on in
                                    (("up", y > 0), ("down", y < 0), ("left", x < 0), ("right", x > 0))]
                    else:
                        controls = [(f"button{event.button + 1}", event.type == pygame.JOYBUTTONDOWN)]
                    for control, pressed in controls:
                        key = self.edge(event.instance_id, joy.get_guid(), control, pressed)
                        if key:
                            keys.append(key)
        except pygame.error as exc:
            self.error = str(exc)
        return keys

    def description(self):
        return ", ".join(j.get_name() for j in self.devices.values()) or self.error or "연결된 휠 없음"
