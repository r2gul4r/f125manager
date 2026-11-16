//! Each published chunk is a complete checksummed zstd frame. Unpublished
//! temporary files are ignored; an open replay reads an immutable chunk prefix.
use crate::live::Feed;
use crate::pit_loss::{Condition, Damage, History, Observation, Scenarios, Work};
use crate::pit_rules::Profile;
use pyo3::{prelude::*, types::PyDict};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File},
    io::{self, Read, Write},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        mpsc::{self, Receiver, RecvTimeoutError, SyncSender},
        Arc, Mutex,
    },
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

const MAGIC: &[u8; 8] = b"F125RAW1";
const MAX_CHUNK: usize = 512 * 1024;
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Stop {
    #[serde(default)]
    pub profile: Option<Profile>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wet: Option<bool>,
    #[serde(default, skip_serializing_if = "is_green")]
    pub safety: u8,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub wing_repair: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub penalty: bool,
    #[serde(default, skip_serializing_if = "zero")]
    pub service_ms: u16,
    #[serde(default)]
    pub damage_in: Option<Damage>,
    #[serde(default)]
    pub damage_out: Option<Damage>,
    #[serde(default)]
    pub tyre_changed: Option<bool>,
    #[serde(default)]
    pub safety_changed: bool,
    #[serde(default)]
    pub safety_states: Vec<u8>,
    #[serde(default)]
    pub scenarios: Option<Scenarios>,
    #[serde(default)]
    pub measured_loss_ms: Option<u32>,
    #[serde(default)]
    pub transit_references: u8,
    #[serde(default)]
    pub service_delayed: Option<bool>,
    #[serde(default)]
    pub service_safety: Option<u8>,
    pub epoch: u64,
    pub lap: u8,
    pub predicted: Option<u8>,
    pub actual: Option<u8>,
    pub entry_ms: u64,
    pub exit_ms: Option<u64>,
    #[serde(skip)]
    pub exit_frame: Option<u32>,
}
impl Stop {
    pub fn observation(&self, format: u16, track: i8) -> Option<Observation> {
        let (before, after) = self.damage_in.zip(self.damage_out)?;
        if self.actual.is_none()
            || self.service_ms == 0
            || self.tyre_changed != Some(true)
            || self.penalty
            || self.safety > 2
            || track < 0
            || (2..6).any(|i| after[i] < before[i])
        {
            return None;
        }
        let condition = Condition {
            format,
            track,
            wet: self.wet,
            profile: self.profile?,
            safety: self.service_safety?,
            work: if self.wing_repair {
                Work::FrontWing
            } else {
                Work::Tyres
            },
        };
        Some(Observation {
            origin: None,
            condition,
            service: self.service_ms,
            loss: if self.safety_changed {
                None
            } else {
                self.measured_loss_ms
            },
        })
    }
}
fn zero(value: &u16) -> bool {
    *value == 0
}
fn is_green(value: &u8) -> bool {
    *value == 0
}
#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Manifest {
    version: u8,
    id: String,
    uid: String,
    format: u16,
    started_ms: u64,
    duration_ms: u64,
    track: Option<i8>,
    #[serde(default)]
    profile: Option<Profile>,
    session_type: Option<u8>,
    pit_loss_ms: u32,
    #[serde(default)]
    observation_seeds: Vec<Observation>,
    #[serde(default)]
    field_observations: Vec<Observation>,
    chunks: u32,
    packets: u64,
    stops: Vec<Stop>,
    epoch: u64,
}
#[derive(Default)]
pub(crate) struct Status {
    pub dropped: AtomicU64,
    pub error: Mutex<Option<String>>,
    pub active: Mutex<Option<(u64, String, u64)>>,
}
type Packet = (u64, Vec<u8>);
pub(crate) struct Recorder {
    tx: Option<SyncSender<Packet>>,
    worker: Option<thread::JoinHandle<()>>,
    pub status: Arc<Status>,
}
impl Recorder {
    pub fn new(root: PathBuf, pit_loss: u32, history: History) -> io::Result<Self> {
        let (tx, rx) = mpsc::sync_channel(4096);
        let status = Arc::new(Status::default());
        let stats = status.clone();
        let worker = thread::Builder::new()
            .name("f1-recorder".into())
            .spawn(move || {
                if let Err(e) = record(root, rx, pit_loss, history, &stats) {
                    *stats.error.lock().unwrap() = Some(e.to_string());
                }
            })?;
        Ok(Self {
            tx: Some(tx),
            worker: Some(worker),
            status,
        })
    }
    pub fn submit(&self, ms: u64, b: &[u8]) {
        if b.len() < 29
            || !matches!(u16::from_le_bytes([b[0], b[1]]), 2025 | 2026)
            || b[7..15] == [0; 8]
        {
            return;
        }
        if self
            .tx
            .as_ref()
            .unwrap()
            .try_send((ms, b.to_vec()))
            .is_err()
        {
            self.status.dropped.fetch_add(1, Ordering::Relaxed);
        }
    }
}
impl Drop for Recorder {
    fn drop(&mut self) {
        self.tx.take();
        if let Some(w) = self.worker.take() {
            let _ = w.join();
        }
    }
}
struct Session {
    uid: u64,
    dir: PathBuf,
    m: Manifest,
    feed: Feed,
    start: u64,
    last_flush: u64,
    buf: Vec<u8>,
}
impl Session {
    fn open(
        root: &Path,
        uid: u64,
        format: u16,
        start: u64,
        loss: u32,
        history: History,
    ) -> io::Result<Self> {
        fs::create_dir_all(root)?;
        let wall = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default();
        let mut n = wall.as_micros();
        let (id, dir) = loop {
            let id = format!("{n}-{uid:016x}");
            let dir = root.join(&id);
            match fs::create_dir(&dir) {
                Ok(()) => break (id, dir),
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => n += 1,
                Err(e) => return Err(e),
            }
        };
        Ok(Self {
            uid,
            dir,
            m: Manifest {
                version: 8,
                id,
                uid: uid.to_string(),
                format,
                started_ms: wall.as_millis() as u64,
                duration_ms: 0,
                track: None,
                profile: None,
                session_type: None,
                pit_loss_ms: loss,
                observation_seeds: vec![],
                field_observations: vec![],
                chunks: 0,
                packets: 0,
                stops: vec![],
                epoch: 1,
            },
            feed: Feed::seeded(history),
            start,
            last_flush: 0,
            buf: Vec::with_capacity(MAX_CHUNK),
        })
    }
    fn append(&mut self, at: u64, b: &[u8]) {
        let ms = at - self.start;
        self.buf.extend(ms.to_le_bytes());
        self.buf.extend((b.len() as u16).to_le_bytes());
        self.buf.extend(b);
        self.feed.ingest(b, ms, self.m.pit_loss_ms);
        if b[6] == 1 && b[5] == 1 && b.len() == if self.m.format == 2026 { 926 } else { 753 } {
            let track = b[36] as i8;
            let profile = Profile::from_session(b);
            if self.m.track != Some(track) || self.m.profile != profile {
                self.m.profile = profile;
                self.m.track = Some(track);
                self.m.observation_seeds = self
                    .feed
                    .history
                    .iter()
                    .copied()
                    .filter(|s| s.condition.format == self.m.format && s.condition.track == track)
                    .collect();
            }
            self.m.session_type = Some(b[35]);
        }
        self.m.packets += 1;
        self.m.duration_ms = ms;
    }
    fn flush(&mut self) -> io::Result<()> {
        if self.buf.is_empty() {
            return Ok(());
        }
        let tmp = self.dir.join("chunk.tmp");
        let mut zip = zstd::stream::Encoder::new(File::create(&tmp)?, 1)?;
        zip.include_checksum(true)?;
        zip.write_all(MAGIC)?;
        zip.write_all(&self.buf)?;
        zip.finish()?.sync_data()?;
        fs::rename(tmp, self.dir.join(format!("{:08}.zst", self.m.chunks)))?;
        self.m.chunks += 1;
        self.m.epoch = self.feed.epoch;
        self.m.field_observations = self.feed.field_losses.iter().map(|s| s.1).collect();
        self.m.stops.clone_from(&self.feed.stop_history);
        self.m.stops.extend_from_slice(&self.feed.stops);
        let tmp = self.dir.join("manifest.tmp");
        let mut file = File::create(&tmp)?;
        serde_json::to_writer(&mut file, &self.m)?;
        file.sync_data()?;
        drop(file);
        // The complete index can be published independently of the next raw chunk.
        self.buf.clear();
        self.last_flush = self.m.duration_ms;
        Ok(())
    }
}
// Windows readers can open the published index without FILE_SHARE_DELETE.
// Keep writing raw chunks and retry the latest complete index after the reader closes.
fn publish_indexes(pending: &mut Vec<PathBuf>, status: &Status) -> io::Result<()> {
    let mut locked = None;
    let mut i = 0;
    while i < pending.len() {
        let dir = &pending[i];
        match fs::rename(dir.join("manifest.tmp"), dir.join("manifest.json")) {
            Ok(()) => {
                pending.swap_remove(i);
            }
            Err(e) if cfg!(windows) && matches!(e.raw_os_error(), Some(5 | 32 | 33)) => {
                locked = Some(format!(
                    "Recording index pending for {}: {e}",
                    dir.display()
                ));
                i += 1;
            }
            Err(e) => {
                return Err(io::Error::new(
                    e.kind(),
                    format!("Publishing {}: {e}", dir.display()),
                ))
            }
        }
    }
    *status.error.lock().unwrap() = locked;
    Ok(())
}
fn checkpoint(
    session: &mut Session,
    pending: &mut Vec<PathBuf>,
    status: &Status,
) -> io::Result<()> {
    if !session.buf.is_empty() {
        session.flush()?;
        if !pending.contains(&session.dir) {
            pending.push(session.dir.clone());
        }
    }
    publish_indexes(pending, status)
}
fn record(
    root: PathBuf,
    rx: Receiver<Packet>,
    loss: u32,
    mut history: History,
    status: &Status,
) -> io::Result<()> {
    let mut pending = Vec::new();
    let mut active: Option<Session> = None;
    let mut previous = std::collections::VecDeque::new();
    loop {
        match rx.recv_timeout(Duration::from_millis(300)) {
            Ok((at, b)) => {
                let uid = u64::from_le_bytes(b[7..15].try_into().unwrap());
                if active.as_ref().is_none_or(|s| s.uid != uid) {
                    if previous.contains(&uid) {
                        continue;
                    }
                    if let Some(mut s) = active.take() {
                        checkpoint(&mut s, &mut pending, status)?;
                        s.feed
                            .archive_losses(s.m.started_ms.saturating_add(s.m.duration_ms));
                        history = s.feed.history;
                        previous.push_back(s.uid);
                        if previous.len() > 8 {
                            previous.pop_front();
                        }
                    }
                    active = Some(Session::open(
                        &root,
                        uid,
                        u16::from_le_bytes([b[0], b[1]]),
                        at,
                        loss,
                        history.clone(),
                    )?);
                    if let Some(s) = &active {
                        *status.active.lock().unwrap() = Some((uid, s.m.id.clone(), at));
                    }
                }
                let session = active.as_mut().unwrap();
                session.append(at, &b);
                if session.buf.len() >= MAX_CHUNK
                    || session.m.duration_ms - session.last_flush >= 1000
                {
                    checkpoint(session, &mut pending, status)?;
                }
            }
            Err(reason) => {
                if let Some(s) = active.as_mut() {
                    checkpoint(s, &mut pending, status)?;
                }
                if reason == RecvTimeoutError::Disconnected {
                    for _ in 0..20 {
                        if pending.is_empty() {
                            break;
                        }
                        thread::sleep(Duration::from_millis(50));
                        publish_indexes(&mut pending, status)?;
                    }
                    return Ok(());
                }
            }
        }
    }
}
// Read each real stop once, never the seed copied into later recordings.
// Older recordings saved the raw packets but did not index losses.
pub(crate) fn load_history(root: &Path) -> io::Result<History> {
    history_before(root, None)
}

