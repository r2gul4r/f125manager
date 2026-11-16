"""Load the production Windows shell against a running dashboard with a temporary profile."""

import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from subprocess import run

import webview

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_window import create_dashboard


def inspect(url, profile, first):
    window = create_dashboard(url)
    window.hidden = not first
    verified = []

    def check():
        from System import Func, Object
        try:
            frame = "document.querySelector('iframe').contentDocument"
            for _ in range(100):
                if window.evaluate_js(f"Boolean({frame}?.querySelector('#root > *'))"):
                    break
                time.sleep(.1)
            assert window.evaluate_js(f"Boolean({frame}.querySelector('#root > *'))")
            assert window.evaluate_js(f"[document,{frame}].every(d=>d.documentElement.translate===false)")
            form = window.native
            folder = form.Invoke(Func[Object](lambda: form.webview.CoreWebView2.Environment.UserDataFolder))
            assert Path(folder).resolve() == Path(profile).resolve()
            task = form.Invoke(Func[Object](lambda: form.webview.CoreWebView2.Profile.GetBrowserExtensionsAsync()))
            entries = task.GetAwaiter().GetResult()
            def extension_names():
                return ', '.join(str(entry.Name) for entry in entries)
            names = form.Invoke(Func[Object](extension_names))
            print("WebView2 profile extensions:", names, flush=True)
            assert not any(name in names.lower() for name in ("chatgpt","codex"))
            if first:
                assert window.evaluate_js(f"""(() => {{
                    const button = {frame}.querySelector('.race-state > strong + .header-refresh');
                    if (!button || button.nextElementSibling.id !== 'race-menu-button') return false;
                    const box = button.getBoundingClientRect();
                    if (box.width < 24 || Math.abs(box.width - box.height) > 1) return false;
                    button.click();
                    return true;
                }})()""")
                for _ in range(50):
                    if window.evaluate_js("""(() => {
                        const view = document.querySelector('iframe').contentWindow;
                        return view.performance.getEntriesByType('navigation')[0]?.type === 'reload'
                            && !!view.document.querySelector('.header-refresh');
                    })()"""):
                        break
                    time.sleep(.1)
                else:
                    raise AssertionError("Dashboard did not reload inside the native window")
                window.evaluate_js("localStorage.setItem('pitwall.display.layout','fit')")
                def enter_fullscreen():
                    core = form.webview.CoreWebView2
                    return core.CallDevToolsProtocolMethodAsync("Runtime.evaluate", json.dumps({
                        "expression":"document.documentElement.requestFullscreen()", "userGesture":True,
                        "awaitPromise":True
                    }))
                outcome = json.loads(form.Invoke(Func[Object](enter_fullscreen)).GetAwaiter().GetResult())
                assert "exceptionDetails" not in outcome, outcome
                for _ in range(50):
                    if form.is_fullscreen:
                        break
                    time.sleep(.1)
                assert form.is_fullscreen
                window.evaluate_js("document.exitFullscreen(); true")
                for _ in range(50):
                    if not form.is_fullscreen:
                        break
                    time.sleep(.1)
                assert not form.is_fullscreen
            else:
                assert window.evaluate_js("document.documentElement.dataset.layout") == "fit"
            verified.append(True)
        finally:
            window.destroy()

    webview.start(check, gui="edgechromium", private_mode=False, storage_path=profile)
    assert verified


if __name__ == "__main__":
    if len(sys.argv)==4:
        inspect(sys.argv[1], sys.argv[2], sys.argv[3]=="first")
    else:
        with TemporaryDirectory(ignore_cleanup_errors=True) as profile:
            for stage in ("first","reopen"):
                run([sys.executable, __file__, sys.argv[1], profile, stage], check=True, timeout=45)
        print("PASS native WebView2, translation opt-out, isolated profile, fullscreen and persistent fit layout")
