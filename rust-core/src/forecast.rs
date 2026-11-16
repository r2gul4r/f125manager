//! One-stop, lap-boundary strategy model. Coefficients are demo assumptions in milliseconds.
use pyo3::{exceptions::PyValueError, prelude::*, types::PyDict};

const REJOIN_TRAFFIC_MS: i64 = 3000;

#[derive(Clone, Copy, PartialEq)]
enum Tyre {
    Soft,
    Medium,
    Hard,
    Inter,
    Wet,
}
use Tyre::*;
impl Tyre {
    fn parse(code: &str) -> PyResult<Self> {
        match code {
            "S" => Ok(Soft),
            "M" => Ok(Medium),
            "H" => Ok(Hard),
            "I" => Ok(Inter),
            "W" => Ok(Wet),
            _ => Err(PyValueError::new_err("unknown tyre")),
        }
    }
    fn suits(self, surface: u8) -> bool {
        match surface {
            0 => !matches!(self, Inter | Wet),
            1 => self == Inter,
            _ => self == Wet,
        }
    }
    fn code(self) -> &'static str {
        match self {
            Soft => "S",
            Medium => "M",
            Hard => "H",
            Inter => "I",
            Wet => "W",
        }
    }
    fn life(self) -> i32 {
        match self {
            Soft => 13,
            Medium => 19,
            Hard => 26,
            Inter => 22,
            Wet => 25,
        }
    }
    fn wear(self) -> i64 {
        match self {
            Soft => 145,
            Medium => 90,
            Hard => 55,
            Inter => 95,
            Wet => 80,
        }
    }
    fn penalty(self, surface: u8) -> i64 {
        match (surface, self) {
            (0, Soft) => -450,
            (0, Medium) => 0,
            (0, Hard) => 400,
            (0, Inter) => 3500,
            (0, Wet) => 6500,
            (1, Inter) => 2000,
            (1, Wet) => 3600,
            (1, _) => 6400,
            (_, Wet) => 4700,
            (_, Inter) => 7600,
            _ => 12000,
        }
    }
}

struct Car {
    code: String,
    gap: i64,
    tyre: Tyre,
    age: i32,
    base: i64,
    wear: i64,
    spread: i64,
    remaining: Option<i32>,
    stock: Vec<(Tyre, i64, i32)>,
    penalty: i64,
    serve_penalty: bool,
    pitting: bool,
    accrued_pit_ms: Option<u32>,
    compound_wear: Vec<(Tyre, i64)>,
}
impl Car {
    fn replacement(&self, surface: u8, default: Tyre, laps: i32) -> Tyre {
        self.stock
            .iter()
            .min_by_key(|(tyre, delta, life)| {
                let suitable = match surface {
                    0 => !matches!(tyre, Inter | Wet),
                    1 => *tyre == Inter,
                    _ => *tyre == Wet,
                };
                (!suitable, (laps - life).max(0), *delta)
            })
            .map_or(default, |s| s.0)
    }
    fn new_lap(&self, tyre: Tyre, surface: u8) -> i64 {
        self.stock.iter().find(|s| s.0 == tyre).map_or_else(
            || self.lap_time(tyre, 0, surface),
            |s| self.lap_time(self.tyre, self.age, surface) + s.1,
        )
    }
    fn lap_time(&self, tyre: Tyre, age: i32, surface: u8) -> i64 {
        self.base + tyre.penalty(surface) + self.degradation(tyre) * i64::from(age)
    }
    fn degradation(&self, tyre: Tyre) -> i64 {
        if tyre == self.tyre {
            self.wear
        } else {
            self.compound_wear
                .iter()
                .find(|v| v.0 == tyre)
                .map_or(tyre.wear(), |v| v.1)
        }
    }
}

pub(crate) fn pit_loss_ms(ms: u32, neutral: bool) -> u32 {
    if neutral {
        (u64::from(ms) * 6 / 10) as u32
    } else {
        ms
    }
}

