//! Track a flying lap from one timing-line crossing to the next.
use crate::live::u32_at;
use std::collections::BTreeMap;

#[derive(Clone)]
struct Crossing {
    lap: u8,
    tyre: u8,
    age: u8,
    surface: u8,
    mean_wear: Option<f32>,
    clean: bool,
    last_clock: f32,
    before_line: bool,
}
// player, slot, lap, visual compound, age at start, surface, lap ms, mean wheel wear change (percentage points)
type Sample = (bool, u8, u8, u8, u8, u8, u32, Option<f32>);
#[derive(Default, Clone)]
pub(crate) struct Practice {
    open: BTreeMap<u8, Crossing>,
    pub rows: BTreeMap<(u8, u8), (u32, Sample)>,
}
impl Practice {
    pub fn rewind(&mut self, target: u32) {
        self.open.clear();
        self.rows.retain(|_, (frame, _)| *frame <= target);
    }
    pub fn observe(
        &mut self,
        laps: &[u8],
        status: &[u8],
        session: &[u8],
        damage: Option<&[u8]>,
        modern: bool,
    ) {
        let player = laps[27];
        let clock = f32::from_bits(u32_at(laps, 15));
        let status_clock = f32::from_bits(u32_at(status, 15));
        let fresh = (clock - status_clock).abs() < 1.0;
        let surface = match session[29] {
            0..=2 => 0,
            3 => 1,
            4..=5 => 2,
            _ => 255,
        };
        let stride = if modern { 59 } else { 55 };
        for (i, (a, s)) in laps[29..]
            .as_chunks::<57>()
            .0
            .iter()
            .zip(status[29..].chunks_exact(stride))
            .enumerate()
        {
            let slot = i as u8;
            if (session[154] != 0 && slot != player) || a[45] != 2 || a[33] == 0 {
                self.open.remove(&slot);
                continue;
            }
            let lap = a[33];
            let tyre = s[26];
            let clean = fresh
                && surface != 255
                && session[153] == 0
                && !matches!(s[28], 3 | 4)
                && a[34] == 0
                && matches!(a[44], 1 | 4)
                && a[37] == 0
                && matches!(tyre, 7 | 8 | 16..=18);
            let entry = self.open.entry(slot).or_insert(Crossing {
                lap: 0,
                mean_wear: None,
                tyre,
                age: 0,
                surface,
                clean: false,
                last_clock: clock,
                before_line: false,
            });
            let contiguous = (0.0..=3.0).contains(&(clock - entry.last_clock));
            let distance = f32::from_bits(u32_at(a, 20));
            let before_line = distance < 0.0 && u32_at(a, 4) == 0;
            let flying_start = entry.before_line
                && (0.0..=200.0).contains(&distance)
                && u32_at(a, 4) < 1500
                && clean;
            if entry.lap != lap || flying_start {
                let mean_wear = damage
                    .filter(|d| (f32::from_bits(u32_at(d, 15)) - clock).abs() < 1.5)
                    .and_then(|d| {
                        let wheels =
                            [0, 4, 8, 12].map(|n| f32::from_bits(u32_at(d, 29 + 46 * i + n)));
                        wheels
                            .iter()
                            .all(|v| (0.0..=100.0).contains(v))
                            .then(|| wheels.iter().sum::<f32>() / 4.0)
                    });
                let time = u32_at(a, 0);
                let at_line = u32_at(a, 4) < 1500;
                if entry.clean
                    && clean
                    && contiguous
                    && entry.lap.checked_add(1) == Some(lap)
                    && at_line
                    && entry.tyre == tyre
                    && entry.surface == surface
                    && (30000..=600000).contains(&time)
                {
                    self.rows.insert(
                        (slot, entry.lap),
                        (
                            u32_at(laps, 19),
                            (
                                slot == player,
                                slot,
                                entry.lap,
                                tyre,
                                entry.age,
                                surface,
                                time,
                                mean_wear
                                    .zip(entry.mean_wear)
                                    .map(|(end, start)| end - start)
                                    .filter(|v| (0.0..=100.0).contains(v)),
                            ),
                        ),
                    );
                }
                *entry = Crossing {
                    lap,
                    tyre,
                    age: s[27],
                    mean_wear,
                    surface,
                    clean: clean && at_line,
                    last_clock: clock,
                    before_line,
                };
            } else {
                entry.clean &=
                    contiguous && clean && entry.tyre == tyre && entry.surface == surface;
                entry.last_clock = clock;
                entry.before_line = before_line;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uninterrupted_personal_laps_survive_a_rewind_only_before_its_target() {
        for modern in [false, true] {
            let mut fp = Practice::default();
            let mut session = [0; 155];
            session[154] = 1;
            let mut laps = [0; 29 + 57 * 2];
            let stride = if modern { 59 } else { 55 };
            let mut status = vec![0; 29 + stride * 2];
            // Two cars cross together. The second car is private in this session.
            for sec in 0..=150u32 {
                let clock = (sec as f32).to_le_bytes();
                laps[15..19].copy_from_slice(&clock);
                status[15..19].copy_from_slice(&clock);
                laps[19..23].copy_from_slice(&sec.to_le_bytes());
                for (i, c) in laps[29..].as_chunks_mut::<57>().0.iter_mut().enumerate() {
                    c[..4].copy_from_slice(&30000u32.to_le_bytes());
                    c[4..8].copy_from_slice(&((sec % 30) * 1000).to_le_bytes());
                    c[33] = (sec / 30 + 1) as u8;
                    c[44] = 1;
                    c[45] = 2;
                    c[37] = u8::from(sec == 40);
                    c[34] = u8::from(sec == 70);
                    let s = &mut status[29 + stride * i..];
                    s[26] = 17;
                    s[27] = (sec / 30) as u8;
                    s[5..9].copy_from_slice(&(25.0 - sec as f32 * 0.05).to_le_bytes());
                }
                session[153] = u8::from(sec == 100);
                fp.observe(&laps, &status, &session, None, modern);
            }
            assert_eq!(
                fp.rows.keys().copied().collect::<Vec<_>>(),
                [(0, 1), (0, 5)]
            );
            fp.rewind(75);
            assert_eq!(fp.rows.len(), 1);
            assert!(fp.open.is_empty());
        }
    }
}
