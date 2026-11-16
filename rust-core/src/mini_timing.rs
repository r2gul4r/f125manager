//! Estimate eight split times per official sector from the lap clock at distance crossings.
#[derive(Default, Clone)]
pub(crate) struct MiniTiming {
    geometry: Option<[f32; 4]>,
    cars: Vec<CarSplits>,
}

type Times = [Option<u32>; 24];
#[derive(Clone)]
struct FinishedLap {
    times: Times,
    prior_best: Times,
}
#[derive(Default, Clone)]
struct CarSplits {
    lap: u8,
    previous: Option<(f32, u32)>,
    ineligible: bool,
    approaching_start: bool,
    crossings: [Option<u32>; 25],
    best: Times,
    finished: Option<FinishedLap>,
}

impl CarSplits {
    fn durations(&self) -> [Option<u32>; 24] {
        std::array::from_fn(|i| {
            if self.ineligible {
                return None;
            }
            self.crossings[i + 1]?
                .checked_sub(self.crossings[i]?)
                .filter(|&t| t > 0)
        })
    }

    fn advance(&mut self, distance: f32, time: u32, bounds: [f32; 4]) {
        if let Some((prev, clock)) = self.previous {
            // The game corrects the running clock at sector lines (10 ms at Monza).
            // Wait for the clock to catch up before interpolating the next crossing.
            if distance >= prev && time < clock && clock - time <= 50 {
                return;
            }
            if distance < prev || time < clock {
                self.ineligible = true;
            } else if distance > prev && distance - prev <= 200.0 && time - clock <= 2000 {
                for sector in 0..3 {
                    if prev >= bounds[sector + 1] || distance < bounds[sector] {
                        continue;
                    }
                    for n in 1..=8 {
                        let end =
                            bounds[sector] + (bounds[sector + 1] - bounds[sector]) * n as f32 / 8.0;
                        if prev < end && end <= distance {
                            self.crossings[sector * 8 + n] = Some(
                                clock
                                    + ((time - clock) as f32 * (end - prev) / (distance - prev))
                                        .round() as u32,
                            );
                        }
                    }
                }
            }
        }
        self.previous = Some((distance, time));
    }
}

impl MiniTiming {
    pub(crate) fn observe(&mut self, rows: &[u8], bounds: [f32; 4]) {
        if self.geometry != Some(bounds) {
            self.cars.clear();
            self.geometry = Some(bounds);
        }
        if !bounds.windows(2).all(|w| w[1].is_finite() && w[0] < w[1]) {
            return;
        }
        self.cars.resize_with(rows.len() / 57, CarSplits::default);
        for (car, r) in self.cars.iter_mut().zip(rows.chunks_exact(57)) {
            let lap = r[33];
            let distance = f32::from_le_bytes(r[20..24].try_into().unwrap());
            let time = u32::from_le_bytes(r[4..8].try_into().unwrap());
            // In practice the out lap can have the same number as the first flying lap.
            let flying_start = car.approaching_start
                && (0.0..=200.0).contains(&distance)
                && time <= 2000
                && matches!(r[44], 1 | 4)
                && r[34] == 0;
            if car.lap != lap || flying_start {
                let next = car.lap > 0 && car.lap.checked_add(1) == Some(lap);
                let mut finished = None;
                if next {
                    let last = u32::from_le_bytes(r[..4].try_into().unwrap());
                    car.advance(bounds[3], last, bounds);
                    let times = car.durations();
                    if times.iter().any(Option::is_some) {
                        finished = Some(FinishedLap {
                            times,
                            prior_best: car.best,
                        });
                    }
                    for (i, split) in times.into_iter().enumerate() {
                        if let Some(t) = split {
                            car.best[i] = Some(car.best[i].map_or(t, |b| b.min(t)));
                        }
                    }
                }
                *car = CarSplits {
                    lap,
                    best: car.best,
                    finished,
                    ..Default::default()
                };
                // The lap clock starts at zero; only seed the first interval near the line.
                if time <= 2000 && distance <= 200.0 {
                    car.crossings[0] = Some(0);
                }
            }
            car.approaching_start = distance < 0.0 && time == 0;
            if lap == 0 || r[45] != 2 || r[34] != 0 || r[37] != 0 || !matches!(r[44], 1 | 4) {
                car.ineligible = true;
                car.finished = None;
                car.previous = None;
            } else if (0.0..=bounds[3]).contains(&distance) && !car.ineligible {
                if distance >= bounds[1] / 8.0 || time >= 5000 {
                    car.finished = None;
                }
                car.advance(distance, time, bounds);
                let s1 = crate::live::split(r, 8);
                let s2 = crate::live::split(r, 11);
                if r[36] >= 1 && s1 > 0 && s1 <= time {
                    car.crossings[8] = Some(s1);
                    if r[36] == 2 && s2 > 0 && s1 + s2 <= time {
                        car.crossings[16] = Some(s1 + s2);
                    }
                }
            }
        }
    }