struct Race {
    lap: i32,
    end: i32,
    surface: u8,
    rain_starting: bool,
    pit_ms: u32,
    neutral: bool,
    neutral_loss: Option<u32>,
    outlook: Vec<(u8, u8)>,
    stock: Vec<(Tyre, i64, i32)>,
}
impl Race {
    fn conditions(&self, lap: i32) -> u8 {
        if let Some((_, surface)) = self
            .outlook
            .iter()
            .rev()
            .find(|(at, _)| i32::from(*at) <= lap)
        {
            return *surface;
        }
        if self.rain_starting && lap >= self.lap + 2 {
            1
        } else {
            self.surface
        }
    }
    fn replacement(&self, lap: i32, dry: Tyre) -> Tyre {
        match self.conditions(lap) {
            1 => Inter,
            2 => Wet,
            _ => dry,
        }
    }
    fn loss(&self, lap: i32) -> i64 {
        if self.neutral && lap == self.lap {
            if let Some(ms) = self.neutral_loss {
                return i64::from(ms);
            }
        }
        i64::from(pit_loss_ms(self.pit_ms, self.neutral && lap == self.lap))
    }
    fn stop_cost(&self, car: &Car, lap: i32) -> i64 {
        let loss = self.loss(lap);
        if car.pitting && lap == self.lap {
            (loss - i64::from(car.accrued_pit_ms.unwrap_or(0))).max(0)
        } else {
            loss
        }
    }
    // Extend a live candidate when the next stint exceeds the game's set life.
    // Consume each physical set once and reserve sets for the driver's later stops.
    fn stint_stops(
        &self,
        car: &Car,
        stops: &[(i32, Tyre)],
        mut report: impl FnMut(i32, i32, Tyre, &'static str),
    ) -> (Vec<(i32, Tyre)>, i32) {
        if car.stock.is_empty() {
            return (stops.to_vec(), 0);
        }
        let mut plan = Vec::new();
        let mut used = Vec::new();
        let mut missing = 0;
        for (index, &(mut at, mut tyre)) in stops.iter().enumerate() {
            let end = stops.get(index + 1).map_or(self.end + 1, |s| s.0);
            loop {
                plan.push((at, tyre));
                let Some((id, (_, _, life))) = car
                    .stock
                    .iter()
                    .enumerate()
                    .find(|(id, s)| s.0 == tyre && !used.contains(id))
                else {
                    report(at, end - 1, tyre, "stock");
                    missing += end - at;
                    break;
                };
                used.push(id);
                let crossover = self.outlook.iter().find(|(n, surface)| {
                    i32::from(*n) > at
                        && i32::from(*n) < end
                        && *surface != self.conditions(at)
                        && !tyre.suits(*surface)
                });
                let next_lap = crossover.map_or(at + life, |s| (at + life).min(i32::from(s.0)));
                let expired = next_lap == at + life;
                if next_lap >= end {
                    break;
                }
                at = next_lap;
                let surface = self.conditions(at);
                let Some(next) = car
                    .stock
                    .iter()
                    .enumerate()
                    .filter(|(id, s)| {
                        !used.contains(id)
                            && car
                                .stock
                                .iter()
                                .enumerate()
                                .filter(|(n, set)| set.0 == s.0 && !used.contains(n))
                                .count()
                                > stops[index + 1..].iter().filter(|r| r.1 == s.0).count()
                            && match surface {
                                0 => !matches!(s.0, Inter | Wet),
                                1 => s.0 == Inter,
                                _ => s.0 == Wet,
                            }
                    })
                    .min_by_key(|(_, s)| ((end - at - s.2).max(0), s.1))
                else {
                    report(at, end - 1, tyre, if expired { "life" } else { "weather" });
                    missing += end - at;
                    break;
                };
                tyre = next.1 .0;
            }
        }
        (plan, missing)
    }
    // Totals from the start of the reference lap. A stop at L mounts the new set on L.
    fn duration(&self, car: &Car, through: i32, stops: &[(i32, Tyre)]) -> i64 {
        let mut tyre = car.tyre;
        let mut age = car.age;
        let mut time = 0;
        let mut adjustment = 0;
        let mut used = Vec::new();
        for lap in self.lap..=through {
            if let Some(&(_, new)) = stops.iter().find(|(at, _)| *at == lap) {
                tyre = new;
                age = 0;
                time += self.stop_cost(car, lap);
                if !car.stock.is_empty() {
                    // The game's delta compares the replacement with the currently fitted set.
                    adjustment = car
                        .stock
                        .iter()
                        .enumerate()
                        .find(|(i, (t, _, _))| *t == new && !used.contains(i))
                        .map_or(0, |(i, (_, delta, _))| {
                            used.push(i);
                            car.lap_time(car.tyre, car.age, self.surface) + delta
                                - car.lap_time(new, 0, self.surface)
                        });
                }
            }
            time += car.lap_time(tyre, age, self.conditions(lap)) + adjustment;
            age += 1;
        }
        time
    }
    // Five equally weighted tyre-life scenarios. A stop past the penultimate lap is omitted.
    fn rival_stop(&self, car: &Car, shift: i32) -> i32 {
        if car.pitting {
            return self.lap;
        }
        let wear_ratio = car.tyre.wear() as f64 / car.wear as f64;
        let life = car.remaining.map_or_else(
            || (f64::from(car.tyre.life()) * wear_ratio).round() as i32,
            |left| car.age + left,
        );
        for lap in self.lap..self.end {
            let surface = self.conditions(lap);
            let unsuitable = match surface {
                0 => matches!(car.tyre, Inter | Wet),
                1 => car.tyre != Inter,
                _ => car.tyre != Wet,
            };
            if (unsuitable && lap - self.lap >= shift.max(0))
                || car.age + lap - self.lap >= life + shift
            {
                return lap;
            }
        }
        self.end + 1
    }
}

// Compare both cars at the instant the later first stop finishes. Include a
// served penalty once, and exclude the lap just starting at this boundary.
impl Race {
    fn at_exit(&self, car: &Car, stops: &[(i32, Tyre)], boundary: i32) -> i64 {
        let mut elapsed = car.gap + self.duration(car, boundary - 1, stops);
        if stops.iter().any(|(lap, _)| *lap == boundary) {
            elapsed += self.stop_cost(car, boundary);
        }
        if stops.first().is_some_and(|(lap, _)| *lap <= boundary) && car.serve_penalty {
            elapsed += car.penalty;
        }
        elapsed
    }

