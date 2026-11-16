use std::collections::VecDeque;

/// Sample the game's interval clock at 4 Hz. Fit a slope rather than using a
/// single change: the game updates intervals in discrete steps.
#[derive(Default, Clone)]
pub(crate) struct GapTrend {
    pair: Option<(u8, u8)>,
    samples: VecDeque<(u32, u32)>,
}

impl GapTrend {
    pub fn observe(&mut self, pair: (u8, u8), time: u32, gap: u32) {
        if self.pair != Some(pair)
            || self
                .samples
                .back()
                .is_some_and(|&(last, _)| time < last || time - last > 2000)
        {
            self.samples.clear();
        }
        self.pair = Some(pair);
        if self.samples.is_empty() && gap == 0 {
            return;
        }
        if self
            .samples
            .back()
            .is_some_and(|&(last, _)| time - last < 250)
        {
            return;
        }
        self.samples.push_back((time, gap));
        while self
            .samples
            .front()
            .is_some_and(|&(t, _)| time - t > 30_000)
        {
            self.samples.pop_front();
        }
    }

    // Leader slot, follower slot, milliseconds gained per 10 s, window in ms.
    pub fn estimate(&self) -> Option<(u8, u8, i32, u32)> {
        let (start, _) = *self.samples.front()?;
        let span = self.samples.back()?.0 - start;
        if span < 2000 || self.samples.len() < 5 {
            return None;
        }
        let mut t = 0.;
        let mut g = 0.;
        let mut tt = 0.;
        let mut tg = 0.;
        for &(at, gap) in &self.samples {
            let x = f64::from(at - start);
            let y = f64::from(gap);
            t += x;
            g += y;
            tt += x * x;
            tg += x * y;
        }
        let n = self.samples.len() as f64;
        let gain = (-10_000. * (n * tg - t * g) / (n * tt - t * t)).round();
        let (leader, follower) = self.pair?;
        Some((leader, follower, gain as i32, span))
    }
}

/// Hold the published projection for this player lap and adjacent pair, while
/// GapTrend continues to follow the on-track interval on every packet.
#[derive(Default, Clone)]
pub(crate) struct LapBattle {
    key: Option<(u8, u8, u8)>,
    first_lap: u8,
    pub result: Option<(u8, u8, u8, i64, Option<u32>, u8)>,
}
impl LapBattle {
    pub fn observe(
        &mut self,
        pair: (u8, u8),
        lap: u8,
        gap: u32,
        completed: impl FnOnce(u8) -> Vec<i64>,
    ) {
        let key = (pair.0, pair.1, lap);
        if self.key.is_none_or(|(a, b, n)| (a, b) != pair || n > lap) {
            self.first_lap = lap;
        }
        if self.key != Some(key) {
            self.key = Some(key);
            self.result = None;
        }
        if self.result.is_some() {
            return;
        }
        let oldest = if lap == self.first_lap {
            lap.saturating_sub(1)
        } else {
            self.first_lap
        };
        let deltas = completed(oldest.max(1));
        if deltas.is_empty() {
            return;
        }
        let mean = (deltas.iter().sum::<i64>() as f64 / deltas.len() as f64).round() as i64;
        self.result = Some((
            pair.0,
            pair.1,
            lap,
            mean,
            super::laps_to_one_second(gap, mean),
            deltas.len() as u8,
        ));
    }
}

#[cfg(test)]
mod tests {
    use super::GapTrend;

    #[test]
    fn displayed_average_changes_at_lap_or_opponent_boundary() {
        let mut battle = super::LapBattle::default();
        battle.observe((2, 3), 5, 9000, |_| vec![1000, 2000, 3000]);
        assert_eq!(battle.result, Some((2, 3, 5, 2000, Some(4), 3)));
        battle.observe((2, 3), 5, 2000, |_| panic!("reused lap"));
        assert_eq!(battle.result.unwrap().4, Some(4));
        battle.observe((2, 3), 6, 2000, |_| vec![-500, 0]);
        assert_eq!(battle.result, Some((2, 3, 6, -250, None, 2)));
        battle.observe((1, 3), 6, 5000, |_| Vec::new());
        assert!(battle.result.is_none());
        battle.observe((1, 3), 6, 5000, |_| vec![1000]);
        assert_eq!(battle.result.unwrap().4, Some(4));
    }

    #[test]
    fn live_gap_slope_requires_fresh_samples_of_the_same_battle() {
        let mut trend = GapTrend::default();
        for i in 0..=8 {
            trend.observe((1, 2), 250 * i, 3000 - 25 * i);
        }
        assert_eq!(trend.estimate(), Some((1, 2, 1000, 2000)));
        trend.observe((1, 3), 2250, 800);
        assert!(trend.estimate().is_none());
        for i in 1..=8 {
            trend.observe((1, 3), 2250 + 250 * i, 800 + 25 * i);
        }
        assert_eq!(trend.estimate(), Some((1, 3, -1000, 2000)));
        trend.observe((1, 3), 9000, 2000);
        assert!(trend.estimate().is_none());
    }
}
