export const screens = {A:'Live Timing', B:'My Race', analysis:'Session Analysis'} as const;
export type Screen = keyof typeof screens;
export const screenOrder = Object.keys(screens) as Screen[];

// Wheel navigation follows the visible controls in the same order as the page.
export function operateTool(action: 'up'|'down'|'left'|'right'|'ok', scope='.tool-screen') {
  const controls = Array.from(document.querySelectorAll<HTMLElement>(
    scope+' :is(select,button,input[type="range"],summary):not(:disabled)'
  )).filter(el => el.getClientRects().length);
  if (!controls.length) return;
  const index = controls.indexOf(document.activeElement as HTMLElement);
  const step = action === 'up' || action === 'left' ? -1 : 1;
  if (action === 'up' || action === 'down' || index < 0) {
    const next = index < 0 ? (step < 0 ? controls.length-1 : 0) : (index + step + controls.length) % controls.length;
    controls[next].focus();
    return;
  }
  const control = controls[index];
  if (control instanceof HTMLSelectElement) {
    control.selectedIndex = (control.selectedIndex + step + control.length) % control.length;
    control.dispatchEvent(new Event('change', {bubbles:true}));
  } else if (control instanceof HTMLInputElement) {
    const increment = control.closest('.replay-tools') ? 1000 : 1;
    if (step > 0) control.stepUp(increment);
    else control.stepDown(increment);
    control.dispatchEvent(new Event('input', {bubbles:true}));
  } else if (action === 'ok') control.click();
}
