import {compounds, type Compound} from './timing';
import './tyreBadge.css';

export function TyreBadge({compound}: {compound?:Compound|null}) {
  return <span className="tyre-badge" data-compound={compound}
    role={compound?'img':undefined} aria-label={compound ? compounds[compound] : undefined} aria-hidden={!compound}>
    {compound && <svg viewBox="-50 -50 100 100" aria-hidden="true" focusable="false">
      <text className="tyre-glyph" textAnchor="middle" y=".5cap">{compound}</text>
    </svg>}
  </span>;
}
