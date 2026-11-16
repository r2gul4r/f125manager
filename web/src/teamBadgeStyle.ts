import type {CSSProperties} from 'react';

// Timing-feed colour -> reference badge: rank fill, rank text, code fill, code text.
// Rank fills are the most frequent interior pixels across teammates in the supplied image.
// White interiors are normalized to white. The active Aston Martin palette uses a bright green and a white nameplate.
const referenceBadges: Record<string, readonly [string, string, string, string]> = {
  '#4781D7': ['#0383FF', '#FFFFFF', '#FFFFFF', '#206BC3'], // Red Bull
  '#ED1131': ['#FF0000', '#FFFFFF', '#FFFFFF', '#AB0102'], // Ferrari
  '#00D7B6': ['#00F3BF', '#001813', '#001813', '#00F3BF'], // Mercedes
  '#F47600': ['#FC6800', '#1E0900', '#1E0900', '#FC6800'], // McLaren
  '#6C98FF': ['#FFFFFF', '#181818', '#181818', '#FFFFFF'], // Racing Bulls
  '#00A1E8': ['#FF00FF', '#FFFFFF', '#FFFFFF', '#A507A7'], // Alpine
  '#F50537': ['#FE6A6A', '#20090C', '#20090C', '#FE6A6A'], // Audi
  '#9C9FA2': ['#A3A7AB', '#0F1110', '#0F1110', '#A3A7AB'], // Haas
  '#1868DB': ['#000B68', '#FFFFFF', '#FFFFFF', '#000030'], // Williams
  '#909090': ['#FFE102', '#1B1500', '#1B1500', '#FFE102'], // Cadillac
  '#229971': ['#00C987', '#071910', '#FFFFFF', '#006B48'], // Aston Martin
};

export function teamBadgeStyle(team = '#909090', retired = false): CSSProperties {
  const color = team.toUpperCase();
  if (retired && color === '#229971') {
    // Sampled directly from the two dimmed Aston Martin badges in the reference.
    return {'--team': '#01372B', '--team-ink': '#575958', '--code-fill': '#575958', '--code-ink': '#0B2F27'} as CSSProperties;
  }
  const tone = (value: string) => retired ? `color-mix(in srgb, ${value} 34%, black)` : value;
  const badge = referenceBadges[color];
  if (badge) {
    const [fill, ink, codeFill, codeInk] = badge;
    return {'--team': tone(fill), '--team-ink': tone(ink), '--code-fill': tone(codeFill),
      '--code-ink': tone(codeInk), '--code-weight': codeFill === '#FFFFFF' ? 900 : 800} as CSSProperties;
  }
  const linear = (offset: number) => {
    const channel = parseInt(team.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  };
  const luminance = 0.2126 * linear(1) + 0.7152 * linear(3) + 0.0722 * linear(5);
  const ink = (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) ? '#000' : '#fff';
  return {'--team': tone(team), '--team-ink': tone(ink), '--code-weight': ink === '#fff' ? 900 : 800} as CSSProperties;
}
