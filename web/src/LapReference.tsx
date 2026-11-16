export function LapReference({label,lap}:{label:string;lap:number}) {
  return <span className="lap-reference">{label} <strong>L{lap}</strong></span>;
}
