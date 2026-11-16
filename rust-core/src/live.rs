//! EA packed little-endian UDP packets. Retain the latest packet per stream and car.
use crate::pit_loss::{
    average, groups, valid_gap, Condition, Damage, Equipment, History, Observation, Scenarios,
    Visit, Work, PARTS,
};
use crate::pit_rules::Profile;
use crate::recording::{Recorder, Stop};
use pyo3::{prelude::*, types::PyDict};
use std::{
    collections::{BTreeMap, VecDeque},
    net::UdpSocket,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};

fn u16_at(b: &[u8], i: usize) -> u16 {
    u16::from_le_bytes([b[i], b[i + 1]])
}
pub(crate) fn u32_at(b: &[u8], i: usize) -> u32 {
    u32::from_le_bytes(b[i..i + 4].try_into().unwrap())
}
pub(crate) fn split(b: &[u8], i: usize) -> u32 {
    u32::from(u16_at(b, i)) + 60000 * u32::from(b[i + 2])
}

// A missing leader clock is recoverable from the adjacent timing clocks on the
// same frame. Refuse inconsistent neighbours after a pass or at a timing reset.
fn race_gap(rows: &[u8], car: &[u8]) -> Option<u32> {
    let direct = split(car, 17);
    if car[32] == 1 {
        return Some(0);
    }
    if car[32] == 0 || car[45] != 2 || u16_at(car, 17) >= 60000 {
        return None;
    }
    if direct > 0 {
        return Some(direct);
    }
    let adjacent = |pos: u8| {
        rows.as_chunks::<57>()
            .0
            .iter()
            .find(|&r| r[45] == 2 && r[32] == pos && valid_gap(r) && u16_at(r, 17) < 60000)
    };
    let ahead = adjacent(car[32] - 1)?;
    let behind = adjacent(car[32].checked_add(1)?)?;
    let lo = split(ahead, 17);
    let hi = split(behind, 17);
    if hi < lo {
        return None;
    }
    let interval = |r: &[u8]| (u16_at(r, 14) < 60000 && split(r, 14) > 0).then(|| split(r, 14));
    let prev = interval(car).map(|v| lo + v);
    let next = interval(behind).and_then(|v| hi.checked_sub(v));
    if prev.zip(next).is_some_and(|(p, n)| p.abs_diff(n) > 500) {
        return None;
    }
    prev.or(next).filter(|v| (lo..=hi).contains(v))
}

// Compare the same completed lap on both current stints. Session history may
// arrive one packet later than LapData; the latter carries the last lap time.
fn completed_battle_lap(row: &[u8], history: Option<&[u8]>, number: u8) -> Option<u32> {
    if number == 0 || number >= row[33] {
        return None;
    }
    if let Some(h) = history {
        if h[1436..]
            .as_chunks::<3>()
            .0
            .iter()
            .take(h[31] as usize)
            .any(|s| s[0] != 255 && number <= s[0].saturating_add(1))
        {
            return None;
        }
        if number <= h[30] {
            let data = &h[36 + 14 * usize::from(number - 1)..];
            if u32_at(data, 0) > 0 {
                return (data[13] & 1 != 0).then(|| u32_at(data, 0));
            }
        }
    }
    (number == row[33] - 1 && u32_at(row, 0) > 0).then(|| u32_at(row, 0))
}

// The leader can start the next lap while a rival is still approaching the
// line. Their leader gaps still use the same clock until a full lap separates them.
fn comparable_laps(rows: &[u8], track_length: u16) -> bool {
    let mut racing = rows
        .as_chunks::<57>()
        .0
        .iter()
        .filter(|r| r[45] == 2 && r[32] > 0);
    let Some(leader) = racing.clone().find(|r| r[32] == 1) else {
        return false;
    };
    let distance = |r: &[u8]| f32::from_bits(u32_at(r, 20));
    let lead = distance(leader);
    // Session length is whole metres; lap distance retains the final fraction.
    let circuit = 0.0..(f32::from(track_length) + 1.0);
    racing.all(|r| {
        r[33] == leader[33]
            || (r[33] > 0
                && track_length > 0
                && leader[33].checked_sub(r[33]) == Some(1)
                && circuit.contains(&lead)
                && circuit.contains(&distance(r))
                && distance(r) > lead)
    })
}

fn forecast_gaps(rows: &[u8], track_length: u16, comparable: bool) -> Option<Vec<(u8, u32)>> {
    if comparable {
        let direct: Option<Vec<_>> = rows
            .as_chunks::<57>()
            .0
            .iter()
            .filter(|r| r[45] == 2 && r[32] > 0)
            .map(|r| race_gap(rows, r).map(|gap| (r[32], gap)))
            .collect();
        if direct.is_some() {
            return direct;
        }
    }
    linked_forecast_gaps(rows, track_length)
}

// Follow measured intervals between consecutive on-track positions. Independent
// leader clocks bound a missing group; at the tail only the forward chain exists.
// Never use these forecast-only clocks as pit-loss observations.
fn linked_forecast_gaps(rows: &[u8], track_length: u16) -> Option<Vec<(u8, u32)>> {
    let mut cars: Vec<_> = rows
        .as_chunks::<57>()
        .0
        .iter()
        .filter(|r| r[45] == 2 && r[32] > 0)
        .map(<[u8; 57]>::as_slice)
        .collect();
    cars.sort_unstable_by_key(|r| r[32]);
    let leader = *cars.first()?;
    if leader[32] != 1 || cars.windows(2).any(|pair| pair[0][32] == pair[1][32]) {
        return None;
    }
    let lap_reference = cars
        .iter()
        .map(|r| u32_at(r, 0))
        .filter(|lap| (30_000..=600_000).contains(lap))
        .min();
    let distance = |r: &[u8]| f32::from_bits(u32_at(r, 20));
    let circuit = 0.0..(f32::from(track_length) + 1.0);
    let mut direct = Vec::with_capacity(cars.len());
    for car in &cars {
        if u16_at(car, 17) >= 60_000 {
            return None;
        }
        direct.push(valid_gap(car).then(|| if car[32] == 1 { 0 } else { split(car, 17) }));
    }
    let interval = |ahead: &[u8], car: &[u8]| {
        (ahead[32].checked_add(1) == Some(car[32])
            && ahead[34] == 0
            && car[34] == 0
            && u16_at(car, 14) < 60_000
            && split(car, 14) > 0)
            .then(|| split(car, 14))
    };
    let mut forward = direct.clone();
    for i in 1..cars.len() {
        forward[i] =
            direct[i].or_else(|| forward[i - 1]?.checked_add(interval(cars[i - 1], cars[i])?));
    }
    let mut backward = direct.clone();
    for i in (1..cars.len()).rev() {
        backward[i - 1] =
            direct[i - 1].or_else(|| backward[i]?.checked_sub(interval(cars[i - 1], cars[i])?));
    }
    let mut result: Vec<(u8, u32)> = Vec::with_capacity(cars.len());
    for (i, car) in cars.iter().enumerate() {
        let laps = leader[33].checked_sub(car[33])?;
        if car[33] == 0 || track_length == 0 || !circuit.contains(&distance(car)) {
            return None;
        }
        if forward[i]
            .zip(backward[i])
            .is_some_and(|(a, b)| a.abs_diff(b) > 500)
        {
            return None;
        }
        let gap = forward[i].or(backward[i]).or_else(|| race_gap(rows, car))?;
        let whole_laps = laps.saturating_sub(u8::from(distance(car) > distance(leader)));
        if whole_laps > 0 && gap < u32::from(whole_laps) * lap_reference? {
            return None;
        }
        if i > 0 && (direct[i].is_none() || direct[i - 1].is_none()) && result.last()?.1 > gap {
            return None;
        }
        result.push((car[32], gap));
    }
    Some(result)
}

#[cfg(test)]
mod gap_tests {
    use super::*;

    fn car(rank: u8, lap: u8, gap: u32, interval: u32) -> [u8; 57] {
        let mut r = [0; 57];
        r[..4].copy_from_slice(&80_000u32.to_le_bytes());
        r[20..24].copy_from_slice(&500.0f32.to_le_bytes());
        r[32] = rank;
        r[33] = lap;
        r[45] = 2;
        for (offset, ms) in [(14, interval), (17, gap)] {
            r[offset..offset + 2].copy_from_slice(&((ms % 60_000) as u16).to_le_bytes());
            r[offset + 2] = (ms / 60_000) as u8;
        }
        r
    }

