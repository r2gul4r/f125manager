import {useEffect, useState} from 'react';

export function DisplaySettings() {
  const shell = window.frameElement?.matches('[data-desktop-shell]') ? window.frameElement.ownerDocument : null;
  const display = shell ?? document;
  const [fullscreen, setFullscreen] = useState(Boolean(display.fullscreenElement));
  const [layout, setLayout] = useState(shell?.documentElement.dataset.layout === 'fit' ? 'fit' : 'fill');
  const [error, setError] = useState('');

  useEffect(() => {
    const sync = () => setFullscreen(Boolean(display.fullscreenElement));
    display.addEventListener('fullscreenchange', sync);
    return () => display.removeEventListener('fullscreenchange', sync);
  }, [display]);

  async function changeMode(mode: string) {
    setError('');
    try {
      if (mode === 'fullscreen') await display.documentElement.requestFullscreen();
      else await display.exitFullscreen();
    } catch {
      setError('화면 모드를 바꾸지 못했어. 브라우저의 전체화면 권한을 확인해.');
    }
  }

  function changeLayout(value: string) {
    if (!shell) return;
    shell.documentElement.dataset.layout = value;
    setLayout(value);
    try { localStorage.setItem('pitwall.display.layout', value); }
    catch { setError('화면 맞춤 설정은 이번 창에만 적용됨.'); }
  }

  return <section aria-label="Display"><h3>Display</h3>
    <div className="display-settings">
      <label>Window mode <select aria-label="Window mode" value={fullscreen ? 'fullscreen' : 'windowed'} onChange={e=>void changeMode(e.target.value)}>
        <option value="windowed">Windowed</option>
        <option value="fullscreen" disabled={!display.fullscreenEnabled}>Fullscreen</option>
      </select></label>
      {shell && <label>Layout <select aria-label="Layout" value={layout} onChange={e=>changeLayout(e.target.value)}>
        <option value="fill">Fill window</option><option value="fit">Fit 16:9</option>
      </select></label>}
    </div>
    {error && <p lang="ko" role="alert">{error}</p>}
  </section>;
}
