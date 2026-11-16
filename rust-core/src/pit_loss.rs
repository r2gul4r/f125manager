use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, sync::Arc};

use crate::pit_rules::{minimum_delay_ms, Profile};

pub(crate) type History = Arc<Vec<Observation>>;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub(crate) enum Work {
    Tyres,
    FrontWing,
    RivalTyres,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub(crate) struct Condition {
    pub format: u16,
    pub track: i8,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wet: Option<bool>,
    pub profile: Profile,
    pub safety: u8,
    pub work: Work,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub(crate) struct Observation {
    // Race UID and time at which the archived recording became available.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub origin: Option<(u64, u64)>,
    pub condition: Condition,
    pub service: u16,
    pub loss: Option<u32>,
}

#[derive(Default)]
pub(crate) struct Group {
    pub(crate) samples: Vec<Observation>,
    upper: u32,
}

impl Group {
    pub fn includes(&self, duration: u16) -> bool {
        u32::from(duration) <= self.upper
    }

    pub fn totals(&self, loss: bool) -> Vec<u32> {
        self.samples
            .iter()
            .filter(|s| self.includes(s.service))
            .filter_map(|s| {
                if loss {
                    s.loss
                } else {
                    Some(u32::from(s.service))
                }
            })
            .collect()
    }
}

// Refit from raw pairs whenever the observed cohort changes. Even a slow first
// stop can leave the average once comparable, faster evidence becomes available.
pub(crate) fn groups(samples: impl Iterator<Item = Observation>) -> BTreeMap<Condition, Group> {
    let mut groups = BTreeMap::<Condition, Group>::new();
    for sample in samples {
        groups
            .entry(sample.condition)
            .or_default()
            .samples
            .push(sample);
    }
    for group in groups.values_mut() {
        let mut times: Vec<u32> = group.samples.iter().map(|s| u32::from(s.service)).collect();
        times.sort_unstable();
        let floor = minimum_delay_ms();
        // Distinct slower visits must not widen the spread of an otherwise
        // repeatable service. Equal support favors the faster cluster because
        // delays add time. The upper fence still admits all shorter stops.
        let mut typical: &[u32] = &[];
        for cluster in times.chunk_by(|a, b| b - a <= floor) {
            if cluster.len() > typical.len() {
                typical = cluster;
            }
        }
        let mid = (typical.len() - 1) / 2;
        let median = typical[mid];
        let mut deviations: Vec<_> = typical.iter().map(|t| t.abs_diff(median)).collect();
        let mad = *deviations.select_nth_unstable(mid).1;
        group.upper = median + floor.max(4 * mad);
    }
    groups
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn transit_loss_requires_two_continuous_on_track_references() {
        fn rows(t: u64, invalid_peer: bool) -> Vec<u8> {
            let mut rows = vec![0; 57 * 3];
            for (slot, r) in rows.chunks_exact_mut(57).enumerate() {
                let d = if slot == 0 {
                    100.0 + t as f32 * 0.01
                } else {
                    80.0 - 4.0 * slot as f32 + t as f32 * 0.05
                };
                r[20..24].copy_from_slice(&d.to_le_bytes());
                r[32] = (slot + 2) as u8;
                r[33] = 3;
                r[45] = 2;
                if slot == 0 {
                    r[46] = u8::from(t < 4000);
                    r[49..51].copy_from_slice(&2000u16.to_le_bytes());
                } else if invalid_peer && slot == 2 && t == 1000 {
                    r[34] = 2;
                }
            }
            rows
        }
        for invalid in [false, true] {
            let mut visit = Visit::start(&rows(0, invalid), 0, 0, 5000);
            for t in (100..=4000).step_by(100) {
                let r = rows(t, invalid);
                visit.update(&r, &r[..57], t);
            }
            let end = rows(4000, invalid);
            assert_eq!(
                visit.loss(&end, &end[..57], 4000),
                if invalid { None } else { Some((3200, 2)) }
            );
        }
    }

    #[test]
    fn long_first_stop_is_reassessed_and_cannot_inflate_the_loss() {
        let condition = Condition {
            format: 2026,
            track: 3,
            wet: Some(false),
            safety: 0,
            work: Work::FrontWing,
            profile: Profile::from_session(&[0; 753]).unwrap(),
        };
        let values = [(14000, 40000), (8000, 26000), (8016, 27000), (8000, 26000)];
        for n in 1..=values.len() {
            let group = &groups(values[..n].iter().map(|&(service, loss)| Observation {
                origin: None,
                condition,
                service,
                loss: Some(loss),
            }))[&condition];
            assert_eq!(group.includes(14000), n == 1);
            if n == 4 {
                assert_eq!(average(&group.totals(false)), Some((8005, 3)));
                assert_eq!(average(&group.totals(true)), Some((26333, 3)));
            }
        }
    }
}

pub(crate) fn average(values: &[u32]) -> Option<(u32, usize)> {
    let count = values.len();
    if count == 0 {
        return None;
    }
    let sum: u64 = values.iter().map(|v| u64::from(*v)).sum();
    Some((((sum + count as u64 / 2) / count as u64) as u32, count))
}

// Same offsets in the 2025 and 2026 CarDamage packets, left and right front first.
pub(crate) type Damage = [u8; 6];
pub(crate) const PARTS: [&str; 6] = [
    "frontLeft",
    "frontRight",
    "rearWing",
    "floor",
    "diffuser",
    "sidepod",
];
// Each forecast is (rank, total loss in ms, matching sample count), tyres first.
pub(crate) type Scenarios = [(u8, u32, usize); 2];

#[derive(Default, Clone, Copy)]
pub(crate) struct Equipment {
    pub damage: Option<(u32, Damage)>,
    pub tyre: Option<(u32, u8, u8)>,
    pub fitted: Option<(u32, u8)>,
    pub wear: Option<(u32, [f32; 4])>,
}

impl Equipment {
    pub fn changed_tyres(self, exit: Self) -> Option<bool> {
        let set = self.fitted.zip(exit.fitted).filter(|(a, b)| b.0 > a.0);
        let status = self.tyre.zip(exit.tyre).filter(|(a, b)| b.0 > a.0);
        let wear = self.wear.zip(exit.wear).filter(|(a, b)| b.0 > a.0);
        if set.is_some_and(|(a, b)| a.1 != b.1)
            || status.is_some_and(|(a, b)| a.1 != b.1 || a.2 > b.2)
            || wear.is_some_and(|(a, b)| a.1.iter().zip(b.1).all(|(old, new)| old - new > 0.5))
        {
            return Some(true);
        }
        set.map(|_| false)
    }
}

// Compare elapsed game time over the same two lap-distance coordinates. Only
// rivals observed crossing both coordinates on the racing surface can contribute.
#[derive(Clone)]
struct Transit {
    start_ms: u64,
    entry: f64,
    length: u16,
    traces: Vec<Option<Vec<(u64, f64)>>>,
}

pub(crate) fn distance(row: &[u8], length: u16) -> Option<f64> {
    let d = f32::from_le_bytes(row[20..24].try_into().unwrap());
    (length > 0 && row[33] > 0 && (0.0..=f32::from(length) + 1.0).contains(&d))
        .then(|| f64::from(row[33]) * f64::from(length) + f64::from(d))
}

fn circulating(row: &[u8]) -> bool {
    row[45] == 2 && row[34] == 0 && row[46] == 0 && row[32] > 0
}

fn crossing(points: &[(u64, f64)], target: f64) -> Option<f64> {
    let i = points.partition_point(|p| p.1 < target);
    let &(end, b) = points.get(i)?;
    if b == target {
        return Some(end as f64);
    }
    let &(start, a) = points.get(i.checked_sub(1)?)?;
    Some(start as f64 + (end - start) as f64 * (target - a) / (b - a))
}

impl Transit {
    fn start(rows: &[u8], player: usize, ms: u64, length: u16) -> Option<Self> {
        let entry = distance(&rows[player * 57..], length)?;
        let traces = rows
            .chunks_exact(57)
            .enumerate()
            .map(|(i, r)| {
                let d = distance(r, length)?;
                (i != player && circulating(r) && d <= entry).then(|| vec![(ms, d)])
            })
            .collect();
        Some(Self {
            start_ms: ms,
            entry,
            length,
            traces,
        })
    }

    fn update(&mut self, rows: &[u8], ms: u64, exiting: bool) {
        for (slot, r) in self.traces.iter_mut().zip(rows.chunks_exact(57)) {
            let Some(points) = slot.as_mut() else {
                continue;
            };
            let (at, before) = *points.last().unwrap();
            let delta = ms.saturating_sub(at);
            let next = distance(r, self.length);
            if !circulating(r)
                || ms < at
                || delta > 500
                || ms - self.start_ms > 120_000
                || next.is_none_or(|d| d < before || d - before > 1.0 + 0.13 * delta as f64)
            {
                *slot = None;
            } else if delta >= 100 || (exiting && delta > 0) {
                points.push((ms, next.unwrap()));
            }
        }
    }

    fn loss(&self, me: &[u8], ms: u64) -> Option<(u32, u8)> {
        let exit = distance(me, self.length)?;
        if exit <= self.entry || exit - self.entry >= f64::from(self.length) {
            return None;
        }
        let elapsed = ms.checked_sub(self.start_ms)? as f64;
        let mut losses: Vec<_> = self
            .traces
            .iter()
            .flatten()
            .filter_map(|points| {
                let reference = crossing(points, exit)? - crossing(points, self.entry)?;
                Some((elapsed - reference).round() as i32)
            })
            .collect();
        // Multiple independent cars guard against one car slowing or fighting.
        if losses.len() < 2 {
            return None;
        }
        losses.sort_unstable();
        let median = losses[losses.len() / 2].midpoint(losses[(losses.len() - 1) / 2]);
        (1000..=120_000)
            .contains(&median)
            .then_some((median as u32, losses.len() as u8))
    }
}

#[derive(Clone)]
pub(crate) struct Visit {
    entry_gaps: Vec<Option<i32>>,
    serviced: bool,
    transit: Option<Transit>,
}

impl Visit {
    pub(crate) fn start(rows: &[u8], player: usize, ms: u64, length: u16) -> Self {
        let me = &rows[player * 57..];
        let entry_gaps = rows
            .chunks_exact(57)
            .enumerate()
            .map(|(slot, r)| {
                (slot != player && valid_gap(me) && on_track(r)).then(|| gap(me) - gap(r))
            })
            .collect();
        Self {
            entry_gaps,
            serviced: false,
            transit: Transit::start(rows, player, ms, length),
        }
    }

    pub(crate) fn update(&mut self, rows: &[u8], me: &[u8], ms: u64) {
        if let Some(transit) = &mut self.transit {
            transit.update(rows, ms, me[34] != 2 && me[46] != 1);
        }
        for (baseline, rival) in self.entry_gaps.iter_mut().zip(rows.chunks_exact(57)) {
            if !on_track(rival) {
                *baseline = None;
            }
        }
        self.serviced |= u16::from_le_bytes([me[49], me[50]]) > 0;
    }

    pub(crate) fn loss(self, rows: &[u8], me: &[u8], ms: u64) -> Option<(u32, u8)> {
        if !self.serviced {
            return None;
        }
        self.delta(rows, me)
            .filter(|v| (1000..=120000).contains(v))
            .map(|v| (v, 0))
            .or_else(|| self.transit?.loss(me, ms))
    }

    pub(crate) fn delta(&self, rows: &[u8], me: &[u8]) -> Option<u32> {
        if !valid_gap(me) {
            return None;
        }
        // Relative movement against the same rivals survives a change of leader.
        // Take the median before checking plausibility to avoid selection bias.
        let mut changes: Vec<_> = self
            .entry_gaps
            .iter()
            .copied()
            .zip(rows.chunks_exact(57))
            .filter_map(|(before, rival)| Some(gap(me) - gap(rival) - before?))
            .collect();
        changes.sort_unstable();
        let hi = changes.len() / 2;
        let loss = changes.get(hi)?.midpoint(changes[(changes.len() - 1) / 2]);
        Some(loss.max(0) as u32)
    }
}

fn gap(row: &[u8]) -> i32 {
    i32::from(u16::from_le_bytes([row[17], row[18]])) + 60_000 * i32::from(row[19])
}

pub(crate) fn valid_gap(row: &[u8]) -> bool {
    row[32] == 1 || (row[32] > 1 && gap(row) > 0)
}

fn on_track(row: &[u8]) -> bool {
    circulating(row) && valid_gap(row)
}
