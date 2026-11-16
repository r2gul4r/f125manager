use crate::pit_rules::Profile;
use serde::Deserialize;
use std::{collections::BTreeMap, sync::LazyLock};

#[derive(Deserialize)]
struct Circuit {
    limiter_metres: u32,
    series: BTreeMap<String, Reference>,
}
#[derive(Deserialize)]
struct Reference {
    kmh: u32,
    dry: u32,
    wet: u32,
    bypass: u32,
}
#[derive(Deserialize)]
struct Catalogue {
    tracks: BTreeMap<i8, Circuit>,
}
static DB: LazyLock<Catalogue> = LazyLock::new(|| {
    serde_json::from_str(include_str!("track_pits.json")).expect("invalid circuit pit reference")
});

pub(crate) fn estimate(session: &[u8], format: u16) -> Option<u32> {
    let profile = Profile::from_session(session)?;
    let circuit = DB.tracks.get(&(session[36] as i8))?;
    let series = match session[37] {
        0 | 3 | 13 => "f1",
        2 => "f2",
        _ => return None,
    };
    let reference = circuit.series.get(&format!("{series}_{format}"))?;
    let speed = match session[42] {
        0 => reference.kmh,
        v @ 30..=120 => u32::from(v),
        _ => return None,
    };
    let weather_delta = match session[29] {
        0..=2 => 0,
        3..=5 => i64::from(reference.wet) - i64::from(reference.dry),
        _ => return None,
    };
    let travel = (circuit.limiter_metres * 3600 + speed / 2) / speed;
    let loss = i64::from(travel) + i64::from(profile.routine_midpoint()) + weather_delta
        - i64::from(reference.bypass);
    (1..=120000).contains(&loss).then_some(loss as u32)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn first_visit_uses_the_layout_limit_and_weather() {
        let mut session = [0; 926];
        session[36] = 3;
        session[42] = 80;
        let dry = estimate(&session, 2026).unwrap();
        session[29] = 4;
        assert_eq!(estimate(&session, 2026), Some(dry + 5000));
        session[29] = 0;
        session[42] = 60;
        assert!(estimate(&session, 2026).unwrap() > dry);
        session[42] = 0;
        assert_eq!(estimate(&session, 2026), Some(dry));
        session[36] = 39;
        let reverse = estimate(&session, 2026);
        session[36] = 7;
        assert_ne!(estimate(&session, 2026), reverse);
        session[36] = 255;
        assert_eq!(estimate(&session, 2026), None);
    }
}