    pub(crate) fn showing_last(&self, slot: usize) -> bool {
        self.cars
            .get(slot)
            .is_some_and(|car| car.finished.is_some())
    }

    pub(crate) fn colours(&self) -> Vec<[&'static str; 24]> {
        let current: Vec<_> = self
            .cars
            .iter()
            .map(|car| {
                car.finished.as_ref().map_or_else(
                    || (car.durations(), car.best),
                    |lap| (lap.times, lap.prior_best),
                )
            })
            .collect();
        // Colour against other valid passages, including rivals still on this lap.
        let mut field = [u32::MAX; 24];
        for (times, best) in &current {
            for (i, entry) in field.iter_mut().enumerate() {
                for t in [best[i], times[i]].into_iter().flatten() {
                    *entry = (*entry).min(t);
                }
            }
        }
        current
            .into_iter()
            .map(|(times, best)| {
                std::array::from_fn(|i| match times[i] {
                    Some(t) if t == field[i] => "fastest",
                    Some(t) if best[i].is_none_or(|b| t <= b) => "personal",
                    Some(_) => "normal",
                    None => "pending",
                })
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn car(lap: u8, distance: f32, ms: u32, invalid: bool) -> [u8; 57] {
        let mut row = [0; 57];
        row[..4].copy_from_slice(&24000u32.to_le_bytes());
        row[4..8].copy_from_slice(&ms.to_le_bytes());
        row[20..24].copy_from_slice(&distance.to_le_bytes());
        row[33] = lap;
        row[37] = u8::from(invalid);
        row[44] = 4;
        row[45] = 2;
        row
    }

    #[test]
    fn same_number_outlap_then_flying_lap_matches_game_clocks() {
        let bounds = [0., 800., 1600., 2400.];
        let mut minis = MiniTiming::default();
        let mut out = car(1, -30., 0, false);
        out[44] = 3;
        minis.observe(&out, bounds);
        for i in 0..24 {
            if i == 16 {
                minis.observe(&car(1, 1599., 16010, false), bounds);
            }
            let mut r = car(1, (i * 100) as f32, i * 1000, false);
            r[36] = (i / 8) as u8;
            r[8..10].copy_from_slice(&7950u16.to_le_bytes());
            r[11..13].copy_from_slice(&8075u16.to_le_bytes());
            minis.observe(&r, bounds);
        }
        minis.observe(&car(2, 0., 0, false), bounds);
        let last = minis.cars[0].finished.as_ref().unwrap();
        let sums: Vec<u32> = last
            .times
            .chunks_exact(8)
            .map(|s| {
                s.iter()
                    .copied()
                    .collect::<Option<Vec<_>>>()
                    .unwrap()
                    .into_iter()
                    .sum()
            })
            .collect();
        assert_eq!(sums, [7950, 8075, 7975]);
        assert_eq!(minis.colours()[0], ["fastest"; 24]);
    }

    #[test]
    fn compares_same_distance_and_excludes_invalid_laps_and_missing_boundaries() {
        let mut minis = MiniTiming::default();
        let mut observe = |lap, distances: [f32; 2], times: [u32; 2], invalid| {
            let rows = [
                car(lap, distances[0], times[0], invalid),
                car(lap, distances[1], times[1], false),
            ]
            .concat();
            minis.observe(&rows, [0., 800., 1600., 2400.]);
            minis.colours()
        };
        observe(1, [0., 0.], [0, 0], false);
        let colours = observe(1, [125., 100.], [1250, 800], false);
        assert_eq!(colours[0][0], "personal");
        assert_eq!(colours[1][0], "fastest");
        observe(2, [0., 0.], [0, 0], false);
        let colours = observe(2, [120., 100.], [1080, 950], false);
        assert_eq!(colours[0][0], "personal");
        assert_eq!(colours[1][0], "normal");
        assert_eq!(
            observe(2, [125., 110.], [1120, 1050], true)[0][0],
            "pending"
        );
        observe(3, [0., 0.], [0, 0], false);
        let colours = observe(3, [180., 450.], [1440, 3500], false);
        assert_eq!(colours[0][0], "fastest");
        assert_eq!(colours[1][3], "pending");
    }
}
