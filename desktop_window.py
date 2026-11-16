"""Standalone Windows dashboard using the system WebView2 runtime."""

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import webview


def create_dashboard(url: str):
    address = urlsplit(url)
    if address.scheme != "http" or address.hostname != "127.0.0.1" or not address.port:
        raise ValueError("Expected a loopback dashboard address")
    window = webview.create_window("F1 25 · Race Engineer",
                                   f"http://127.0.0.1:{address.port}/desktop.html",
                                   maximized=True, background_color="#111115")

    def attach_fullscreen_handler():
        form = window.native

        def fullscreen_changed(core, _):
            if core.ContainsFullScreenElement != form.is_fullscreen:
                window.toggle_fullscreen()

        def initialized(control, event):
            if event.IsSuccess:
                control.CoreWebView2.ContainsFullScreenElementChanged += fullscreen_changed

        form.webview.CoreWebView2InitializationCompleted += initialized

    window.events.before_show += attach_fullscreen_handler
    return window


if __name__ == "__main__":
    create_dashboard(sys.argv[1])
    profile = Path(os.environ["LOCALAPPDATA"]) / "F125Manager" / "WebView2"
    webview.start(gui="edgechromium", private_mode=False, storage_path=str(profile))
