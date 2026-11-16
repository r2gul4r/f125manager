import type {Frame} from './timing';

type Zone = NonNullable<Frame['marshalZones']>[number];
type Point = [number,number];

export function yellowIntervals(zones:Zone[]): [number,number][] {
  const ranges:[number,number][] = [];
  zones.forEach(([start,flag],i)=>{
    if (flag!==3) return;
    const last=i===zones.length-1;
    const end=last ? 1 : zones[i+1][0];
    if (end>start) ranges.push([start,end]);
    // The last marshal post owns the interval through lap zero to the first post.
    if (last && zones[0][0]>0) ranges.push([0,zones[0][0]]);
  });
  return ranges;
}

function sectorAt(data:Uint8ClampedArray,p:number) {
  const r=data[p],g=data[p+1],b=data[p+2];
  return r>=g && r>=b ? 0 : g>=b ? 1 : 2;
}

// Match the original warning rim to lap distance once per circuit. Project onto
// segments (not sample points), including fractional positions at either end.
export function indexRim(image:ImageData, path:Point[], reverse:boolean) {
  const {width,height,data}=image;
  const scores=new Float32Array(width*height).fill(Infinity);
  const phases=new Float64Array(width*height);
  const used:number[]=[];
  // Source masks were generated from edge pixels within 31 map units of the path.
  const radius=32;
  path.forEach(([x,y],i)=>{
    const [endX,endY]=path[(i+1)%path.length];
    const dx=endX-x,dy=endY-y,length=Math.hypot(dx,dy);
    if (!length) return;
    // Timing-sector ink disambiguates nearby parallel roads and Suzuka's crossover.
    // Yellow boundaries themselves always come from the UDP marshal posts.
    const votes=[0,0,0];
    for (let n=-radius;n<=radius;n++) {
      const col=Math.floor((x+endX)/2-n*dy/length),row=Math.floor((y+endY)/2+n*dx/length);
      if (col<0 || row<0 || col>=width || row>=height) continue;
      const offset=4*(row*width+col);
      votes[sectorAt(data,offset)]+=data[offset+3];
    }
    const sector=votes.indexOf(Math.max(...votes));
    const left=Math.max(0,Math.floor(Math.min(x,endX)-radius)),right=Math.min(width-1,Math.ceil(Math.max(x,endX)+radius));
    const top=Math.max(0,Math.floor(Math.min(y,endY)-radius)),bottom=Math.min(height-1,Math.ceil(Math.max(y,endY)+radius));
    for(let row=top;row<=bottom;row++) {
      for(let col=left;col<=right;col++) {
        const p=row*width+col,offset=p*4;
        if (!data[offset+3]) continue;
        const u=col+.5-x,v=row+.5-y;
        const t=Math.max(0,Math.min(1,(u*dx+v*dy)/(length*length)));
        const distance=(u-t*dx)**2+(v-t*dy)**2;
        if(distance>radius**2) continue;
        const score=distance+(sectorAt(data,offset)===sector ? 0 : radius**2);
        if(score>=scores[p]) continue;
        if(scores[p]===Infinity) used.push(p);
        scores[p]=score;
        const fraction=(i+t)/path.length;
        phases[p]=(reverse ? 1-fraction : fraction)%1;
      }
    }
  });
  return (ranges:[number,number][])=>{
    const output=new ImageData(width,height);
    for(const p of used) {
      if(ranges.some(([a,b])=>a<=phases[p] && phases[p]<b)) {
        output.data[p*4]=255;
        output.data[p*4+3]=data[p*4+3];
      }
    }
    return output;
  };
}