    #[test]
    fn consecutive_lapped_cars_need_a_measured_chain() {
        let mut cars = [
            car(1, 6, 0, 0),
            car(2, 6, 56_000, 56_000),
            car(3, 5, 0, 26_000),
            car(4, 5, 0, 3_000),
        ];
        assert_eq!(
            forecast_gaps(&cars.concat(), 5000, false).unwrap()[2..],
            [(3, 82_000), (4, 85_000)]
        );
        cars[2][34] = 2;
        assert!(forecast_gaps(&cars.concat(), 5000, false).is_none());
        cars[2] = car(3, 5, 0, 2000);
        assert!(forecast_gaps(&cars.concat(), 5000, false).is_none());
    }

    #[test]
    fn consecutive_missing_clocks_can_be_read_from_behind() {
        let mut cars = [
            car(1, 6, 0, 0),
            car(2, 6, 0, 0),
            car(3, 6, 0, 3000),
            car(4, 6, 9000, 4000),
        ];
        assert_eq!(
            forecast_gaps(&cars.concat(), 5000, true).unwrap()[1..3],
            [(2, 2000), (3, 5000)]
        );
        cars[1] = car(2, 6, 0, 8000);
        assert!(forecast_gaps(&cars.concat(), 5000, true).is_none());
        cars[2] = car(3, 6, 0, 0);
        cars[1][34] = 2;
        cars[2][34] = 2;
        assert!(forecast_gaps(&cars.concat(), 5000, true).is_none());
    }
}

// Session v1 (both formats): packed pairs of lap fraction and signed FIA flag.
fn marshal_zones(session: &[u8]) -> Vec<(f32, i8)> {
    let count = usize::from(session[47]);
    if count > 21 {
        return vec![];
    }
    let mut zones = Vec::with_capacity(count);
    for i in 0..count {
        let offset = 48 + 5 * i;
        let start = f32::from_bits(u32_at(session, offset));
        if !(0.0..=1.0).contains(&start) {
            // Dropping a single boundary would wrongly extend its preceding zone.
            return vec![];
        }
        zones.push((start, session[offset + 4] as i8));
    }
    zones.sort_by(|a, b| a.0.total_cmp(&b.0));
    zones
}

fn length(format: u16, id: u8) -> Option<usize> {
    let sizes = match id {
        0 => (1349, 1325),
        1 => (753, 926),
        2 => (1285, 1399),
        3 => (45, 45),
        4 => (1284, 1470),
        6 => (1352, 1448),
        7 => (1239, 1445),
        10 => (1041, 1133),
        11 => (1460, 1460),
        12 => (231, 231),
        _ => return None,
    };
    Some(if format == 2026 { sizes.1 } else { sizes.0 })
}
// Distance, km/h, throttle %, brake %, ERS MJ, mean surface temperature °C.
type TracePoint = (f32, u16, Option<u8>, Option<u8>, Option<f32>, f32);
// Frame, event code, involved driver, lap and event-specific wire fields.
type TimingEvent = (u32, String, u8, u8, Vec<u8>);
#[derive(Default, Clone)]
pub(crate) struct Feed {
    exit_timing: crate::exit_timing::ExitTiming,
    minis: crate::mini_timing::MiniTiming,
    practice: crate::practice::Practice,
    trace: Arc<BTreeMap<(u8, u8), (u32, TracePoint)>>,
    trace_driver: Option<u8>,
    slow_laps: BTreeMap<(u8, u8), u32>,
    trends: [crate::pace::GapTrend; 2],
    lap_battles: [crate::pace::LapBattle; 2],
    pub(crate) history: History,
    loss_basis: Option<(i8, u32, usize)>,
    neutral_loss: [Option<(u32, usize)>; 2],
    field_inside: Vec<Option<bool>>,
    field_visits: BTreeMap<usize, FieldVisit>,
    pub(crate) field_losses: Vec<(u32, Observation)>,
    visit: Option<Visit>,
    pub(crate) legacy_pit_prior: bool,
    game_pit_prior: Option<u32>,
    pub(crate) fixed_replay_loss: bool,
    pub(crate) stops: Vec<Stop>,
    pub(crate) stop_history: Vec<Stop>,
    prediction: Option<u8>,
    last_rejoin: Option<(u8, u8)>,
    rejoin_clock: Option<(u64, u8)>,
    entry_equipment: Equipment,
    scenarios: Option<Scenarios>,
    scenario_clock: Option<(u64, u8, u8)>,
    work_loss: [[Option<(u32, usize)>; 4]; 3],
    tyre_validation: [crate::pit_calibration::Validation; 3],
    previous_pit: Option<bool>,
    previous_ms: Option<u64>,
    pending: Option<usize>,
    player_slot: Option<u8>,
    uid: Option<u64>,
    format: u16,
    old: VecDeque<u64>,
    pub(crate) epoch: u64,
    floor: u32,
    rewind_limits: Vec<(u32, u32)>,
    lap_packet_ms: u64,
    packets: BTreeMap<(u8, u8), Arc<[u8]>>,
    events: VecDeque<TimingEvent>,
    prior_events: VecDeque<(u64, TimingEvent)>,
    button_frame: Option<u32>,
    buttons_held: u32,
    pressed_actions: VecDeque<u8>,
    lap_at: Option<Instant>,
    accepted: u64,
    rejected: u64,
    fault: Option<String>,
}
#[derive(Clone)]
struct FieldVisit {
    safety: u8,
    wet: Option<bool>,
    track: i8,
    measurement: Visit,
    equipment: Equipment,
    service_ms: u16,
}

impl Feed {
    pub(crate) fn seeded(history: History) -> Self {
        Self {
            history,
            ..Default::default()
        }
    }

