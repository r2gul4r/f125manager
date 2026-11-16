import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app import Dashboard, STYLE, Mapping
from race import snapshot,briefing
from wheel import Wheel

class Demo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion");cls.app.setStyleSheet(STYLE)
    def setUp(self):
        self.w=Dashboard();self.w.timer.stop();self.w.resize(1920,1080);self.w.show()
        self.app.processEvents()
    def tearDown(self):
        self.w.wheel.timer.stop();self.w.close();self.w.deleteLater();self.app.processEvents()
    def key(self,k):
        QTest.keyClick(self.w,k);self.app.processEvents()
    def test_rank_map_and_timing_source(self):
        w=self.w;self.assertEqual(len(w.tower.indices()),22);self.assertEqual(w.stats[0][1].text(),"P8")
        self.assertIn("4랩 뒤",w.chase.text())
        w.scene_to(2);self.assertIn("벌어지는",w.chase.text())
        w.scene_to(3);w.seconds=10;w.render()
        self.assertIs(w.circuit.frame,w.tower.frame);self.assertIs(w.local.frame,w.circuit.frame)
        self.assertEqual(w.stats[0][1].text(),"P7");self.assertIn("HAM",w.stats[1][0].text())
        self.assertEqual(w.local.indices(),[4,5,6,7,8]);self.assertIn("분석 대기",w.chase.text())
        for i in (4,5):
            w.scene_to(i);self.assertIn("분석 대기",w.strategy.buttons[0].text());self.assertIn("분석 대기",w.defend.text())
        w.local.frame=replace(w.frame,cars=tuple(sorted(w.frame.cars,key=lambda c:c.code!="YOU")))
        self.assertEqual(w.local.indices(),[0,1,2])
    def test_preview_confirm_cancel_and_dial(self):
        w=self.w;self.key(Qt.Key_2);self.assertEqual(w.pages.currentIndex(),1)
        self.key(Qt.Key_Down);self.assertEqual(w.strategy.plan.stops,((21,"H"),))
        w.act("B");self.assertEqual(w.strategy.cursor,1)
        self.key(Qt.Key_Escape);self.assertEqual(w.strategy.plan.stops,((21,"H"),))
        self.key(Qt.Key_Down);self.key(Qt.Key_Return);self.assertEqual(w.strategy.plan.stops,((19,"H"),))
        self.key(Qt.Key_Down);self.key(Qt.Key_Return);self.assertTrue(w.strategy.edit)
        self.key(Qt.Key_Right);self.key(Qt.Key_Down);self.key(Qt.Key_Right);self.key(Qt.Key_Down);self.key(Qt.Key_Return)
        self.assertEqual(w.strategy.plan.stops,((20,"I"),))
        self.key(Qt.Key_1);self.key(Qt.Key_2);self.assertEqual(w.strategy.plan.stops,((20,"I"),))
    def test_grid_multistint(self):
        w=self.w;w.scene_to(0);w.act("B");s=w.strategy
        for k in ("ok","left","down","down","down","ok"):w.act(k)
        self.assertEqual(len(s.draft),2);self.assertEqual(len(s.plan.stops),1)
        while s.editfields()[s.cursor][0]!="save":w.act("down")
        w.act("ok");self.assertEqual(s.plan.start,"S");self.assertEqual(s.plan.stops,((21,"H"),(24,"M")))
        self.assertEqual(w.frame.cars[w.frame.player].tyre,"S");self.assertEqual(w.ring.text(),"S")
        w.scene_to(1);self.assertEqual(len(s.plan.stops),2)
    def test_map_repeated_edges_and_persistence(self):
        w=self.w;wheel=w.wheel
        with tempfile.TemporaryDirectory() as d:
            wheel.file=Path(d)/"wheel.json";wheel.bindings={}
            m=Mapping(wheel,w);m.listen("B");wheel.edge(31,"fixture","button56",True)
            self.assertEqual(w.pages.currentIndex(),0);m.accept()
            wheel.edge(31,"fixture","button56",False);wheel.edge(31,"fixture","button56",True)
            self.assertEqual(w.pages.currentIndex(),1)
            wheel.assign("fixture/button56","down");wheel.edge(31,"fixture","button56",True)
            self.assertEqual(w.strategy.cursor,0)
            wheel.edge(31,"fixture","button56",False);wheel.edge(31,"fixture","button56",True)
            self.assertEqual(w.strategy.cursor,1);self.assertIn("fixture/button56",wheel.file.read_text())
            restored=Wheel(wheel.file);restored.timer.stop()
            self.assertEqual(restored.bindings["fixture/button56"],"down")
    def test_render_and_geometry(self):
        w=self.w
        for i,name in enumerate(("A-live","B-race")):
            w.tab(i);self.app.processEvents();im=w.grab()
            self.assertEqual(im.width(),1920)
            if os.environ.get("F125_PREVIEWS"):
                self.assertTrue(im.save(str(Path(os.environ["F125_PREVIEWS"])/(name+".png"))))
        self.assertGreater(w.tower.height()/23,30);self.assertGreater(w.local.height()/6,40)

    @unittest.skipUnless(os.name=="nt","Windows SDL package integration")
    def test_sdl_virtual_wheel(self):
        import ctypes as ct
        import pygame
        lib=ct.CDLL(str(Path(pygame.__file__).with_name("SDL2.dll")))
        lib.SDL_JoystickOpen.restype=ct.c_void_p
        lib.SDL_JoystickSetVirtualButton.argtypes=[ct.c_void_p,ct.c_int,ct.c_uint8]
        lib.SDL_JoystickSetVirtualHat.argtypes=[ct.c_void_p,ct.c_int,ct.c_uint8]
        lib.SDL_JoystickClose.argtypes=[ct.c_void_p]
        wheel=self.w.wheel;idx=lib.SDL_JoystickAttachVirtual(2,0,64,1)
        self.assertGreaterEqual(idx,0);handle=lib.SDL_JoystickOpen(idx);self.assertTrue(handle)
        try:
            wheel.poll();joy=pygame.joystick.Joystick(idx);guid=joy.get_guid()
            wheel.bindings={f"{guid}/button56":"B",f"{guid}/hat0:down":"down",f"{guid}/button2":"ok",f"{guid}/button1":"A"}
            def move(setter,*args):
                self.assertEqual(setter(handle,*args),0);lib.SDL_JoystickUpdate();wheel.poll()
            move(lib.SDL_JoystickSetVirtualButton,55,1)
            self.assertEqual(self.w.pages.currentIndex(),1)
            move(lib.SDL_JoystickSetVirtualHat,0,4)
            self.assertEqual(self.w.strategy.cursor,1)
            move(lib.SDL_JoystickSetVirtualButton,1,1)
            self.assertEqual(self.w.strategy.plan.stops,((19,"H"),))
            move(lib.SDL_JoystickSetVirtualButton,0,1)
            self.assertEqual(self.w.pages.currentIndex(),0)
        finally:
            lib.SDL_JoystickClose(handle);lib.SDL_JoystickDetachVirtual(idx);wheel.poll()

if __name__=="__main__":unittest.main()