fn history_before(root: &Path, cutoff: Option<u64>) -> io::Result<History> {
    let mut history = History::default();
    if !root.exists() {
        return Ok(history);
    }
    for entry in fs::read_dir(root)? {
        let dir = entry?.path();
        let Ok(mut replay) = Replay::new(dir) else {
            continue;
        };
        if cutoff.is_some_and(|at| replay.m.started_ms.saturating_add(replay.m.duration_ms) >= at) {
            continue;
        }
        let Some(track) = replay.m.track.filter(|t| *t >= 0) else {
            continue;
        };
        if !matches!(replay.m.session_type, Some(15..=17 | 19 | 20)) {
            continue;
        }
        let start = history.len();
        if replay.m.version < 8 {
            replay.feed.legacy_pit_prior = false;
            if replay.read_until(replay.m.duration_ms).is_ok() {
                Arc::make_mut(&mut history).extend(replay.feed.observations(track));
            }
        } else {
            let samples = Arc::make_mut(&mut history);
            samples.extend(
                replay
                    .m
                    .stops
                    .iter()
                    .filter(|s| s.epoch == replay.m.epoch)
                    .filter_map(|s| s.observation(replay.m.format, track)),
            );
            samples.extend(replay.m.field_observations);
        }
        if let Ok(uid) = replay.m.uid.parse::<u64>() {
            let end = replay.m.started_ms.saturating_add(replay.m.duration_ms);
            for sample in &mut Arc::make_mut(&mut history)[start..] {
                sample.origin = Some((uid, end));
            }
        }
    }
    Ok(history)
}

