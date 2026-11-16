"""Read-only F1 practice save snapshots, kept locally alongside the UDP recordings."""

import hashlib
import json
import logging
import os
import sqlite3
from collections import deque
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from time import time_ns

LOG = logging.getLogger(__name__)
SCHEMA = """
CREATE TABLE IF NOT EXISTS blobs(hash TEXT PRIMARY KEY, data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS observations(
    id INTEGER PRIMARY KEY, uid TEXT NOT NULL, wall_ns INTEGER NOT NULL,
    kind TEXT NOT NULL, file TEXT, modified_ns INTEGER, hash TEXT, context TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS session_observations ON observations(uid,id);
CREATE TABLE IF NOT EXISTS sessions(uid TEXT PRIMARY KEY, updated_ns INTEGER, epoch INTEGER, laps TEXT);
"""


def steam_userdata() -> Path:
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"
            ) as key:
                return Path(winreg.QueryValueEx(key, "SteamPath")[0]) / "userdata"
        except OSError:
            pass  # Steam also supports its default machine-wide installation.
    return (
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Steam/userdata"
    )


@dataclass(frozen=True)
class SaveVersion:
    signature: tuple[int, int, int]
    digest: str
    data: bytes
    sampled_ns: int


def signature(stat):
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def save_versions(directories, previous, now):
    current = {}
    for directory in directories:
        for path in directory.iterdir():
            name = path.name.lower()
            if (
                not name.startswith(("savegame@midsession", "savegame@profile#"))
                or not path.is_file()
            ):
                continue
            stamp = signature(path.stat())
            if path in previous and previous[path].signature == stamp:
                current[path] = previous[path]
                continue
            data = path.read_bytes()
            if signature(path.stat()) != stamp or len(data) != stamp[0]:
                raise OSError(f"Save changed during read: {path.name}")
            current[path] = SaveVersion(
                stamp, hashlib.sha256(data).hexdigest(), data, now
            )
    return current


def practice_context(raw):
    if (
        raw.get("handoff")
        or raw.get("spectating")
        or not raw.get("uid")
        or raw.get("sessionType") not in (1, 2, 3, 4)
    ):
        return None, ()
    car = next((c for c in raw.get("cars", ()) if c["slot"] == raw.get("player")), {})
    context = {
        k: raw.get(k)
        for k in (
            "uid",
            "epoch",
            "sessionType",
            "seasonLink",
            "weekendLink",
            "track",
            "format",
            "timeLeft",
            "ageMs",
            "paused",
        )
    }
    context.update(
        {k: car.get(k) for k in ("lap", "currentMs", "compound", "pit", "driverStatus")}
    )
    return context, car.get("history", ())


