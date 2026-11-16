import {useEffect, useState} from 'react';

interface Model {id:string; label:string; default:string; efforts:string[]}
interface Preferences {model:string|null; effort:string|null; models:Model[]}

export function CodexSettings() {
  const [open,setOpen]=useState(false);
  const [settings,setSettings]=useState<Preferences|null>(null);
  const [message,setMessage]=useState('');
  const [saving,setSaving]=useState(false);
  useEffect(()=>{
    if (!open) return;
    const controller=new AbortController();
    setMessage('');
    fetch('/api/settings/codex',{signal:controller.signal}).then(async response=>{
      if (!response.ok) throw new Error();
      setSettings(await response.json());
    }).catch(()=>{if (!controller.signal.aborted) setMessage('모델 목록을 불러오지 못했어. 다시 열어서 재시도해.')});
    return ()=>controller.abort();
  },[open]);
  async function save(model:string|null, effort:string|null) {
    if (!settings) return;
    setSaving(true);
    try {
      const response=await fetch('/api/settings/codex',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,effort})});
      if (!response.ok) throw new Error();
      setSettings({...settings,model,effort});
      setMessage('다음 전략 요청부터 적용됨');
    } catch {setMessage('설정을 저장하지 못했어. 다시 선택해.')}
    finally {setSaving(false)}
  }
  const selected=settings?.models.find(m=>m.id===settings.model);
  return <details onToggle={e=>setOpen(e.currentTarget.open)}><summary>Codex strategy</summary>
    {settings ? <div className="display-settings">
      <label>Model <select aria-label="Model" disabled={saving} value={settings.model??''} onChange={e=>{
        const m=settings.models.find(m=>m.id===e.target.value);
        void save(m?.id??null,m?.default??null);
      }}><option value="">Codex default</option>{settings.models.map(m=><option key={m.id} value={m.id}>{m.label}</option>)}</select></label>
      <label>Reasoning effort <select aria-label="Reasoning effort" disabled={saving || !selected} value={settings.effort??''} onChange={e=>void save(settings.model,e.target.value)}>
        {!selected && <option value="">Codex default</option>}{selected?.efforts.map(e=><option key={e}>{e}</option>)}
      </select></label>
    </div> : !message && <small>Loading models…</small>}
    {message && <small role="status">{message}</small>}
  </details>;
}
