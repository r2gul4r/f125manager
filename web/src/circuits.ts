import gameTracks from '../../assets/game-circuits/tracks.json';
import paths from '../../assets/boxbox/image-paths.json?raw';
import raw from '../../assets/boxbox/2026.json?raw';

export interface Venue extends CircuitMap {
  round: number;
  lengthKm: number;
  rotation: number;
  coordinates: [number, number][];
  corners: [number, number, number, number][];
}
export interface CircuitMap {
  id:string;
  officialName:string;
  imageSeason?:number;
  reverse?:boolean;
}
const liveTracks:Record<number,CircuitMap> = gameTracks;
export const venues: Venue[] = JSON.parse(raw);
export const liveVenue = (id:number):CircuitMap|undefined => liveTracks[id];
export const suzuka = venues.find(venue => venue.id === 'suzuka')!;

// Each path is sampled at equal lap-distance intervals in the original 1252x704 diagram.
type Pixel = [number, number];
const diagramPaths: Record<string, Pixel[]> = JSON.parse(paths);
export function trackLayout(venue: CircuitMap) {
  const path = diagramPaths[venue.id];
  function location(phase: number) {
    const index = (venue.reverse ? (1-phase)%1 : phase) * path.length;
    const whole = Math.floor(index);
    const mix = index - whole;
    const [ax,ay] = path[whole % path.length];
    const [bx,by] = path[(whole+1) % path.length];
    return {x:ax+(bx-ax)*mix, y:ay+(by-ay)*mix};
  }
  return {location, path};
}