class PracticeSaves:
    def __init__(self, root: Path, directory=None):
        self.path = root.resolve() / "practice-saves" / "captures.sqlite3"
        self.directory = Path(directory) if directory else None
        self.userdata = steam_userdata()
        self.previous: dict[Path, SaveVersion] = {}
        self.context = None
        self.marker = None
        self.history = None
        self.tail_until = 0
        self.tail_context = None
        self.recent: deque[tuple[str, Path, SaveVersion | None, int]] = deque(maxlen=24)
        self.schema_ready = False
        self.status = {"state": "Starting", "files": 0, "error": None}

    def directories(self):
        if self.directory is not None:
            return [self.directory] if self.directory.is_dir() else []
        return sorted(self.userdata.glob("*/3059520/remote"))

    def tick(self, raw):
        now = time_ns()
        directories = self.directories()
        current = (
            save_versions(directories, self.previous, now)
            if directories
            else self.previous
        )
        ctx, history = practice_context(raw)
        # No session-end packet is guaranteed when the game exits. Resume naturally
        # on fresh UDP, without treating unrelated later saves as practice changes.
        if ctx and (ctx["ageMs"] or 0) > 120_000:
            ctx, history = None, ()
        starting = ctx is not None and (
            not self.context or self.context["uid"] != ctx["uid"]
        )
        ending = self.context is not None and (not ctx or starting)
        if ending:
            self.tail_context = self.context
            self.tail_until = now + 30_000_000_000
        tail = self.tail_context if not ctx and now <= self.tail_until else None
        owner = ctx or tail
        changes = []
        while self.recent and now - self.recent[0][3] > 60_000_000_000:
            self.recent.popleft()
        if not owner:
            for path, old in self.previous.items():
                new = current.get(path)
                if not new or new.digest != old.digest:
                    self.recent.append(("before-fp", path, old, now))
                    self.recent.append(("before-fp-change", path, new, now))
        if owner:
            # A pre-FP baseline was sampled while armed. Give it its original clock,
            # never an invented lap. The first in-FP copy anchors the correlation.
            if starting:
                changes.extend(self.recent)
                for path, version in self.previous.items():
                    changes.append(
                        ("armed-baseline", path, version, version.sampled_ns)
                    )
            for path in current.keys() | self.previous.keys():
                old, new = self.previous.get(path), current.get(path)
                if new is None or starting or old is None or new.digest != old.digest:
                    kind = (
                        "removed"
                        if new is None
                        else "fp-baseline"
                        if starting
                        else "changed"
                    )
                    changes.append((kind, path, new, now))
        marker = (
            tuple(
                ctx.get(k)
                for k in ("uid", "epoch", "lap", "compound", "pit", "driverStatus")
            )
            if ctx
            else None
        )
        timed = tuple(
            (i, row[0], bool(row[2] & 1)) for i, row in enumerate(history, 1) if row[0]
        )
        if (
            changes
            or ending
            or marker != self.marker
            or (ctx and timed != self.history)
        ):
            self.write(ctx, ending, owner, changes, marker, timed, now)
        if starting:
            self.recent.clear()
        self.previous, self.context, self.marker, self.history = (
            current,
            ctx,
            marker,
            timed,
        )
        self.status = {
            "state": "Recording" if ctx else "Finishing" if tail else "Armed",
            "files": len(current) if directories else 0,
            "session": owner["uid"] if owner else None,
            "error": None
            if directories and current
            else "No F1 mid-session or profile save files found",
        }

    def write(self, ctx, ending, owner, changes, marker, timed, now):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            if not self.schema_ready:
                db.executescript(SCHEMA)
                self.schema_ready = True

            def event(context, kind, stamp, name=None, modified=None, digest=None):
                db.execute(
                    "INSERT INTO observations(uid,wall_ns,kind,file,modified_ns,hash,context) VALUES(?,?,?,?,?,?,?)",
                    (
                        str(context["uid"]),
                        stamp,
                        kind,
                        name,
                        modified,
                        digest,
                        json.dumps(context),
                    ),
                )

            if ending:
                event(self.context, "session-left", now)
            if ctx and marker != self.marker:
                event(ctx, "telemetry", now)
            for kind, path, version, stamp in changes:
                digest = version.digest if version else None
                if version:
                    db.execute(
                        "INSERT OR IGNORE INTO blobs VALUES(?,?)",
                        (digest, version.data),
                    )
                account = (
                    path.parent.parent.parent.name
                    if not self.directory
                    else "configured"
                )
                context = (
                    {"uid": owner["uid"]}
                    if kind.startswith(("armed-", "before-"))
                    else owner
                )
                event(
                    context,
                    kind if ctx else "after-fp-" + kind,
                    stamp,
                    account + "/" + path.name,
                    version.signature[1] if version else None,
                    digest,
                )
            if ctx:
                old = db.execute(
                    "SELECT epoch,laps FROM sessions WHERE uid=?", (str(ctx["uid"]),)
                ).fetchone()
                laps = json.loads(old[1]) if old else {}
                if old and old[0] != ctx["epoch"]:
                    laps = {k: v for k, v in laps.items() if int(k) < (ctx["lap"] or 1)}
                laps.update(
                    {str(n): {"ms": ms, "valid": valid} for n, ms, valid in timed}
                )
                db.execute(
                    "INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)",
                    (str(ctx["uid"]), now, ctx["epoch"], json.dumps(laps)),
                )

    def run(self, receiver, stop: Event):
        while not stop.is_set():
            try:
                self.tick(receiver.snapshot() if receiver else {})
            except (OSError, sqlite3.Error, ValueError) as exc:
                if self.status.get("error") != str(exc):
                    LOG.warning("Practice save capture: %s", exc)
                self.status = {**self.status, "state": "Retrying", "error": str(exc)}
            stop.wait(0.5)

    def report(self):
        result = {"watcher": self.status, "sessions": []}
        if not self.path.is_file():
            return result
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
            for uid, laps in db.execute(
                "SELECT uid,laps FROM sessions ORDER BY updated_ns DESC"
            ):
                history = json.loads(laps)
                changes = db.execute(
                    "SELECT COUNT(*) FROM observations WHERE uid=? AND kind IN ('changed','after-fp-changed','removed','after-fp-removed')",
                    (uid,),
                ).fetchone()[0]
                marker = db.execute(
                    "SELECT context FROM observations WHERE uid=? AND kind='telemetry' ORDER BY id DESC LIMIT 1",
                    (uid,),
                ).fetchone()
                latest = json.loads(marker[0]) if marker else {}
                result["sessions"].append(
                    {
                        "uid": uid,
                        "sessionType": latest.get("sessionType"),
                        "track": latest.get("track"),
                        "changedFilesObserved": changes,
                        "completedLaps": len(history),
                        "laps": history,
                        "classification": "programme-unverified",
                        "programmeCounts": None,
                        "unclassifiedLaps": len(history),
                    }
                )
        return result
