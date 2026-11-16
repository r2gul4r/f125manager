//! Observed passage gaps at the player's pit-exit lap distance.
use crate::pit_loss::distance;
use std::{collections::VecDeque, sync::Arc};

#[derive(Clone)]
struct Sample {
    clock: u64,
    metres: [Option<f64>; 24],
}

fn passage(a: &Sample, b: &Sample, slot: usize, line: f64) -> Option<u64> {
    let (x, y) = (a.metres[slot]?, b.metres[slot]?);
    let dt = b.clock.checked_sub(a.clock)?;
    // Bound interpolation to nearby packets and physically continuous movement.
    if dt == 0 || dt > 350 || y <= x || x > line || line > y || y - x > 2.0 + 0.12 * dt as f64 {
        return None;
    }
    Some(a.clock + ((line - x) / (y - x) * dt as f64).round() as u64)
}

#[derive(Clone)]
pub(crate) struct Exit {
    pub at: u64,
    frame: u32,
    pub rank: u8,
    pub ahead: Option<usize>,
    pub behind: Option<usize>,
    pub front_ms: Option<u64>,
    pub rear_ms: Option<u64>,
    rear_frame: Option<u32>,
    pub waiting: bool,
    clock: u64,
    line: f64,
}

#[derive(Clone, Default)]
pub(crate) struct ExitTiming {
    history: Arc<VecDeque<Arc<Sample>>>,
    previous: Option<Sample>,
    pub exits: Vec<Exit>,
}

impl ExitTiming {
    pub fn rewind(&mut self, target: u32) {
        self.history = Default::default();
        self.previous = None;
        self.exits.retain(|e| e.frame <= target);
        for e in &mut self.exits {
            e.waiting = false;
            if e.rear_frame.is_some_and(|f| f > target) {
                e.rear_ms = None;
                e.rear_frame = None;
            }
        }
    }

    pub fn observe(
        &mut self,
        rows: &[u8],
        clock: u64,
        length: u16,
        frame: u32,
        exit: Option<(u64, usize)>,
    ) {
        let mut now = Sample {
            clock,
            metres: [None; 24],
        };
        for (i, r) in rows.as_chunks::<57>().0.iter().enumerate() {
            if matches!(r[45], 2 | 3) && r[34] == 0 && r[46] == 0 && r[32] > 0 {
                now.metres[i] = distance(r, length);
            }
        }
        if self.previous.as_ref().is_some_and(|p| p.clock > clock) {
            self.history = Default::default();
            self.previous = None;
            if let Some(e) = self.exits.last_mut() {
                e.waiting = false;
            }
        }
        if let Some(e) = self.exits.last_mut().filter(|e| e.waiting) {
            let slot = e.behind.expect("waiting requires a rear neighbour");
            if let Some(at) = self
                .previous
                .as_ref()
                .and_then(|p| passage(p, &now, slot, e.line))
            {
                e.rear_ms = at.checked_sub(e.clock);
                e.rear_frame = Some(frame);
                e.waiting = false;
            } else if now.metres[slot].is_none_or(|d| d >= e.line) || exit.is_some() {
                e.waiting = false;
            }
        }
        if let Some((at, player)) = exit {
            let me = &rows[player * 57..];
            let neighbour = |rank| {
                rows.as_chunks::<57>()
                    .0
                    .iter()
                    .position(|r| rank > 0 && r[32] == rank && matches!(r[45], 2 | 3))
            };
            let (ahead, behind) = (neighbour(me[32] - 1), neighbour(me[32] + 1));
            let line = distance(me, length);
            let same_lap = |i: usize| rows[i * 57 + 33] == me[33];
            let front_ms = ahead.filter(|&i| same_lap(i)).and_then(|i| {
                let line = line?;
                let mut next = &now;
                if next.metres[i]? < line {
                    return None;
                }
                if next.metres[i]? == line {
                    return Some(0);
                }
                for prev in self.history.iter().rev() {
                    if prev.metres[i]? <= line {
                        return clock.checked_sub(passage(prev, next, i, line)?);
                    }
                    next = prev;
                }
                None
            });
            let rear = behind.filter(|&i| same_lap(i)).and_then(|i| now.metres[i]);
            let coincident = line.zip(rear).is_some_and(|(l, d)| l == d);
            self.exits.push(Exit {
                at,
                frame,
                rank: me[32],
                ahead,
                behind,
                front_ms,
                rear_ms: coincident.then_some(0),
                rear_frame: coincident.then_some(frame),
                waiting: line.zip(rear).is_some_and(|(l, d)| d < l),
                clock,
                line: line.unwrap_or_default(),
            });
        }
        // Ten observations per second suffice to bracket an earlier front-car
        // crossing. The pending rear car uses every accepted LapData packet.
        if self
            .history
            .back()
            .is_none_or(|p| clock.saturating_sub(p.clock) >= 100)
        {
            let history = Arc::make_mut(&mut self.history);
            while history
                .front()
                .is_some_and(|p| clock.saturating_sub(p.clock) > 180_000)
            {
                history.pop_front();
            }
            history.push_back(Arc::new(now.clone()));
        }
        self.previous = Some(now);
    }
}
#[cfg(test)]
mod tests {
    use super::*;

    fn packet(front: f32, back: f32) -> Vec<u8> {
        let mut rows = vec![0; 57 * 3];
        for (i, (row, d)) in rows
            .as_chunks_mut::<57>()
            .0
            .iter_mut()
            .zip([front, 100., back])
            .enumerate()
        {
            row[20..24].copy_from_slice(&d.to_le_bytes());
            row[32] = i as u8 + 1;
            row[33] = 2;
            row[45] = 2;
        }
        rows
    }
    #[test]
    fn interpolates_past_and_future_and_freezes_the_exit_order() {
        let mut m = ExitTiming::default();
        m.observe(&packet(95., 75.), 100, 5000, 1, None);
        m.observe(&packet(105., 85.), 200, 5000, 2, None);
        m.observe(&packet(115., 95.), 300, 5000, 3, Some((800, 1)));
        assert_eq!(m.exits[0].front_ms, Some(150));
        assert!(m.exits[0].waiting);
        let mut later = packet(125., 105.);
        later[32] = 3;
        later[2 * 57 + 32] = 1;
        m.observe(&later, 400, 5000, 4, None);
        assert_eq!((m.exits[0].behind, m.exits[0].rear_ms), (Some(2), Some(50)));
        m.rewind(3);
        assert_eq!((m.exits[0].rear_ms, m.exits[0].waiting), (None, false));
        m.rewind(2);
        assert!(m.exits.is_empty());
    }
    #[test]
    fn missing_crossing_and_lapped_car_have_no_measured_gap() {
        let mut m = ExitTiming::default();
        let mut at_exit = packet(115., 95.);
        at_exit[33] = 3;
        m.observe(&at_exit, 1000, 5000, 5, Some((9000, 1)));
        m.observe(&packet(140., 125.), 1600, 5000, 6, None);
        assert_eq!(
            (m.exits[0].front_ms, m.exits[0].rear_ms, m.exits[0].waiting),
            (None, None, false)
        );
    }
}
