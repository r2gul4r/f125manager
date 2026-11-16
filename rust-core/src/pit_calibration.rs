//! Compare the current mean with a player-only median on later, separate races.
use crate::pit_loss::{average, groups, Group, Observation};
use std::collections::BTreeMap;

#[derive(Clone, Copy, Default)]
pub(crate) struct Validation {
    races: u32,
    wins: u32,
    mean_error: u64,
    median_error: u64,
}

impl Validation {
    fn use_median(self) -> bool {
        self.races >= 2 && self.wins * 2 > self.races && self.median_error < self.mean_error
    }
    pub fn report(self) -> (bool, u32, Option<u64>, Option<u64>) {
        let count = u64::from(self.races);
        (
            self.use_median(),
            self.races,
            self.mean_error.checked_div(count),
            self.median_error.checked_div(count),
        )
    }
}

fn median(values: &mut [u32]) -> Option<u32> {
    if values.len() < 3 {
        return None;
    }
    values.sort_unstable();
    let mid = values.len() / 2;
    Some(((u64::from(values[mid]) + u64::from(values[(values.len() - 1) / 2])) / 2) as u32)
}

pub(crate) fn estimate(
    player: Option<&Group>,
    rivals: Option<&Group>,
    active: Option<u64>,
) -> (Option<(u32, usize)>, Validation) {
    let mut own = player.map(|g| g.totals(true)).unwrap_or_default();
    let mut all = own.clone();
    if let Some(g) = rivals {
        all.extend(g.totals(true));
    }
    let base = average(&all);
    let mut score = Validation::default();
    let Some(candidate) = median(&mut own) else {
        return (base, score);
    };
    let g = player.expect("median requires player observations");
    let mut races = BTreeMap::new();
    for s in &g.samples {
        if let Some((uid, end)) = s.origin.filter(|(uid, _)| Some(*uid) != active) {
            races
                .entry(uid)
                .and_modify(|v: &mut u64| *v = (*v).min(end))
                .or_insert(end);
        }
    }
    for (uid, cutoff) in races {
        let earlier = |s: &&Observation| {
            s.origin
                .is_some_and(|(id, t)| id != uid && Some(id) != active && t < cutoff)
        };
        let train = groups(
            g.samples
                .iter()
                .chain(rivals.into_iter().flat_map(|r| &r.samples))
                .filter(earlier)
                .copied(),
        );
        let Some(past) = train.get(&g.samples[0].condition) else {
            continue;
        };
        let Some(robust) = median(&mut past.totals(true)) else {
            continue;
        };
        let losses: Vec<_> = train.values().flat_map(|p| p.totals(true)).collect();
        let Some((mean, _)) = average(&losses) else {
            continue;
        };
        let mut errors = (0u64, 0u64, 0u64);
        for s in &g.samples {
            if s.origin.is_none_or(|o| o.0 != uid) || !past.includes(s.service) {
                continue;
            }
            if let Some(loss) = s.loss {
                errors.0 += u64::from(loss.abs_diff(mean));
                errors.1 += u64::from(loss.abs_diff(robust));
                errors.2 += 1;
            }
        }
        if let Some((old, new)) = errors
            .0
            .checked_div(errors.2)
            .zip(errors.1.checked_div(errors.2))
        {
            score.races += 1;
            score.wins += u32::from(errors.1 < errors.0);
            score.mean_error += old;
            score.median_error += new;
        }
    }
    (
        if score.use_median() {
            Some((candidate, own.len()))
        } else {
            base
        },
        score,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        pit_loss::{Condition, Work},
        pit_rules::Profile,
    };
    #[test]
    fn only_independent_later_races_can_promote_and_losses_can_revert() {
        let c = Condition {
            format: 2026,
            track: 3,
            wet: Some(false),
            safety: 0,
            work: Work::Tyres,
            profile: Profile::from_session(&[0; 753]).unwrap(),
        };
        let mut rows = Vec::new();
        let sample = |id: u64, loss: u32| Observation {
            condition: c,
            origin: Some((id, id * 100)),
            service: 2500,
            loss: Some(loss),
        };
        for x in [20000, 20000, 26000] {
            rows.push(sample(1, x));
        }
        rows.push(sample(2, 20000));
        rows.push(sample(3, 20000));
        let run = |rows: &[Observation], active| {
            estimate(groups(rows.iter().copied()).get(&c), None, active)
        };
        assert!(!run(&rows, Some(3)).1.use_median());
        let (fit, score) = run(&rows, Some(4));
        assert_eq!(fit, Some((20000, 5)));
        assert_eq!(score.report(), (true, 2, Some(1750), Some(0)));
        rows.push(sample(4, 28000));
        rows.push(sample(5, 29000));
        assert!(!run(&rows, None).1.use_median());
    }
}