    pub(crate) fn observations(&self, track: i8) -> impl Iterator<Item = Observation> + '_ {
        self.stops
            .iter()
            .filter_map(move |s| s.observation(self.format, track))
            .chain(self.field_losses.iter().map(|s| s.1))
    }

    pub(crate) fn archive_losses(&mut self, end: u64) {
        if let Some(session) = self.packets.get(&(1, 0)) {
            let samples: Vec<_> = self
                .observations(session[36] as i8)
                .map(|mut s| {
                    s.origin = self.uid.map(|uid| (uid, end));
                    s
                })
                .collect();
            Arc::make_mut(&mut self.history).extend(samples);
        }
    }

    fn rain_class(&self, weather: u8) -> Option<bool> {
        (!self.legacy_pit_prior && weather <= 5).then_some(weather >= 3)
    }

    fn refresh_losses(&mut self, profile: Option<Profile>, track: i8, fallback: u32) {
        let wet = self
            .packets
            .get(&(1, 0))
            .and_then(|s| self.rain_class(s[29]));
        let groups = groups(
            self.history
                .iter()
                .copied()
                .chain(self.observations(track))
                .filter(|s| {
                    Some(s.condition.profile) == profile
                        && s.condition.track == track
                        && s.condition.format == self.format
                }),
        );
        for stop in self.stops.iter_mut().filter(|s| s.profile == profile) {
            stop.service_delayed = stop
                .observation(self.format, track)
                .and_then(|s| groups.get(&s.condition).map(|g| !g.includes(s.service)));
        }
        let mut baseline = [None; 3];
        for safety in 0..=2 {
            let group = |work| {
                profile.and_then(|profile| {
                    groups.get(&Condition {
                        format: self.format,
                        track,
                        wet,
                        profile,
                        safety,
                        work,
                    })
                })
            };
            let player = group(Work::Tyres);
            let wing = group(Work::FrontWing);
            let (tyres, validation) = crate::pit_calibration::estimate(player, None, self.uid);
            self.tyre_validation[usize::from(safety)] = validation;
            self.work_loss[usize::from(safety)] = [
                tyres,
                crate::pit_calibration::estimate(wing, None, self.uid).0,
                player.and_then(|g| average(&g.totals(false))),
                wing.and_then(|g| average(&g.totals(false))),
            ];
            if !self.fixed_replay_loss {
                baseline[usize::from(safety)] =
                    crate::pit_calibration::estimate(player, group(Work::RivalTyres), self.uid).0;
            }
        }
        self.game_pit_prior = self
            .packets
            .get(&(1, 0))
            .filter(|_| !self.legacy_pit_prior)
            .and_then(|s| crate::track_pits::estimate(s, self.format));
        let (ms, n) = baseline[0].unwrap_or((self.game_pit_prior.unwrap_or(fallback), 0));
        self.loss_basis = Some((track, ms, n));
        self.neutral_loss = [baseline[1], baseline[2]];
    }

    pub(crate) fn ingest(&mut self, b: &[u8], ms: u64, pit_loss: u32) {
        if b.len() < 29 {
            self.rejected += 1;
            return;
        }
        let format = u16_at(b, 0);
        let id = b[6];
        if !matches!(format, 2025 | 2026) {
            self.rejected += 1;
            return;
        }
        let Some(size) = length(format, id) else {
            return;
        };
        let slots = if format == 2026 { 24 } else { 22 };
        if b.len() != size
            || b[5] != 1
            || (id == 11 && (b[29] >= slots || b[30] > 100 || b[31] > 8))
            || (id == 4 && b[29] > slots)
            || (id == 12 && b[29] >= slots)
        {
            self.rejected += 1;
            return;
        }
        let uid = u64::from_le_bytes(b[7..15].try_into().unwrap());
        if self.uid != Some(uid) {
            if self.old.contains(&uid) {
                return;
            }
            if let Some(previous) = self.uid {
                self.archive_losses(
                    std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_millis() as u64,
                );
                self.old.push_back(previous);
                if self.old.len() > 8 {
                    self.old.pop_front();
                }
            }
            self.stop_history.clear();
            self.stops.clear();
            self.prior_events.clear();
            self.rewind_limits.clear();
            self.uid = Some(uid);
            self.format = format;
            self.reset(0);
        }
        if self.format != format {
            self.rejected += 1;
            return;
        }
        let frame = u32_at(b, 23);
        if frame < self.floor {
            return;
        }
        if id == 3 {
            if &b[29..33] == b"BUTN" {
                if self.button_frame.is_some_and(|last| frame < last) {
                    return;
                }
                let held = u32_at(b, 33) >> 20;
                let pressed = held & !self.buttons_held;
                self.buttons_held = held;
                self.button_frame = Some(frame);
                for bit in 0..12 {
                    if pressed & (1 << bit) != 0 && self.pressed_actions.len() < 64 {
                        self.pressed_actions.push_back(bit + 1);
                    }
                }
                self.accepted += 1;
                return;
            }
            let code = String::from_utf8_lossy(&b[29..33]).into_owned();
            if !matches!(
                code.as_str(),
                "FLBK"
                    | "FTLP"
                    | "RTMT"
                    | "RDFL"
                    | "OVTK"
                    | "COLL"
                    | "DTSV"
                    | "SGSV"
                    | "SCAR"
                    | "PENA"
                    | "RCWN"
                    | "LGOT"
                    | "SEND"
                    | "SSTA"
            ) {
                return;
            }
            if matches!(code.as_str(), "OVTK" | "COLL") && !b[33..35].contains(&b[27]) {
                return;
            }
            let (driver, details) = match code.as_str() {
                "PENA" => (b[35], &b[33..40]),
                "OVTK" | "COLL" => (b[33], &b[34..35]),
                "FTLP" | "RTMT" | "RCWN" | "DTSV" | "SGSV" => (b[33], &b[0..0]),
                "SCAR" => (255, &b[33..35]),
                _ => (255, &b[0..0]),
            };
            if self.events.iter().any(|(f, c, slot, _, data)| {
                *f == frame && c == &code && *slot == driver && data == details
            }) {
                return;
            }
            let observed_lap = self
                .packets
                .get(&(2, 0))
                .and_then(|p| p.get(29 + 57 * usize::from(p[27]) + 33))
                .copied()
                .unwrap_or(0);
            if code == "FLBK" {
                self.rewind(frame, u32_at(b, 33));
            }
            let lap = if code == "PENA" && (1..255).contains(&b[38]) {
                b[38]
            } else {
                observed_lap
            };
            self.events
                .push_front((frame, code, driver, lap, details.to_vec()));
            self.events.truncate(16);
        } else {
            let key = (id, if matches!(id, 11 | 12) { b[29] } else { 0 });
            if let Some(prior) = self.packets.get(&key) {
                if u32_at(prior, 23) >= frame {
                    return;
                }
                if id == 1 && (prior[29] != b[29] || prior[42] != b[42] || prior[36] != b[36]) {
                    self.loss_basis = None;
                }
                if id == 1 && Profile::from_session(prior) != Profile::from_session(b) {
                    self.loss_basis = None;
                    self.field_visits.clear();
                    self.field_inside.clear();
                    self.scenarios = None;
                    self.scenario_clock = None;
                    self.last_rejoin = None;
                    self.rejoin_clock = None;
                    if let Some(index) = self.pending {
                        self.stops[index].profile = None;
                    }
                }
                if id == 2 && u32_at(b, 19) < u32_at(prior, 19) {
                    self.rewind(frame, u32_at(b, 19));
                }
            }
            if id == 2 {
                self.lap_at = Some(Instant::now());
                self.lap_packet_ms = ms;
            }
            self.packets.insert(key, Arc::from(b));
            if id == 1 {
                if self.loss_basis.is_none() && !self.legacy_pit_prior {
                    self.refresh_losses(Profile::from_session(b), b[36] as i8, pit_loss);
                }
                if let Some(idx) = self.pending {
                    let stop = &mut self.stops[idx];
                    if stop.safety_states.last() != Some(&b[153]) {
                        stop.safety_changed = true;
                        stop.safety_states.push(b[153]);
                    }
                }
            }
            if id == 1
                && (b[153] > 2
                    || self
                        .pending
                        .is_some_and(|idx| self.stops[idx].safety != b[153])
                    || (b[36] as i8) < 0
                    || (b[153] == 0 && marshal_zones(b).iter().any(|(_, flag)| *flag >= 3)))
            {
                self.visit = None;
            }
            if id == 7 && b[27] < slots {
                let flag = b[29 + usize::from(b[27]) * if format == 2026 { 59 } else { 55 } + 28];
                if flag == 4 || (flag == 3 && self.packets.get(&(1, 0)).is_none_or(|s| s[153] == 0))
                {
                    self.visit = None;
                }
            }
            if id == 2 {
                if let Some(s) = self.packets.get(&(1, 0)).filter(|s| matches!(s[35], 1..=4)) {
                    if let Some(status) = self.packets.get(&(7, 0)) {
                        self.practice.observe(
                            b,
                            status,
                            s,
                            self.packets.get(&(10, 0)).map(AsRef::as_ref),
                            format == 2026,
                        );
                    }
                }
                if let Some(s) = self.packets.get(&(1, 0)) {
                    self.minis.observe(
                        &b[29..29 + usize::from(slots) * 57],
                        [
                            0.0,
                            f32::from_bits(u32_at(s, 745)),
                            f32::from_bits(u32_at(s, 749)),
                            f32::from(u16_at(s, 33)),
                        ],
                    );
                }
                self.observe_field_pits(b);
                self.observe_pit(b, ms, pit_loss);
                self.observe_battle(b);
            }
            if id == 6 {
                self.observe_trace(b);
            }
        }
        self.accepted += 1;
    }
    fn observe_trace(&mut self, telemetry: &[u8]) {
        let (Some(l), Some(s)) = (self.packets.get(&(2, 0)), self.packets.get(&(1, 0))) else {
            return;
        };
        let slot = usize::from(telemetry[27]);
        let modern = self.format == 2026;
        if s[44] != 0
            || l[27] != telemetry[27]
            || slot >= if modern { 24 } else { 22 }
            || u32_at(l, 23).abs_diff(u32_at(telemetry, 23)) > 12
        {
            return;
        }
        let a = &l[29 + slot * 57..];
        let metres = f32::from_bits(u32_at(a, 20));
        let length = f32::from(u16_at(s, 33));
        if a[33] == 0 || a[45] != 2 || !(0.0..length).contains(&metres) {
            return;
        }
        let key = (a[33], (32.0 * metres / length) as u8);
        if self.trace_driver != Some(telemetry[27]) {
            self.trace = Default::default();
            self.trace_driver = Some(telemetry[27]);
        }
        if self.trace.contains_key(&key) {
            return;
        }
        let t = &telemetry[29 + slot * if modern { 59 } else { 60 }..];
        let pedal = |i| {
            let v = f32::from_bits(u32_at(t, i));
            (0.0..=1.0)
                .contains(&v)
                .then_some((100.0 * v).round() as u8)
        };
        let energy = self.packets.get(&(7, 0)).and_then(|p| {
            if u32_at(p, 23).abs_diff(u32_at(telemetry, 23)) > 120 {
                return None;
            }
            let joules = f32::from_bits(u32_at(p, 29 + slot * if modern { 59 } else { 55 } + 37));
            (joules.is_finite() && joules >= 0.0).then_some(joules / 1e6)
        });
        let temperature = t[30..34].iter().map(|v| u16::from(*v)).sum::<u16>() as f32 / 4.0;
        Arc::make_mut(&mut self.trace).insert(
            key,
            (
                u32_at(telemetry, 19),
                (
                    metres,
                    u16_at(t, 0),
                    pedal(2),
                    pedal(10),
                    energy,
                    temperature,
                ),
            ),
        );
    }
    pub(crate) fn analysis<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        d.set_item(
            "samples",
            self.trace
                .iter()
                .map(|((lap, bin), (_, p))| (*lap, *bin, *p))
                .collect::<Vec<_>>(),
        )?;
        let frame = self.render(py)?;
        d.set_item("frame", frame)?;
        Ok(d)
    }
    fn observe_battle(&mut self, lap: &[u8]) {
        let slots = if self.format == 2026 { 24 } else { 22 };
        let rows = &lap[29..29 + slots * 57];
        let player = usize::from(lap[27]);
        let Some(session) = self.packets.get(&(1, 0)) else {
            return;
        };
        if session[43] != 0 {
            return;
        }
        let time = f32::from_bits(u32_at(lap, 15));
        if player >= slots
            || !time.is_finite()
            || time < 0.
            || session[44] != 0
            || !matches!(session[35], 15..=17 | 19 | 20)
            || session[153] == 3
        {
            self.trends = Default::default();
            self.lap_battles = Default::default();
            return;
        }
        let me = &rows[player * 57..][..57];
        for (side, trend) in self.trends.iter_mut().enumerate() {
            let display = &mut self.lap_battles[side];
            let pos = i16::from(me[32]) + if side == 0 { -1 } else { 1 };
            let other = rows
                .as_chunks::<57>()
                .0
                .iter()
                .enumerate()
                .find(|(_, r)| i16::from(r[32]) == pos && r[45] == 2);
            let Some((slot, rival)) = other else {
                *display = Default::default();
                *trend = Default::default();
                continue;
            };
            let (lead, follow, pair) = if side == 0 {
                (rival.as_slice(), me, (slot as u8, player as u8))
            } else {
                (me, rival.as_slice(), (player as u8, slot as u8))
            };
            if lead[34] != 0 || follow[34] != 0 || lead[46] != 0 || follow[46] != 0 || me[45] != 2 {
                *display = Default::default();
            }
            let adjacent_laps = lead[33].checked_sub(follow[33]) == Some(1)
                && f32::from_bits(u32_at(lead, 20)) < f32::from_bits(u32_at(follow, 20));
            let gap = split(follow, 14);
            // After an overtake the interval packet can still name the old
            // neighbour implicitly. The two gaps to the leader update separately.
            let leader_gap = split(follow, 17).saturating_sub(split(lead, 17));
            if me[45] != 2
                || me[32] == 0
                || follow[33] == 0
                || (lead[33] != follow[33] && !adjacent_laps)
                || [lead, follow].iter().any(|r| r[34] != 0 || r[46] != 0)
                || u16_at(follow, 14) >= 60000
                || gap == 0
                || gap.abs_diff(leader_gap) > 2000.max(leader_gap / 5)
            {
                *trend = Default::default();
                continue;
            }
            trend.observe(pair, (time * 1000.).round() as u32, gap);
            // Both cars must have crossed before publishing a new lap average.
            if lead[33] == follow[33] {
                display.observe(pair, me[33], gap, |oldest| {
                    let mut deltas = Vec::new();
                    for n in (oldest..me[33]).rev().take(5) {
                        if self.slow_laps.contains_key(&(pair.0, n))
                            || self.slow_laps.contains_key(&(pair.1, n))
                        {
                            continue;
                        }
                        let clean = |slot, r| {
                            completed_battle_lap(
                                r,
                                self.packets.get(&(11, slot)).map(|p| p.as_ref()),
                                n,
                            )
                            .filter(|ms| (30_000..=600_000).contains(ms))
                        };
                        if let (Some(a), Some(b)) = (clean(pair.0, lead), clean(pair.1, follow)) {
                            deltas.push(i64::from(a) - i64::from(b));
                            if deltas.len() == 3 {
                                break;
                            }
                        }
                    }
                    deltas
                });
            }
        }
    }

    fn equipment(&self, slot: usize, lap: &[u8]) -> Equipment {
        let fresh = |packet: &[u8]| {
            let dt = f32::from_bits(u32_at(lap, 15)) - f32::from_bits(u32_at(packet, 15));
            (-0.2..=2.0).contains(&dt)
        };
        let mut eq = Equipment::default();
        if let Some(p) = self.packets.get(&(10, 0)).filter(|p| fresh(p)) {
            let off = 29 + slot * 46;
            let frame = u32_at(p, 23);
            let damage: Damage = p[off + 28..off + 34].try_into().unwrap();
            eq.damage = damage.iter().all(|v| *v <= 100).then_some((frame, damage));
            let wear = [0, 4, 8, 12].map(|i| f32::from_bits(u32_at(p, off + i)));
            eq.wear = wear
                .iter()
                .all(|v| (0.0..=100.).contains(v))
                .then_some((frame, wear));
        }
        if let Some(p) = self.packets.get(&(7, 0)).filter(|p| fresh(p)) {
            let off = 29 + slot * if self.format == 2026 { 59 } else { 55 };
            if p[off + 25] != 0 && p[off + 25] != 255 {
                eq.tyre = Some((u32_at(p, 23), p[off + 25], p[off + 27]));
            } else if matches!(p[off + 26], 7 | 8 | 16..=18) {
                eq.tyre = Some((u32_at(p, 23), p[off + 26], p[off + 27]));
            }
        }
        if let Some(p) = self
            .packets
            .get(&(12, slot as u8))
            .filter(|p| fresh(p) && p[230] < 20)
        {
            eq.fitted = Some((u32_at(p, 23), p[230]));
        }
        eq
    }

    fn observe_field_pits(&mut self, lap: &[u8]) {
        let Some(session) = self.packets.get(&(1, 0)) else {
            return;
        };
        let safety = session[153];
        if session[43] != 0 {
            return;
        }
        let slots = if self.format == 2026 { 24 } else { 22 };
        let rows = &lap[29..29 + slots * 57];
        let clock = (f32::from_bits(u32_at(lap, 15)) * 1000.).round() as u64;
        let contiguous = self
            .previous_ms
            .is_some_and(|t| clock.checked_sub(t).is_some_and(|d| d <= 2000));
        if !contiguous
            || !matches!(session[35], 15..=17 | 19 | 20)
            || (session[36] as i8) < 0
            || safety > 2
            || (safety == 0 && marshal_zones(session).iter().any(|z| z.1 >= 3))
            || !comparable_laps(rows, u16_at(session, 33))
        {
            self.field_visits.clear();
            self.field_inside.clear();
        }
        // Packet 11 has validity bits but no historical flag or penalty state.
        // Remember the first affected frame so flashbacks discard only future evidence.
        let caution = safety != 0 || marshal_zones(session).iter().any(|z| z.1 >= 3);
        let can_start = self.field_inside.len() == slots && contiguous && safety <= 2;
        self.field_inside.resize(slots, None);
        for (slot, car) in rows.as_chunks::<57>().0.iter().enumerate() {
            let inside = car[46] == 1 || car[34] == 2;
            let previous = self.field_inside[slot].replace(inside);
            let visible = self.packets.get(&(4, 0)).is_some_and(|p| {
                let h = &p[30 + slot * if self.format == 2026 { 60 } else { 57 }..];
                session[154] == 0 || h[0] == 1 || h[if self.format == 2026 { 42 } else { 39 }] == 1
            });
            let equipment = self.equipment(slot, lap);
            let flag = self
                .packets
                .get(&(7, 0))
                .map(|p| p[29 + slot * if self.format == 2026 { 59 } else { 55 } + 28]);
            if car[45] == 2
                && car[33] > 0
                && (caution
                    || matches!(flag, Some(3 | 4))
                    || car[34] != 0
                    || matches!(car[44], 2 | 3))
            {
                self.slow_laps
                    .entry((slot as u8, car[33]))
                    .or_insert(u32_at(lap, 19));
            }
            if flag == Some(4)
                || (flag == Some(3) && safety == 0)
                || slot == usize::from(lap[27])
                || !visible
                || car[45] != 2
                || car[51] != 0
            {
                self.field_visits.remove(&slot);
                continue;
            }
            let track = session[36] as i8;
            let wet = self.rain_class(session[29]);
            if can_start && inside && previous == Some(false) {
                self.field_visits.insert(
                    slot,
                    FieldVisit {
                        safety,
                        wet,
                        track,
                        measurement: Visit::start(rows, slot, clock, u16_at(session, 33)),
                        equipment,
                        service_ms: 0,
                    },
                );
            }
            if let Some(visit) = self.field_visits.get_mut(&slot) {
                if visit.safety != safety
                    || visit.wet != wet
                    || visit.track != track
                    || visit.equipment.damage.zip(equipment.damage).is_some_and(
                        |((_, entry), (_, now))| now.iter().zip(entry).any(|(new, old)| *new < old),
                    )
                {
                    self.field_visits.remove(&slot);
                    continue;
                }
                visit.service_ms = visit.service_ms.max(u16_at(car, 49));
                visit.measurement.update(rows, car, clock);
                if !inside {
                    if let Some(sample) = self.field_visits.remove(&slot).and_then(|v| {
                        let profile = Profile::from_session(session)?;
                        let (before, after) = v.equipment.damage.zip(equipment.damage)?;
                        if before.0 >= after.0
                            || v.equipment.changed_tyres(equipment) != Some(true)
                            || v.service_ms == 0
                        {
                            return None;
                        }
                        Some(Observation {
                            origin: None,
                            condition: Condition {
                                format: self.format,
                                track,
                                wet,
                                safety,
                                profile,
                                work: Work::RivalTyres,
                            },
                            service: v.service_ms,
                            loss: Some(v.measurement.loss(rows, car, clock)?.0),
                        })
                    }) {
                        self.field_losses.push((u32_at(lap, 19), sample));
                        self.loss_basis = None;
                    }
                }
            }
        }
    }
    fn observe_pit(&mut self, lap: &[u8], ms: u64, pit_loss: u32) {
        let previous_prediction = self.prediction.take();
        let player = lap[27];
        let old_player = self.player_slot.replace(player);
        let same_player = old_player == Some(player);
        // The session clock stops with the game. Wall-clock silence in the
        // pause menu must not split a single pit visit.
        let clock_s = f32::from_bits(u32_at(lap, 15));
        let clock_ms = (clock_s * 1000.).round() as u64;
        let recent = self.previous_ms.replace(clock_ms).is_some_and(|before| {
            clock_s.is_finite() && clock_ms.checked_sub(before).is_some_and(|dt| dt <= 2000)
        });
        let Some(session) = self.packets.get(&(1, 0)).cloned() else {
            return;
        };
        let slots = if self.format == 2026 { 24 } else { 22 };
        if usize::from(player) >= slots
            || session[44] != 0
            || !matches!(session[35], 15..=17 | 19 | 20)
        {
            self.previous_pit = None;
            self.pending = None;
            self.visit = None;
            return;
        }
        let rows = &lap[29..29 + slots * 57];
        let me = &rows[usize::from(player) * 57..][..57];
        if me[45] != 2 || me[32] == 0 || me[32] as usize > slots {
            self.previous_pit = None;
            self.pending = None;
            self.visit = None;
            return;
        }
        let inside = me[46] == 1 || me[34] == 2;
        if session[43] != 0 {
            if same_player && !inside {
                self.prediction = previous_prediction;
            }
            return;
        }
        let previous = self.previous_pit.replace(inside);
        if !same_player || !recent {
            self.pending = None;
            self.visit = None;
        }
        if !same_player {
            if old_player.is_some() {
                self.exit_timing = Default::default();
            }
            self.last_rejoin = None;
            self.rejoin_clock = None;
            self.scenarios = None;
            self.scenario_clock = None;
        }
        let exiting = !inside && previous == Some(true) && self.pending.is_some();
        if clock_s.is_finite() && clock_s >= 0. {
            self.exit_timing.observe(
                rows,
                clock_ms,
                u16_at(&session, 33),
                u32_at(lap, 19),
                exiting.then_some((ms, usize::from(player))),
            );
        }
        let equipment = self.equipment(usize::from(player), lap);
        let profile = Profile::from_session(&session);
        let wet = self.rain_class(session[29]);
        let track = session[36] as i8;
        let clean = track >= 0
            && session[153] <= 2
            && me[51] == 0
            && (session[153] != 0 || !marshal_zones(&session).iter().any(|(_, flag)| *flag >= 3))
            && !self.packets.get(&(7, 0)).is_some_and(|p| {
                let flag =
                    p[29 + usize::from(player) * if self.format == 2026 { 59 } else { 55 } + 28];
                flag == 4 || (flag == 3 && session[153] == 0)
            });
        if !clean {
            self.visit = None;
        }
        if inside && (previous != Some(true) || !same_player || !recent) {
            let observed_entry = same_player && recent && previous == Some(false);
            self.entry_equipment = if observed_entry {
                equipment
            } else {
                Equipment::default()
            };
            self.stops.push(Stop {
                wet,
                safety: session[153],
                epoch: self.epoch,
                lap: me[33],
                entry_ms: ms,
                predicted: if same_player && recent && previous == Some(false) {
                    self.rejoin_clock
                        .filter(|(at, safety)| {
                            *safety == session[153]
                                && clock_ms.checked_sub(*at).is_some_and(|dt| dt <= 2000)
                        })
                        .and(self.last_rejoin)
                        .filter(|(_, lap)| *lap == me[33])
                        .map(|(rank, _)| rank)
                } else {
                    None
                },
                profile,
                damage_in: self.entry_equipment.damage.map(|(_, d)| d),
                damage_out: None,
                tyre_changed: None,
                safety_changed: false,
                safety_states: vec![session[153]],
                measured_loss_ms: None,
                transit_references: 0,
                service_delayed: None,
                service_safety: None,
                scenarios: self
                    .scenario_clock
                    .filter(|(at, safety, number)| {
                        observed_entry
                            && *safety == session[153]
                            && (*number == me[33] || number.checked_add(1) == Some(me[33]))
                            && clock_ms.checked_sub(*at).is_some_and(|dt| dt <= 2000)
                    })
                    .and(self.scenarios),
                actual: None,
                exit_ms: None,
                exit_frame: None,
                wing_repair: false,
                service_ms: 0,
                penalty: false,
            });
            self.pending = Some(self.stops.len() - 1);
            if recent
                && same_player
                && previous == Some(false)
                && clean
                && comparable_laps(rows, u16_at(&session, 33))
            {
                self.visit = Some(Visit::start(
                    rows,
                    usize::from(player),
                    clock_ms,
                    u16_at(&session, 33),
                ));
            }
        }
        if let Some(idx) = self.pending {
            let stop = &mut self.stops[idx];
            let service_ms = u16_at(me, 49);
            if service_ms > stop.service_ms {
                // Keep a mixed stationary phase separate from Green, SC and VSC.
                stop.service_safety = Some(match stop.service_safety {
                    Some(first) if first != session[153] => 4,
                    _ => session[153],
                });
                stop.service_ms = service_ms;
            }
            stop.penalty |= me[51] != 0;
            if let Some(((start, before), (end, now))) =
                self.entry_equipment.damage.zip(equipment.damage)
            {
                if end > start {
                    stop.wing_repair |= now[0] < before[0] || now[1] < before[1];
                }
            }
            stop.safety_changed |= stop.safety != session[153];
            if stop.safety_changed || stop.penalty || stop.wet != wet {
                self.visit = None;
            }
        }
        if let Some(visit) = &mut self.visit {
            if comparable_laps(rows, u16_at(&session, 33)) {
                visit.update(rows, me, clock_ms);
            } else {
                self.visit = None;
            }
        }
        if !inside && previous == Some(true) {
            if let Some(index) = self.pending.take() {
                self.stops[index].actual = Some(me[32]);
                self.stops[index].exit_ms = Some(ms);
                self.stops[index].exit_frame = Some(u32_at(lap, 19));
                let stop = &mut self.stops[index];
                stop.tyre_changed = self.entry_equipment.changed_tyres(equipment);
                stop.damage_out = self
                    .entry_equipment
                    .damage
                    .zip(equipment.damage)
                    .filter(|(a, b)| b.0 > a.0)
                    .map(|(_, b)| b.1);
                if let Some((loss, references)) =
                    self.visit.take().and_then(|v| v.loss(rows, me, clock_ms))
                {
                    stop.measured_loss_ms = Some(loss);
                    stop.transit_references = references;
                }
                self.loss_basis = None;
            }
        }
        if self.loss_basis.is_none_or(|basis| basis.0 != track) {
            self.refresh_losses(profile, track, pit_loss);
        }
        if self.packets.get(&(7, 0)).is_some_and(|p| {
            p[29 + usize::from(player) * if self.format == 2026 { 59 } else { 55 } + 28] == 4
        }) {
            return;
        }
        if inside || me[33] == 0 || me[33] >= session[32] || session[153] == 3 {
            return;
        }
        let Some(participants) = self.packets.get(&(4, 0)) else {
            return;
        };
        let active: Vec<_> = rows
            .as_chunks::<57>()
            .0
            .iter()
            .filter(|r| r[45] == 2 && r[32] > 0)
            .collect();
        if active.len() != usize::from(participants[29])
            && rows
                .as_chunks::<57>()
                .0
                .iter()
                .filter(|r| r[45] >= 3)
                .count()
                + active.len()
                != usize::from(participants[29])
            || active.is_empty()
            || me[32] > participants[29]
            || active.iter().any(|r| r[32] > participants[29])
        {
            return;
        }
        let length = u16_at(&session, 33);
        let Some(gaps) = forecast_gaps(rows, length, comparable_laps(rows, length)) else {
            return;
        };
        let mut gap_by_position = [0; 256];
        for (position, gap) in gaps {
            gap_by_position[usize::from(position)] = gap;
        }
        let loss = self.neutral_for(session[153]).map_or_else(
            || {
                crate::forecast::pit_loss_ms(
                    self.loss_basis.unwrap().1,
                    matches!(session[153], 1 | 2),
                )
            },
            |v| v.0,
        );
        let rank_for = |player_loss| {
            let finish = gap_by_position[usize::from(me[32])]
                + player_loss
                + if me[51] == 1 {
                    u32::from(me[38]) * 1000
                } else {
                    0
                };
            let rank = 1 + rows
                .as_chunks::<57>()
                .0
                .iter()
                .enumerate()
                .filter(|(slot, r)| {
                    if r[45] != 2 || r[32] == 0 || r[32] == me[32] {
                        return false;
                    }
                    let remaining = self
                        .field_visits
                        .get(slot)
                        .and_then(|v| v.measurement.delta(rows, *r))
                        .map(|ms| loss.saturating_sub(ms))
                        .unwrap_or_else(|| if r[44] == 2 && r[46] == 0 { loss } else { 0 });
                    (gap_by_position[usize::from(r[32])] + remaining, r[32]) < (finish, me[32])
                })
                .count();
            rank as u8
        };
        if let Some(losses) = profile.and_then(|p| self.service_losses(session[153], p, loss)) {
            self.scenarios = Some(losses.map(|(ms, n)| (rank_for(ms), ms, n)));
            self.scenario_clock = Some((clock_ms, session[153], me[33]));
        }
        let rank = rank_for(loss);
        self.prediction = Some(rank);
        self.last_rejoin = Some((rank, me[33]));
        self.rejoin_clock = Some((clock_ms, session[153]));
    }
    fn rewind(&mut self, floor: u32, target: u32) {
        for event in self.events.drain(..).rev() {
            self.prior_events.push_front((self.epoch, event));
        }
        self.prior_events.truncate(16);
        let mut slow_laps = std::mem::take(&mut self.slow_laps);
        slow_laps.retain(|_, at| *at <= target);
        let mut field_losses = std::mem::take(&mut self.field_losses);
        field_losses.retain(|s| s.0 <= target);
        let mut trace = std::mem::take(&mut self.trace);
        Arc::make_mut(&mut trace).retain(|_, (frame, _)| *frame <= target);
        let mut kept: Vec<_> = self
            .stops
            .iter()
            .filter(|s| s.exit_frame.is_some_and(|exit| exit <= target))
            .cloned()
            .collect();
        let mut fp = std::mem::take(&mut self.practice);
        fp.rewind(target);
        self.rewind_limits.push((self.floor, target));
        let mut exit_timing = std::mem::take(&mut self.exit_timing);
        exit_timing.rewind(target);
        self.reset(floor);
        self.exit_timing = exit_timing;
        self.practice = fp;
        self.field_losses = field_losses;
        self.slow_laps = slow_laps;
        self.trace = trace;
        for stop in &mut kept {
            stop.epoch = self.epoch;
        }
        self.stops = kept;
    }
    fn reset(&mut self, floor: u32) {
        self.exit_timing = Default::default();
        self.minis = Default::default();
        self.practice = Default::default();
        self.slow_laps.clear();
        self.field_inside.clear();
        self.field_visits.clear();
        self.field_losses.clear();
        self.neutral_loss = Default::default();
        self.trace = Default::default();
        self.trends = Default::default();
        self.lap_battles = Default::default();
        self.loss_basis = None;
        self.visit = None;
        self.stop_history.append(&mut self.stops);
        self.previous_pit = None;
        self.previous_ms = None;
        self.player_slot = None;
        self.pending = None;
        self.prediction = None;
        self.last_rejoin = None;
        self.rejoin_clock = None;
        self.entry_equipment = Equipment::default();
        self.scenarios = None;
        self.scenario_clock = None;
        self.work_loss = Default::default();
        self.tyre_validation = Default::default();
        self.packets.clear();
        self.events.clear();
        self.button_frame = None;
        self.buttons_held = 0;
        self.pressed_actions.clear();
        self.floor = floor;
        self.lap_at = None;
        self.epoch += 1;
    }
    fn service_times(&self, safety: u8, profile: Profile) -> Option<[(u32, usize); 2]> {
        let [_, _, tyre_service, wing_service] = *self.work_loss.get(usize::from(safety))?;
        let normal = tyre_service.unwrap_or_else(|| (profile.routine_midpoint(), 0));
        let wing =
            wing_service.unwrap_or_else(|| (normal.0.saturating_add(profile.wing_allowance()), 0));
        Some([normal, wing])
    }
    fn service_losses(&self, safety: u8, profile: Profile, base: u32) -> Option<[(u32, usize); 2]> {
        let [tyres, wing, _, _] = *self.work_loss.get(usize::from(safety))?;
        let [tyre_service, wing_service] = self.service_times(safety, profile)?;
        let normal = tyres.unwrap_or((base, 0));
        let extra = wing_service.0.saturating_sub(tyre_service.0);
        Some([normal, wing.unwrap_or((normal.0.saturating_add(extra), 0))])
    }
    fn neutral_for(&self, safety: u8) -> Option<(u32, usize)> {
        safety
            .checked_sub(1)
            .and_then(|i| self.neutral_loss.get(usize::from(i)))
            .copied()
            .flatten()
    }
    pub(crate) fn render<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        d.set_item("lapBattles", self.lap_battles.each_ref().map(|b| b.result))?;
        d.set_item("gapTrends", self.trends.each_ref().map(|t| t.estimate()))?;
        d.set_item("boxNowPosition", self.prediction)?;
        d.set_item("lastRejoin", self.last_rejoin)?;
        let comparison = if let Some(idx) = self.pending {
            self.stops[idx].scenarios
        } else {
            self.scenario_clock
                .filter(|(at, safety, _)| {
                    self.previous_ms
                        .is_some_and(|now| now.saturating_sub(*at) <= 2000)
                        && self.packets.get(&(1, 0)).is_some_and(|p| p[153] == *safety)
                })
                .and(self.scenarios)
        };
        if let Some(group) = self
            .packets
            .get(&(1, 0))
            .and_then(|p| self.work_loss.get(p[153] as usize))
        {
            d.set_item("serviceAverages", [group[2], group[3]])?;
            if let Some(v) = self
                .packets
                .get(&(1, 0))
                .and_then(|p| self.tyre_validation.get(p[153] as usize))
            {
                d.set_item("tyreLossValidation", v.report())?;
            }
        }
        d.set_item("serviceForecast", comparison)?;
        if let Some((safety, profile)) = self
            .packets
            .get(&(1, 0))
            .and_then(|s| Profile::from_session(s).map(|profile| (s[153], profile)))
        {
            d.set_item(
                "serviceTimes",
                [
                    self.service_times(safety, profile),
                    self.service_times(0, profile),
                ],
            )?;
            if let Some((_, base, _)) = self.loss_basis {
                d.set_item("greenServiceLosses", self.service_losses(0, profile, base))?;
            }
        }
        let work = PyDict::new(py);
        for stop in &self.stops {
            let row = PyDict::new(py);
            row.set_item("safety", stop.safety)?;
            row.set_item("pitExperience", stop.profile.map(|p| p.experience))?;
            row.set_item("safetyChanged", stop.safety_changed)?;
            row.set_item("serviceDelayed", stop.service_delayed)?;
            let included = stop.service_delayed == Some(false);
            row.set_item(
                "serviceVerdict",
                stop.service_delayed
                    .map(|delayed| if delayed { "suspectedDelay" } else { "normal" }),
            )?;
            row.set_item("serviceSafety", stop.service_safety)?;
            if let Some(wet) = stop.wet {
                row.set_item("wet", wet)?;
            }
            row.set_item("serviceIncluded", included)?;
            row.set_item(
                "lossIncluded",
                included && !stop.safety_changed && stop.measured_loss_ms.is_some(),
            )?;
            row.set_item("measuredLossMs", stop.measured_loss_ms)?;
            row.set_item("transitReferences", stop.transit_references)?;
            row.set_item(
                "safetyStates",
                stop.safety_states
                    .iter()
                    .map(|v| u16::from(*v))
                    .collect::<Vec<_>>(),
            )?;
            row.set_item("entryScenarios", stop.scenarios)?;
            row.set_item("tyreChanged", stop.tyre_changed)?;
            row.set_item("damageIn", stop.damage_in.map(|d| d.map(u16::from)))?;
            row.set_item("damageOut", stop.damage_out.map(|d| d.map(u16::from)))?;
            if let Some((a, b)) = stop.damage_in.zip(stop.damage_out) {
                row.set_item(
                    "repairs",
                    PARTS
                        .iter()
                        .enumerate()
                        .filter(|(i, _)| b[*i] < a[*i])
                        .map(|(_, part)| *part)
                        .collect::<Vec<_>>(),
                )?;
            }
            work.set_item(stop.entry_ms, row)?;
        }
        d.set_item("pitWork", work)?;
        let service: Vec<_> = self
            .stops
            .iter()
            .map(|s| (s.entry_ms, s.service_ms, s.wing_repair, s.penalty))
            .collect();
        d.set_item("pitService", service)?;
        if let Some((_, ms, count)) = self.loss_basis {
            d.set_item("pitLossMs", ms)?;
            d.set_item("pitLossSamples", count)?;
            d.set_item("gamePitPriorMs", self.game_pit_prior)?;
        }
        let comparisons: Vec<_> = self
            .stops
            .iter()
            .map(|s| (s.lap, s.predicted, s.actual, s.entry_ms, s.exit_ms))
            .collect();
        d.set_item("pitComparisons", comparisons)?;
        let passages = PyDict::new(py);
        for exit in &self.exit_timing.exits {
            passages.set_item(
                exit.at,
                (
                    exit.rank,
                    exit.ahead,
                    exit.behind,
                    exit.front_ms,
                    exit.rear_ms,
                    exit.waiting,
                ),
            )?;
        }
        d.set_item("exitPassages", passages)?;
        d.set_item("accepted", self.accepted)?;
        d.set_item("rejected", self.rejected)?;
        d.set_item("error", &self.fault)?;
        d.set_item("uid", self.uid.map(|x| x.to_string()))?;
        d.set_item("epoch", self.epoch)?;
        d.set_item("format", self.format)?;
        let age = self.lap_at.map(|t| t.elapsed().as_millis() as u64);
        d.set_item("ageMs", age)?;
        let (Some(s), Some(l), Some(p)) = (
            self.packets.get(&(1, 0)),
            self.packets.get(&(2, 0)),
            self.packets.get(&(4, 0)),
        ) else {
            return Ok(d);
        };
        let modern = self.format == 2026;
        let slots = if modern { 24 } else { 22 };
        let lap_rows = &l[29..29 + slots * 57];
        d.set_item("timingFrame", u32_at(l, 19))?;
        d.set_item("timingBranch", self.floor)?;
        d.set_item("rewindLimits", &self.rewind_limits)?;
        let length = u16_at(s, 33);
        let comparable = comparable_laps(lap_rows, length);
        d.set_item("comparableLaps", comparable)?;
        if !comparable
            || lap_rows
                .as_chunks::<57>()
                .0
                .iter()
                .any(|r| r[45] == 2 && r[32] > 1 && split(r, 17) == 0)
        {
            if let Some(gaps) = forecast_gaps(lap_rows, length, comparable) {
                d.set_item("forecastGaps", gaps)?;
            }
        }
        if matches!(s[35], 1..=4) {
            d.set_item(
                "practiceLaps",
                self.practice.rows.values().map(|r| r.1).collect::<Vec<_>>(),
            )?;
        }
        d.set_item("weather", s[29])?;
        d.set_item("trackTemp", s[30] as i8)?;
        d.set_item("airTemp", s[31] as i8)?;
        let outlook: Vec<_> = s[156..]
            .as_chunks::<8>()
            .0
            .iter()
            .take(usize::from(s[155].min(64)))
            .filter(|f| f[0] == s[35] && f[2] <= 5 && f[7] <= 100)
            .map(|f| (f[1], f[2], f[7]))
            .collect();
        d.set_item("weatherOutlook", outlook)?;
        d.set_item("forecastApproximate", s[668] == 1)?;
        if s[682] > 0 && s[682] <= s[683] && s[683] <= s[32] {
            d.set_item("gamePitWindow", (s[682], s[683]))?;
            if (1..=p[29]).contains(&s[684]) {
                d.set_item("gameRejoin", s[684])?;
                d.set_item(
                    "freshGameRejoin",
                    u32_at(s, 23).abs_diff(u32_at(l, 23)) <= 240,
                )?;
            }
        }
        d.set_item("totalLaps", s[32])?;
        d.set_item("length", u16_at(s, 33))?;
        let sectors = [745, 749].map(|i| f32::from_bits(u32_at(s, i)));
        if 0.0 < sectors[0] && sectors[0] < sectors[1] && sectors[1] < f32::from(u16_at(s, 33)) {
            d.set_item("sectorStarts", sectors)?;
        }
        d.set_item("sessionType", s[35])?;
        d.set_item("seasonLink", u32_at(s, 670))?;
        d.set_item("weekendLink", u32_at(s, 674))?;
        d.set_item("timeLeft", u16_at(s, 38))?;
        d.set_item("track", s[36] as i8)?;
        d.set_item("safety", s[153])?;
        d.set_item("neutralPitLoss", self.neutral_for(s[153]))?;
        d.set_item("player", l[27])?;
        d.set_item("paused", s[43] != 0)?;
        d.set_item("spectating", s[44] != 0)?;
        let zones = marshal_zones(s);
        d.set_item("yellow", zones.iter().any(|(_, flag)| *flag == 3))?;
        d.set_item("marshalZones", zones)?;
        let mut rows = Vec::new();
        let minis = self.minis.colours();
        for i in 0..if modern { 24 } else { 22 } {
            let a = &l[29 + i * 57..];
            if a[32] == 0 || a[32] > p[29] || matches!(a[45], 0 | 1) {
                continue;
            }
            let h = &p[30 + i * if modern { 60 } else { 57 }..];
            let name = if modern { 10 } else { 7 };
            let name_bytes = &h[name..name + 32];
            let end = name_bytes.iter().position(|b| *b == 0).unwrap_or(32);
            let row = PyDict::new(py);
            row.set_item("slot", i)?;
            if let Some(m) = self.packets.get(&(0, 0)) {
                let off = 29 + i * if modern { 54 } else { 60 };
                let x = f32::from_bits(u32_at(m, off));
                let z = f32::from_bits(u32_at(m, off + 8));
                if x.is_finite() && z.is_finite() {
                    row.set_item("world", (x, z))?;
                }
            }
            row.set_item("name", String::from_utf8_lossy(&name_bytes[..end]).as_ref())?;
            row.set_item("number", h[name - 2])?;
            let age_visible =
                s[154] == 0 || h[0] == 1 || i == usize::from(l[27]) || h[name + 32] == 1;
            let colour = name + 38;
            if h[colour - 1] > 0 {
                row.set_item("rgb", &h[colour..colour + 3])?;
            }
            let slow: Vec<_> = self
                .slow_laps
                .range((i as u8, 0)..=(i as u8, u8::MAX))
                .map(|(k, _)| k.1)
                .collect();
            row.set_item("slowLaps", slow)?;
            row.set_item("tyreDataPublic", age_visible)?;
            if let Some(v) = self.field_visits.get(&i) {
                row.set_item(
                    "accruedPitLossMs",
                    v.measurement.delta(&l[29..29 + slots * 57], a),
                )?;
            }
            if let Some(split) = minis.get(i) {
                row.set_item("minis", split.as_slice())?;
                row.set_item("miniLastLap", self.minis.showing_last(i))?;
            }
            row.set_item("position", a[32])?;
            row.set_item("lap", a[33])?;
            row.set_item("pit", a[34] != 0)?;
            row.set_item("pitStops", a[35])?;
            row.set_item("grid", a[43])?;
            row.set_item("result", a[45])?;
            row.set_item("invalid", a[37] != 0)?;
            row.set_item("driverStatus", a[44])?;
            row.set_item("servePenalty", a[51] == 1)?;
            row.set_item("penalties", (a[38], a[41], a[42]))?;
            row.set_item("gapMs", split(a, 17))?;
            row.set_item("raceGapMs", race_gap(&l[29..29 + slots * 57], a))?;
            row.set_item("intervalMs", split(a, 14))?;
            row.set_item("intervalValid", u16_at(a, 14) < 60_000 && split(a, 14) > 0)?;
            row.set_item("lastMs", u32_at(a, 0))?;
            row.set_item("currentMs", u32_at(a, 4))?;
            row.set_item("splits", [split(a, 8), split(a, 11)])?;
            let metres = f32::from_bits(u32_at(a, 20));
            row.set_item("distance", metres.is_finite().then_some(metres))?;
            if let Some(t) = self.packets.get(&(6, 0)) {
                row.set_item("speed", u16_at(t, 29 + (if modern { 59 } else { 60 }) * i))?;
            }
            if let Some(t) = self.packets.get(&(7, 0)) {
                let off = 29 + i * if modern { 59 } else { 55 };
                if i == usize::from(l[27]) {
                    for (name, n) in [("fuelKg", 5), ("fuelCapacityKg", 9)] {
                        let value = f32::from_bits(u32_at(t, off + n));
                        if value.is_finite() && value > 0.0 {
                            row.set_item(name, value)?;
                        }
                    }
                }
                row.set_item("compound", t[off + 26])?;
                if age_visible {
                    row.set_item("age", t[off + 27])?;
                }
                row.set_item("flag", t[off + 28] as i8)?;
            }
            if let Some(t) = self.packets.get(&(11, i as u8)) {
                let history: Vec<_> = (0..usize::from(t[30]))
                    .map(|n| {
                        let b = &t[36 + 14 * n..];
                        (
                            u32_at(b, 0),
                            [split(b, 4), split(b, 7), split(b, 10)],
                            b[13],
                        )
                    })
                    .collect();
                let stints: Vec<_> = (0..usize::from(t[31]))
                    .map(|n| (t[1436 + 3 * n], t[1438 + 3 * n]))
                    .collect();
                row.set_item("history", history)?;
                row.set_item("stints", stints)?;
            }
            if age_visible {
                if let Some(t) = self.packets.get(&(10, 0)) {
                    let off = 29 + i * 46;
                    let wear = [0, 4, 8, 12].map(|n| f32::from_bits(u32_at(t, off + n)));
                    if wear.iter().all(|v| (0.0..=100.0).contains(v)) {
                        row.set_item("wheelWear", wear)?;
                    }
                }
                if let Some(t) = self.packets.get(&(12, i as u8)) {
                    let sets: Vec<_> = t[30..230]
                        .as_chunks::<10>()
                        .0
                        .iter()
                        .enumerate()
                        .filter(|(_, set)| matches!(set[1], 7 | 8 | 16..=18) && set[2] <= 100)
                        .map(|(index, set)| {
                            (
                                set[1],
                                set[2],
                                set[3] == 1,
                                if set[6] > 0 {
                                    set[5].min(set[6])
                                } else {
                                    set[5]
                                },
                                i16::from_le_bytes([set[7], set[8]]),
                                index == usize::from(t[230]),
                            )
                        })
                        .collect();
                    row.set_item("tyreSets", sets)?;
                }
            }
            rows.push(row);
        }
        d.set_item("cars", rows)?;
        d.set_item("events", self.events.iter().cloned().collect::<Vec<_>>())?;
        d.set_item(
            "eventLog",
            self.events
                .iter()
                .map(|event| (self.epoch, event))
                .chain(
                    self.prior_events
                        .iter()
                        .map(|(epoch, event)| (*epoch, event)),
                )
                .take(16)
                .collect::<Vec<_>>(),
        )?;
        Ok(d)
    }
}