fn replay_feed(m: &Manifest) -> Feed {
    let mut feed = Feed::seeded(Arc::new(m.observation_seeds.clone()));
    feed.legacy_pit_prior = m.version < 8;
    feed.fixed_replay_loss = m.version == 1;
    feed
}
fn invalid(msg: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, msg)
}
struct ReplayCheckpoint {
    at: u64,
    chunk: u32,
    feed: Feed,
}

#[pyclass]
pub struct Replay {
    dir: PathBuf,
    m: Manifest,
    chunk: u32,
    bytes: Vec<u8>,
    cursor: usize,
    feed: Feed,
    last_ms: u64,
    checkpoints: Vec<ReplayCheckpoint>,
    interactive: bool,
}
#[pymethods]
impl Replay {
    #[new]
    fn new(dir: PathBuf) -> io::Result<Self> {
        let m: Manifest = serde_json::from_reader(File::open(dir.join("manifest.json"))?)?;
        if !matches!(m.version, 1..=8) || m.chunks == 0 || !(1..=120000).contains(&m.pit_loss_ms) {
            return Err(invalid("Unsupported recording manifest"));
        }
        Ok(Self {
            dir,
            feed: replay_feed(&m),
            m,
            chunk: 0,
            bytes: vec![],
            cursor: 0,
            last_ms: 0,
            checkpoints: Vec::new(),
            interactive: false,
        })
    }
    #[getter]
    fn duration_ms(&self) -> u64 {
        self.m.duration_ms
    }
    #[staticmethod]
    fn for_handoff(dir: PathBuf) -> io::Result<Self> {
        let mut replay = Self::new(dir)?;
        let root = replay
            .dir
            .parent()
            .ok_or_else(|| invalid("Missing recording root"))?;
        let prior = history_before(root, Some(replay.m.started_ms))?;
        // Preserve seeds from archives that may have been moved. Match each
        // observation at most once, prioritizing already measured total losses.
        let mut unmatched = prior.as_ref().clone();
        let seeds = &mut replay.m.observation_seeds;
        seeds.sort_by_key(|s| s.loss.is_none());
        for seed in seeds.iter_mut() {
            if let Some(index) = unmatched.iter().position(|s| {
                (s.condition == seed.condition
                    || (seed.condition.wet.is_none()
                        && Condition {
                            wet: None,
                            ..s.condition
                        } == seed.condition))
                    && s.service == seed.service
                    && (seed.loss.is_none() || seed.loss == s.loss)
            }) {
                *seed = unmatched.swap_remove(index);
            }
        }
        seeds.extend(unmatched);
        replay.feed = replay_feed(&replay.m);
        replay.feed.legacy_pit_prior = false;
        Ok(replay)
    }
    #[getter]
    fn pit_loss_ms(&self) -> u32 {
        self.m.pit_loss_ms
    }
    fn analysis<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        py.allow_threads(|| self.read_until(self.m.duration_ms))?;
        self.feed.analysis(py)
    }
    fn advance<'py>(&mut self, py: Python<'py>, ms: u64) -> PyResult<Bound<'py, PyDict>> {
        self.interactive = true;
        py.allow_threads(|| self.read_until(ms))?;
        let d = self.feed.render(py)?;
        // The reducer freezes this rank on entry from its preceding on-track
        // samples. Keep these physical visits independent of the historical index.
        d.set_item("replayedVisits", d.get_item("pitComparisons")?.unwrap())?;
        // Publish only outcomes known by this instant on this branch, using
        // the prediction frozen by the recording version of the model.
        let stops: Vec<_> = self
            .m
            .stops
            .iter()
            .filter(|s| {
                s.entry_ms <= ms
                    && (s.epoch == self.feed.epoch
                        || (s.epoch < self.feed.epoch
                            && self
                                .feed
                                .stops
                                .iter()
                                .any(|kept| kept.entry_ms == s.entry_ms)))
            })
            .map(|s| {
                let exit = s.exit_ms.filter(|at| *at <= ms);
                (s.lap, s.predicted, exit.and(s.actual), s.entry_ms, exit)
            })
            .collect();
        let recorded = PyDict::new(py);
        for s in &self.m.stops {
            if s.entry_ms <= ms && stops.iter().any(|visit| visit.3 == s.entry_ms) {
                if let Some(pair) = s.scenarios {
                    recorded.set_item(s.entry_ms, pair)?;
                }
            }
        }
        d.set_item("recordedScenarios", recorded)?;
        let mut seen = std::collections::BTreeSet::new();
        d.set_item(
            "pitComparisons",
            stops
                .into_iter()
                .filter(|s| seen.insert(s.3))
                .collect::<Vec<_>>(),
        )?;
        Ok(d)
    }
}
impl Replay {
    fn read_until(&mut self, ms: u64) -> io::Result<()> {
        let checkpoint = self.checkpoints.iter().rev().find(|point| point.at <= ms);
        if ms < self.last_ms || checkpoint.is_some_and(|point| point.at > self.last_ms) {
            if let Some(point) = checkpoint {
                self.chunk = point.chunk;
                self.feed = point.feed.clone();
            } else {
                self.chunk = 0;
                self.feed = replay_feed(&self.m);
            }
            self.cursor = 0;
            self.bytes.clear();
        }
        loop {
            if self.cursor == self.bytes.len() {
                if self.chunk == self.m.chunks {
                    break;
                }
                let path = self.dir.join(format!("{:08}.zst", self.chunk));
                let limit = MAX_CHUNK + 65535 + 32;
                self.bytes.clear();
                zstd::stream::Decoder::new(File::open(path)?)?
                    .take(limit as u64 + 1)
                    .read_to_end(&mut self.bytes)?;
                if !self.bytes.starts_with(MAGIC) || self.bytes.len() > limit {
                    return Err(invalid("Invalid replay chunk"));
                }
                self.chunk += 1;
                self.cursor = MAGIC.len();
            }
            let header = self
                .bytes
                .get(self.cursor..self.cursor + 10)
                .ok_or_else(|| invalid("Truncated record"))?;
            let at = u64::from_le_bytes(header[..8].try_into().unwrap());
            // Save the state immediately before the first record of this chunk.
            // Up to sixteen points per open recording, including on a long first seek.
            let chunk = self.chunk - 1;
            if self.interactive
                && self.cursor == MAGIC.len()
                && chunk > 0
                && chunk.is_multiple_of(self.m.chunks.div_ceil(16))
                && self
                    .checkpoints
                    .last()
                    .is_none_or(|point| chunk > point.chunk)
            {
                self.checkpoints.push(ReplayCheckpoint {
                    at,
                    chunk,
                    feed: self.feed.clone(),
                });
            }
            if at > ms {
                break;
            }
            let n = u16::from_le_bytes([header[8], header[9]]) as usize;
            let start = self.cursor + 10;
            let b = self
                .bytes
                .get(start..start + n)
                .ok_or_else(|| invalid("Truncated datagram"))?;
            self.feed.ingest(b, at, self.m.pit_loss_ms);
            self.cursor = start + n;
        }
        self.last_ms = ms;
        Ok(())
    }
}