    fn cut_risk(
        &self,
        me: &Car,
        stops: &[(i32, Tyre)],
        rivals: &[&Car],
        shifts: &[i32],
    ) -> [usize; 3] {
        let mine = stops[0].0;
        let mut counts = [0; 3];
        for &shift in shifts {
            let mut beaten = [false; 2];
            for rival in rivals {
                let theirs = self.rival_stop(rival, shift);
                if theirs == mine || theirs >= self.end {
                    continue;
                }
                let first = mine.min(theirs);
                let last = mine.max(theirs);
                if self.at_exit(me, &[], first) >= self.at_exit(rival, &[], first) {
                    continue;
                }
                let dry = if rival.tyre == Hard { Medium } else { Hard };
                let schedule = |at| {
                    [(
                        at,
                        rival.replacement(
                            self.conditions(at),
                            self.replacement(at, dry),
                            self.end - at + 1,
                        ),
                    )]
                };
                let my_exit = self.at_exit(me, stops, last);
                if self.at_exit(rival, &schedule(theirs), last) < my_exit
                    && my_exit <= self.at_exit(rival, &schedule(mine), last)
                {
                    beaten[usize::from(theirs > mine)] = true;
                }
            }
            counts[0] += usize::from(beaten[0]);
            counts[1] += usize::from(beaten[1]);
            counts[2] += 1;
        }
        counts
    }
}

// Samples are (tyre age at the start of a clean lap on this set, dry lap time in ms).
type Entry = (String, u32, String, u8, u32, Vec<(u8, u32)>);
fn prepare(entry: Entry) -> PyResult<Car> {
    let (code, gap, compound, age, reference, samples) = entry;
    let tyre = Tyre::parse(&compound)?;
    if reference == 0 || samples.iter().any(|(_, ms)| *ms == 0) {
        return Err(PyValueError::new_err("missing reference pace"));
    }
    let mut wear = tyre.wear();
    if let (Some(&(first_age, first)), Some(&(last_age, last))) = (samples.first(), samples.last())
    {
        if last_age > first_age {
            // Shrink the noisy observed slope toward the compound prior for short stints.
            let span = i64::from(last_age - first_age);
            wear = ((i64::from(last) - i64::from(first) + 3 * wear) / (span + 3)).clamp(25, 350);
        }
    }
    let bases: Vec<i64> = samples
        .iter()
        .map(|(age, ms)| i64::from(*ms) - tyre.penalty(0) - i64::from(*age) * wear)
        .collect();
    let base = if bases.is_empty() {
        i64::from(reference)
    } else {
        bases.iter().sum::<i64>() / bases.len() as i64
    };
    let spread = bases
        .iter()
        .map(|ms| (ms - base).abs())
        .max()
        .unwrap_or(600)
        .max(if samples.len() < 2 { 600 } else { 250 });
    Ok(Car {
        code,
        gap: i64::from(gap),
        tyre,
        age: i32::from(age),
        base,
        wear,
        spread,
        remaining: None,
        stock: vec![],
        penalty: 0,
        serve_penalty: false,
        pitting: false,
        accrued_pit_ms: None,
        compound_wear: vec![],
    })
}

/// Translate a recent lap into the fresh-medium dry reference used by the model.
#[pyfunction]
pub fn reference_pace(ms: u32, compound: &str, age: u8, surface: u8) -> PyResult<u32> {
    let tyre = Tyre::parse(compound)?;
    if surface > 2 || ms == 0 {
        return Err(PyValueError::new_err("invalid reference lap"));
    }
    Ok(
        (i64::from(ms) - tyre.penalty(surface) - tyre.wear() * i64::from(age))
            .clamp(1, i64::from(u32::MAX)) as u32,
    )
}

// Per-lap surface outlook, available physical sets (delta ms, remaining laps),
// fitted-set remaining laps by car, and the game's optional player stop window.
type LiveInputs = (
    Vec<(u8, u8)>,
    Vec<(String, i16, u8)>,
    Vec<(String, u8)>,
    Option<(u8, u8)>,
);
type CarInputs = (
    String,
    Vec<(String, i16, u8)>,
    u8,
    bool,
    bool,
    Option<u32>,
    Vec<(String, i32, u8)>,
);
fn parse_stock(sets: &[(String, i16, u8)]) -> PyResult<Vec<(Tyre, i64, i32)>> {
    sets.iter()
        .filter(|s| s.2 > 0)
        .map(|(code, delta, life)| Ok((Tyre::parse(code)?, i64::from(*delta), i32::from(*life))))
        .collect()
}
type ServiceLosses = [(u32, usize); 2];
#[pyfunction(signature=(entries, player, distance, conditions, pit_loss_ms, scheduled, telemetry=None, observations=None, proposal=None, quick_losses=None, serviced=false, advisor_choices=None))]
#[allow(clippy::too_many_arguments)]
pub fn race_forecast<'py>(
    py: Python<'py>,
    entries: Vec<Entry>,
    player: usize,
    distance: (u8, u8),
    conditions: (u8, bool, bool),
    pit_loss_ms: u32,
    scheduled: Vec<(u8, String)>,
    telemetry: Option<LiveInputs>,
    observations: Option<(Vec<CarInputs>, Option<u32>)>,
    proposal: Option<(u8, String)>,
    quick_losses: Option<[Option<ServiceLosses>; 2]>,
    serviced: bool,
    advisor_choices: Option<Vec<Option<(u8, String)>>>,
) -> PyResult<Bound<'py, PyDict>> {
    let live = telemetry.is_some();
    let (outlook, stock, lives, _game_window) = telemetry.unwrap_or_default();
    let (observed, neutral_loss) = observations.unwrap_or_default();
    let mut cars: Vec<_> = entries
        .into_iter()
        .map(|entry| {
            let reference = entry.4;
            let mut car = prepare(entry)?;
            if live {
                car.base = i64::from(reference);
                car.remaining = lives
                    .iter()
                    .find(|(code, _)| *code == car.code)
                    .map(|(_, life)| i32::from(*life));
                if let Some((_, sets, seconds, serve, pitting, accrued, slopes)) =
                    observed.iter().find(|c| c.0 == car.code)
                {
                    for (code, slope, n) in slopes {
                        let tyre = Tyre::parse(code)?;
                        let count = i64::from(*n);
                        let rate = ((i64::from(*slope) * count + 3 * tyre.wear()) / (count + 3))
                            .clamp(25, 350);
                        car.compound_wear.push((tyre, rate));
                        if tyre == car.tyre && *n > 0 {
                            car.wear = rate;
                        }
                    }
                    car.base = i64::from(reference)
                        - car.tyre.penalty(conditions.0)
                        - car.wear * i64::from(car.age);
                    car.accrued_pit_ms = *accrued;
                    car.stock = parse_stock(sets)?;
                    car.penalty = i64::from(*seconds) * 1000;
                    car.serve_penalty = *serve;
                    car.pitting = *pitting;
                }
            }
            Ok(car)
        })
        .collect::<PyResult<_>>()?;
    let me = cars
        .get_mut(player)
        .ok_or_else(|| PyValueError::new_err("missing player"))?;
    let (lap, end) = (i32::from(distance.0.max(1)), i32::from(distance.1));
    if lap >= end || conditions.0 > 2 || pit_loss_ms == 0 {
        return Err(PyValueError::new_err("invalid race context"));
    }
    me.stock = parse_stock(&stock)?;
    let me = &cars[player];
    let race = Race {
        lap,
        end,
        surface: conditions.0,
        rain_starting: conditions.1,
        neutral: conditions.2,
        neutral_loss,
        pit_ms: pit_loss_ms,
        outlook,
        stock: me.stock.clone(),
    };
    let later: Vec<_> = scheduled
        .iter()
        .filter(|(at, _)| i32::from(*at) >= lap)
        .skip(1)
        .map(|(at, t)| Ok((i32::from(*at), Tyre::parse(t)?)))
        .collect::<PyResult<_>>()?;
    let with_later = |at, tyre| {
        std::iter::once((at, tyre))
            .chain(later.iter().copied().filter(|(l, _)| *l > at))
            .collect::<Vec<_>>()
    };
    let shifts = [-4, -2, 0, 2, 4];
    let mut rival_finishes = Vec::new();
    let mut rival_stops = vec![Vec::new(); cars.len()];
    let mut rival_cycles = Vec::new();
    let rivals = PyDict::new(py);
    for (i, car) in cars.iter().enumerate().filter(|(i, _)| *i != player) {
        let windows = shifts.map(|shift| race.rival_stop(car, shift));
        let dry = if car.tyre == Hard { Medium } else { Hard };
        let replacement =
            |at| car.replacement(race.conditions(at), race.replacement(at, dry), end - at + 1);
        let finishes = windows.map(|at| {
            let stops = if at <= end {
                race.stint_stops(car, &[(at, replacement(at))], |_, _, _, _| {})
                    .0
            } else {
                vec![]
            };
            car.gap + car.penalty + race.duration(car, end, &stops)
        });
        if windows[2] < end && !car.pitting {
            rival_stops[i] = race
                .stint_stops(
                    car,
                    &[(windows[2], replacement(windows[2]))],
                    |_, _, _, _| {},
                )
                .0;
        }
        rival_finishes.push((i, finishes));
        rival_cycles.push(
            car.gap
                + if windows[2] < end {
                    race.stop_cost(car, windows[2])
                        + if car.serve_penalty { car.penalty } else { 0 }
                } else {
                    0
                },
        );
        let row = PyDict::new(py);
        row.set_item(
            "probability",
            [1, 3, 5].map(|n| {
                20 * windows
                    .iter()
                    .filter(|at| **at < end && **at < lap + n)
                    .count()
            }),
        )?;
        let possible: Vec<_> = windows.into_iter().filter(|at| *at < end).collect();
        row.set_item("window", possible.first().zip(possible.last()))?;
        let new = replacement(lap);
        let my_new = me.replacement(
            race.surface,
            race.replacement(lap, if me.tyre == Hard { Medium } else { Hard }),
            end - lap + 1,
        );
        row.set_item(
            "undercutMs",
            car.lap_time(car.tyre, car.age, race.surface) - me.new_lap(my_new, race.surface),
        )?;
        row.set_item(
            "overcutMs",
            car.new_lap(new, race.surface) - me.lap_time(me.tyre, me.age, race.surface),
        )?;
        rivals.set_item(&car.code, row)?;
    }
    let mut rejoins = Vec::new();
    let mut service_rejoins = Vec::new();
    let mut tyre_exits = Vec::new();
    let mut challengers: Vec<_> = cars
        .iter()
        .enumerate()
        .filter(|(i, car)| (car.gap, *i) > (me.gap, player))
        .collect();
    challengers.sort_by_key(|(i, car)| (car.gap, *i));
    let challengers: Vec<_> = challengers
        .into_iter()
        .take(2)
        .map(|(_, car)| car)
        .collect();
    let mut nearest = Vec::new();
    for at in lap..end {
        let mut times: Vec<_> = cars
            .iter()
            .enumerate()
            .map(|(i, car)| {
                let time = car.gap
                    + race.duration(car, at - 1, &rival_stops[i])
                    + if i == player {
                        race.loss(at) + if me.serve_penalty { me.penalty } else { 0 }
                    } else if car.pitting {
                        race.stop_cost(car, lap) + if car.serve_penalty { car.penalty } else { 0 }
                    } else {
                        0
                    };
                (time, i)
            })
            .collect();
        times.sort_unstable();
        let position = times.iter().position(|(_, i)| *i == player).unwrap();
        if let Some(pair) = &quick_losses {
            let losses = pair[usize::from(at != lap)];
            service_rejoins.push(losses.map(|services| {
                services.map(|(ms, count)| {
                    // Keep the same rivals, penalty and tie break as the baseline exit.
                    let exit = times[position].0 - race.loss(at) + i64::from(ms);
                    let rank = 1 + times
                        .iter()
                        .filter(|&&(time, i)| i != player && (time, i) < (exit, player))
                        .count();
                    (rank, ms, count)
                })
            }));
        }
        let base_loss = race.loss(at) + if me.serve_penalty { me.penalty } else { 0 };
        let entry = times[position].0 - base_loss;
        let entry_rank = 1 + times
            .iter()
            .filter(|&&(t, i)| i != player && (t, i) < (entry, player))
            .count();
        let exit_row = |times: &[(i64, usize)], position: usize, loss: i64| -> PyResult<_> {
            let ahead = position.checked_sub(1).map(|i| times[i]);
            let behind = times.get(position + 1);
            let row = PyDict::new(py);
            row.set_item("position", position + 1)?;
            row.set_item("before", ahead.map(|(_, i)| &cars[i].code))?;
            row.set_item("after", behind.map(|(_, i)| &cars[*i].code))?;
            row.set_item("aheadGapMs", ahead.map(|(t, _)| times[position].0 - t))?;
            row.set_item("behindGapMs", behind.map(|(t, _)| t - times[position].0))?;
            row.set_item(
                "trafficAhead",
                times[..position]
                    .iter()
                    .rev()
                    .take_while(|(t, _)| times[position].0 - t <= REJOIN_TRAFFIC_MS)
                    .map(|(t, i)| (&cars[*i].code, times[position].0 - t))
                    .collect::<Vec<_>>(),
            )?;
            row.set_item("lossMs", loss)?;
            Ok(row)
        };
        let row = exit_row(&times, position, base_loss)?;
        rejoins.push(row);
        let tyre_loss = quick_losses
            .and_then(|pair| pair[usize::from(at != lap)])
            .map_or(base_loss, |services| {
                base_loss - race.loss(at) + i64::from(services[0].0)
            });
        times[position].0 = entry + tyre_loss;
        times.sort_unstable();
        let tyre_rank = times.iter().position(|(_, i)| *i == player).unwrap();
        let ahead = tyre_rank.checked_sub(1).map(|i| times[i]);
        nearest.push(ahead.map_or(i64::MAX, |(time, _)| times[tyre_rank].0 - time));
        let tyre_exit = exit_row(&times, tyre_rank, tyre_loss)?;
        tyre_exit.set_item("entryPosition", entry_rank)?;
        if at - lap <= 3 {
            let center = times[tyre_rank].0;
            if at > lap {
                let pace: Vec<_> = times
                    .iter()
                    .skip(tyre_rank.saturating_sub(1))
                    .take(if tyre_rank == 0 { 2 } else { 3 })
                    .map(|&(_, i)| i)
                    .filter(|&i| !cars[i].pitting && !rival_stops[i].iter().any(|(n, _)| *n == lap))
                    .map(|i| {
                        (
                            &cars[i].code,
                            cars[i].lap_time(cars[i].tyre, cars[i].age, race.conditions(lap)),
                        )
                    })
                    .collect();
                tyre_exit.set_item("lapPaceMs", pace)?;
            }
            tyre_exit.set_item("penaltyMs", if me.serve_penalty { me.penalty } else { 0 })?;
            tyre_exit.set_item(
                "rivalMargins",
                times
                    .iter()
                    .filter(|(_, i)| *i != player)
                    .map(|(time, i)| (&cars[*i].code, time - center))
                    .collect::<Vec<_>>(),
            )?;
        }
        tyre_exits.push(tyre_exit);
    }
    // Reserve room on either side of the balanced stop when possible.
    // On a wet surface compare an immediate stop with two delayed alternatives.
    let hard = if me.tyre == Hard { Medium } else { Hard };
    let first = if end - lap >= 3 { lap + 1 } else { lap };
    let last = if end - lap >= 3 { end - 2 } else { end - 1 };
    let optimum = (first..=last)
        .min_by_key(|at| race.duration(me, end, &with_later(*at, race.replacement(*at, hard))))
        .unwrap();
    let mut balanced = if race.surface > 0 { lap + 1 } else { optimum };
    let set_score = |at: i32, tyre: Tyre| {
        let (stops, missing) = race.stint_stops(me, &with_later(at, tyre), |_, _, _, _| {});
        let excess = missing + me.remaining.map_or(0, |left| (at - lap - left).max(0));
        (excess, race.duration(me, end, &stops))
    };
    let select = |at: i32, default: Tyre| {
        [Soft, Medium, Hard, Inter, Wet]
            .into_iter()
            .filter(|t| race.stock.iter().any(|s| s.0 == *t))
            .min_by_key(|tyre| {
                let surface = race.conditions(at);
                let unsuitable = match surface {
                    0 => matches!(tyre, Inter | Wet),
                    1 => *tyre != Inter,
                    _ => *tyre != Wet,
                };
                (unsuitable, set_score(at, *tyre))
            })
            .unwrap_or(race.replacement(at, default))
    };
    if live {
        let limit = me
            .remaining
            .map_or(end - 1, |life| (lap + life).min(end - 1));
        let weather_stop = (lap..=limit).find(|n| {
            let surface = race.conditions(*n);
            match surface {
                0 => matches!(me.tyre, Inter | Wet),
                1 => me.tyre != Inter,
                _ => me.tyre != Wet,
            }
        });
        let last_viable = weather_stop.unwrap_or(limit);
        balanced = (lap..=last_viable)
            .min_by_key(|at| set_score(*at, select(*at, hard)))
            .unwrap_or(lap);
    }
    let mut candidates = [
        (balanced, hard),
        ((balanced - 2).max(lap), hard),
        (balanced + 2, if me.tyre == Soft { Medium } else { Soft }),
    ];
    if live {
        let best = |range: std::ops::Range<i32>, fallback| {
            range
                .min_by_key(|at| set_score(*at, select(*at, hard)))
                .unwrap_or(fallback)
        };
        candidates[1].0 = best(lap..balanced, balanced);
        candidates[2].0 = best(balanced + 1..end, balanced);
    }
    let mut plans = Vec::new();
    let mut choices: Vec<_> = ["A", "B", "C"]
        .into_iter()
        .zip(candidates)
        .map(|(id, (at, dry))| {
            let at = at.min(end - 1);
            (id, at, select(at, dry))
        })
        .collect();
    let stay_out = serviced
        && me.remaining.is_some_and(|life| life > end - lap)
        && (lap..=end).all(|n| match race.conditions(n) {
            0 => matches!(me.tyre, Soft | Medium | Hard),
            1 => me.tyre == Inter,
            _ => me.tyre == Wet,
        });
    if stay_out && race.duration(me, end, &[]) <= set_score(choices[0].1, choices[0].2).1 {
        choices[0] = ("A", end, me.tyre);
    }
    if let Some(overrides) = advisor_choices {
        if overrides.len() != 3 {
            return Err(PyValueError::new_err("Expected three Codex plans"));
        }
        for (choice, pick) in choices.iter_mut().zip(overrides) {
            match pick {
                None if stay_out => {
                    choice.1 = end;
                    choice.2 = me.tyre;
                }
                Some((n, code)) => {
                    let tyre = Tyre::parse(&code)?;
                    if !(lap..end).contains(&i32::from(n))
                        || (!me.stock.is_empty() && !me.stock.iter().any(|s| s.0 == tyre))
                    {
                        return Err(PyValueError::new_err("Unavailable Codex stop"));
                    }
                    choice.1 = i32::from(n);
                    choice.2 = tyre;
                }
                None => return Err(PyValueError::new_err("Stay out is unavailable")),
            }
        }
    }
    if let Some((at, code)) = proposal {
        let tyre = Tyre::parse(&code)?;
        let at = i32::from(at);
        if !(lap..end).contains(&at)
            || (!me.stock.is_empty() && !me.stock.iter().any(|s| s.0 == tyre))
        {
            return Err(PyValueError::new_err("Unavailable Codex stop"));
        }
        choices.push(("Codex", at, tyre));
    }
    for (id, at, tyre) in choices {
        let mut issues = Vec::new();
        let staying = at == end;
        let current_excess = me.remaining.map_or(0, |life| (at - lap - life).max(0));
        if current_excess > 0 {
            issues.push((at - current_excess, at - 1, me.tyre.code(), "life"));
        }
        let (stops, missing) = if staying {
            (Vec::new(), 0)
        } else {
            race.stint_stops(me, &with_later(at, tyre), |start, end, tyre, reason| {
                issues.push((start, end, tyre.code(), reason));
            })
        };
        let remaining = race.duration(me, end, &stops) + me.penalty;
        let finish = me.gap + remaining;
        let ranks = shifts.map(|shift| {
            let scenario = ((shift + 4) / 2) as usize;
            1 + rival_finishes
                .iter()
                .filter(|(idx, times)| {
                    times[scenario]
                        < finish
                            + i64::from(shift)
                                * (me.spread + cars[*idx].spread)
                                * i64::from(end - lap + 1)
                                / 4
                })
                .count()
        });
        let lo = ranks.iter().min().unwrap();
        let hi = ranks.iter().max().unwrap();
        let traffic = !staying && nearest[(at - lap) as usize] <= REJOIN_TRAFFIC_MS;
        let stop_cost = stops.iter().map(|(at, _)| race.loss(*at)).sum::<i64>()
            + if me.serve_penalty { me.penalty } else { 0 };
        let row = PyDict::new(py);
        row.set_item("id", id)?;
        row.set_item("stop", (at, tyre.code()))?;
        row.set_item("lifeShortfall", current_excess + missing)?;
        row.set_item("tyreIssues", issues)?;
        if live {
            row.set_item(
                "stops",
                stops
                    .iter()
                    .map(|(n, t)| (*n, t.code()))
                    .collect::<Vec<_>>(),
            )?;
        }
        row.set_item("remainingMs", remaining)?;
        row.set_item("wearMs", me.degradation(tyre))?;
        row.set_item(
            "wearObserved",
            me.compound_wear.iter().any(|v| v.0 == tyre)
                || (tyre == me.tyre && me.wear != tyre.wear()),
        )?;
        row.set_item(
            "net",
            1 + rival_cycles
                .iter()
                .filter(|t| **t < me.gap + stop_cost)
                .count(),
        )?;
        row.set_item("finish", (*lo, *hi))?;
        row.set_item("scenarioRanks", ranks)?;
        row.set_item("traffic", traffic)?;
        row.set_item(
            "risk",
            if hi - lo >= 5 {
                "High"
            } else if traffic || hi - lo >= 2 {
                "Medium"
            } else {
                "Low"
            },
        )?;
        let viable: Vec<_> = (lap..end)
            .filter(|other| {
                (other - at).abs() <= 2
                    && set_score(*other, tyre).1 + me.penalty <= remaining + 1000
            })
            .collect();
        row.set_item(
            "window",
            (
                viable.first().copied().unwrap_or(at),
                viable.last().copied().unwrap_or(at),
            ),
        )?;
        plans.push(row);
    }
    let result = PyDict::new(py);
    // The UI holds the published schedules for a lap. Price every possible
    // first stop so a held schedule can still use the newest rival observations.
    let cuts = PyDict::new(py);
    if !challengers.is_empty() {
        for tyre in [Soft, Medium, Hard, Inter, Wet] {
            if !me.stock.is_empty() && !me.stock.iter().any(|set| set.0 == tyre) {
                continue;
            }
            let outcomes = (lap..end)
                .map(|at| race.cut_risk(me, &[(at, tyre)], &challengers, &shifts))
                .collect::<Vec<_>>();
            cuts.set_item(tyre.code(), outcomes)?;
        }
    }
    result.set_item("cutScenarios", cuts)?;
    result.set_item(
        "cutRivals",
        challengers.iter().map(|c| &c.code).collect::<Vec<_>>(),
    )?;
    result.set_item("plans", plans)?;
    result.set_item("trafficWindowMs", REJOIN_TRAFFIC_MS)?;
    result.set_item("tyreExits", tyre_exits)?;
    result.set_item("rejoins", rejoins)?;
    result.set_item("serviceRejoins", service_rejoins)?;
    result.set_item("rivals", rivals)?;
    Ok(result)
}