#[pyclass]
pub struct UdpReceiver {
    record_status: Option<Arc<crate::recording::Status>>,
    feed: Arc<Mutex<Feed>>,
    stop: Arc<AtomicBool>,
    worker: Option<thread::JoinHandle<()>>,
    port: u16,
}
#[pymethods]
impl UdpReceiver {
    #[new]
    #[pyo3(signature=(host,port,record_dir=None,pit_loss=20000))]
    fn new(
        host: &str,
        port: u16,
        record_dir: Option<std::path::PathBuf>,
        pit_loss: u32,
    ) -> PyResult<Self> {
        if !(1..=120000).contains(&pit_loss) {
            return Err(pyo3::exceptions::PyValueError::new_err("invalid pit loss"));
        }
        let socket = UdpSocket::bind((host, port))?;
        let port = socket.local_addr()?.port();
        socket.set_read_timeout(Some(Duration::from_millis(150)))?;
        let history = record_dir
            .as_deref()
            .map(crate::recording::load_history)
            .transpose()?
            .unwrap_or_default();
        let feed = Arc::new(Mutex::new(Feed::seeded(history.clone())));
        let stop = Arc::new(AtomicBool::new(false));
        let state = Arc::clone(&feed);
        let quit = Arc::clone(&stop);
        let recorder = record_dir
            .map(|dir| Recorder::new(dir, pit_loss, history))
            .transpose()?;
        let record_status = recorder.as_ref().map(|r| r.status.clone());
        let worker = thread::Builder::new()
            .name("f1-udp".into())
            .spawn(move || {
                let clock = Instant::now();
                let mut b = [0; 65535];
                while !quit.load(Ordering::Relaxed) {
                    match socket.recv(&mut b) {
                        Ok(n) => {
                            let ms = clock.elapsed().as_millis() as u64;
                            state.lock().unwrap().ingest(&b[..n], ms, pit_loss);
                            if let Some(writer) = &recorder {
                                writer.submit(ms, &b[..n]);
                            }
                        }
                        Err(e)
                            if matches!(
                                e.kind(),
                                std::io::ErrorKind::WouldBlock
                                    | std::io::ErrorKind::TimedOut
                                    | std::io::ErrorKind::Interrupted
                            ) =>
                        {
                            continue
                        }
                        Err(e) => {
                            state.lock().unwrap().fault = Some(e.to_string());
                            break;
                        }
                    }
                }
            })?;
        Ok(Self {
            feed,
            stop,
            record_status,
            worker: Some(worker),
            port,
        })
    }
    #[getter]
    fn port(&self) -> u16 {
        self.port
    }
    fn drain_udp_actions(&self) -> Vec<u8> {
        self.feed
            .lock()
            .unwrap()
            .pressed_actions
            .drain(..)
            .collect()
    }
    fn analysis<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let snapshot = self.feed.lock().unwrap().clone();
        snapshot.analysis(py)
    }
    fn snapshot<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let snapshot = self.feed.lock().unwrap().clone();
        let d = snapshot.render(py)?;
        if let Some(status) = &self.record_status {
            if let Some((uid, id, start)) = status.active.lock().unwrap().as_ref() {
                if snapshot.uid == Some(*uid) && snapshot.lap_at.is_some() {
                    d.set_item("recordingId", id)?;
                    d.set_item("timingMs", snapshot.lap_packet_ms.saturating_sub(*start))?;
                }
            }
            d.set_item("recordDropped", status.dropped.load(Ordering::Relaxed))?;
            d.set_item("recordError", status.error.lock().unwrap().clone())?;
        }
        Ok(d)
    }
    fn close(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}
impl Drop for UdpReceiver {
    fn drop(&mut self) {
        self.close()
    }
}
