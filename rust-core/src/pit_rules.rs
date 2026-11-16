use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, sync::LazyLock};

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
enum Series {
    F1,
    F1Equal,
    F2,
    F2Equal,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
pub(crate) struct Profile {
    series: Series,
    mode: u8,
    pub experience: u8,
}

#[derive(Deserialize)]
struct Tier {
    routine: [u32; 2],
    wing: u32,
}
#[derive(Deserialize)]
struct GameRules {
    profiles: BTreeMap<String, Vec<Tier>>,
    mistakes: BTreeMap<String, [u32; 2]>,
}

static RULES: LazyLock<GameRules> = LazyLock::new(|| {
    serde_json::from_str(include_str!("pit_rules.json")).expect("invalid embedded GVDB pit rules")
});

impl Profile {
    pub fn from_session(session: &[u8]) -> Option<Self> {
        let series = match (session.get(37)?, session.get(708)?) {
            (0 | 3 | 13, 0) => Series::F1,
            (0 | 3 | 13, 1) => Series::F1Equal,
            (2, 0) => Series::F2,
            (2, 1) => Series::F2Equal,
            _ => return None,
        };
        Some(Self {
            series,
            mode: session[694],
            experience: *session.get(724)?,
        })
    }
    fn tiers(self) -> &'static [Tier] {
        &RULES.profiles[match self.series {
            Series::F1 => "f1",
            Series::F1Equal => "f1_equal_performance",
            Series::F2 => "f2",
            Series::F2Equal => "f2_equal_performance",
        }]
    }
    pub fn wing_allowance(self) -> u32 {
        // The value is identical across training tiers within each installed profile.
        self.tiers()[0].wing
    }

    pub fn routine_midpoint(self) -> u32 {
        let tiers = self.tiers();
        let low = tiers.iter().map(|t| t.routine[0]).min().unwrap();
        let high = tiers.iter().map(|t| t.routine[1]).max().unwrap();
        low.midpoint(high)
    }
}

// Smallest wheel delay in the shipped database. This is a noise floor on the
// excess above observed service time, never a maximum normal service time.
pub(crate) fn minimum_delay_ms() -> u32 {
    RULES.mistakes.values().map(|range| range[0]).min().unwrap()
}
