import { F1_DRIVER_NAMES } from '../constants/f1';
export function parseDriverName(rawName: string | undefined, defaultName: string, driverId?: number): string {
  let nameStr = '';
  if (typeof rawName === 'string') {
    const nullIdx = rawName.indexOf('\0');
    nameStr = (nullIdx !== -1 ? rawName.slice(0, nullIdx) : rawName).trim();
  }

  if (nameStr && nameStr.length > 0) {
    return nameStr;
  }

  if (driverId !== undefined && F1_DRIVER_NAMES[driverId]) {
    return F1_DRIVER_NAMES[driverId];
  }

  return defaultName;
}

