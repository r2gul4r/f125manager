use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
mod exit_timing;
mod forecast;
mod live;
mod mini_timing;
mod pace;
mod pit_calibration;
mod pit_loss;
mod pit_rules;
mod practice;
mod recording;
mod track_pits;

/// Return the format, packet ID, session UID and overall frame ID from the common EA header.
#[pyfunction]
fn read_header(packet: &[u8]) -> PyResult<(u16, u8, u64, u32)> {
    let header = packet
        .get(..29)
        .ok_or_else(|| PyValueError::new_err("truncated F1 header"))?;
    let format = u16::from_le_bytes([header[0], header[1]]);
    if !matches!(format, 2025 | 2026) {
        return Err(PyValueError::new_err("unsupported F1 packet format"));
    }
    let session = u64::from_le_bytes(header[7..15].try_into().unwrap());
    let overall_frame = u32::from_le_bytes(header[23..27].try_into().unwrap());
    Ok((format, header[6], session, overall_frame))
}

/// Rank a mock field and compute intervals in integer milliseconds, retaining the car's slot.
#[pyfunction]
fn timing_order(gaps_ms: Vec<u32>) -> Vec<(usize, u32)> {
    let mut slots: Vec<_> = gaps_ms.into_iter().enumerate().collect();
    slots.sort_by_key(|(_, gap)| *gap);
    let mut previous = 0;
    slots
        .into_iter()
        .map(|(slot, gap)| {
            let interval = gap - previous;
            previous = gap;
            (slot, interval)
        })
        .collect()
}

/// Positive delta means the following car closes on the leading car.
#[pyfunction]
fn closing_pace(gap_ms: u32, leading_lap: u32, following_lap: u32) -> Option<(i64, Option<u32>)> {
    if leading_lap == 0 || following_lap == 0 {
        return None;
    }
    let delta = i64::from(leading_lap) - i64::from(following_lap);
    Some((delta, laps_to_one_second(gap_ms, delta)))
}

fn laps_to_one_second(gap_ms: u32, delta: i64) -> Option<u32> {
    if gap_ms <= 1000 {
        Some(0)
    } else if delta > 0 {
        Some(u64::from(gap_ms - 1000).div_ceil(delta as u64) as u32)
    } else {
        None
    }
}

/// Scale the slope of the observed interval to one representative lap.
#[pyfunction]
fn battle_projection(gap_ms: u32, gain_per_10s: i32, lap_ms: u32) -> Option<(i64, Option<u32>)> {
    if gap_ms == 0 || !(30_000..=600_000).contains(&lap_ms) {
        return None;
    }
    let delta = (f64::from(gain_per_10s) * f64::from(lap_ms) / 10_000.).round() as i64;
    Some((delta, laps_to_one_second(gap_ms, delta)))
}

#[cfg(test)]
mod tests {
    use super::closing_pace;
    use super::timing_order;
    #[test]
    fn forecasts_one_second_entry_from_completed_laps() {
        assert_eq!(closing_pace(1200, 93400, 93350), Some((50, Some(4))));
        assert_eq!(closing_pace(1201, 93400, 93350), Some((50, Some(5))));
        assert_eq!(closing_pace(1200, 93350, 93400), Some((-50, None)));
        assert_eq!(closing_pace(1000, 93350, 93400), Some((-50, Some(0))));
        assert_eq!(closing_pace(800, 0, 93400), None);
    }
    #[test]
    fn ranks_by_gap_with_stable_ties() {
        assert_eq!(
            timing_order(vec![1200, 0, 1200]),
            vec![(1, 0), (0, 1200), (2, 0)]
        );
    }
}

#[pymodule]
fn f125_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add_function(wrap_pyfunction!(forecast::reference_pace, module)?)?;
    module.add_class::<live::UdpReceiver>()?;
    module.add_class::<recording::Replay>()?;
    module.add_function(wrap_pyfunction!(forecast::race_forecast, module)?)?;
    module.add_function(wrap_pyfunction!(read_header, module)?)?;
    module.add_function(wrap_pyfunction!(timing_order, module)?)?;
    module.add_function(wrap_pyfunction!(closing_pace, module)?)?;
    module.add_function(wrap_pyfunction!(battle_projection, module)?)?;
    Ok(())
}
