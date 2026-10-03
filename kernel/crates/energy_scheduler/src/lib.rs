//! Cyber-Physical Thermodynamic RAPL Smoother and Mechanical Kill-Switch.
//!
//! Enforces the Lean 4 `cpu_energy_bounded` invariant at the OS scheduler level:
//! - 5-sample trimmed-mean smoother filters non-deterministic CPU power interrupts.
//! - Mechanical kill-switch preempts rogue agents exceeding E_barrier = 10^6 µJ.

#![no_std]

/// Energy threshold barrier in micro-Joules (10^6 µJ).
pub const ENERGY_BARRIER_UJ: u64 = 1_000_000;

/// Fixed-size 5-sample ring buffer for computing trimmed-mean energy without allocations.
#[derive(Debug, Clone, Copy)]
pub struct TrimmedMeanFilter5 {
    samples: [u64; 5],
    index: usize,
    count: usize,
}

impl Default for TrimmedMeanFilter5 {
    fn default() -> Self {
        Self::new()
    }
}

impl TrimmedMeanFilter5 {
    /// Creates an empty 5-sample filter.
    pub const fn new() -> Self {
        Self {
            samples: [0; 5],
            index: 0,
            count: 0,
        }
    }

    /// Records a new hardware energy register sample (e.g. from Intel RAPL MSR).
    pub fn push(&mut self, sample_uj: u64) {
        self.samples[self.index] = sample_uj;
        self.index = (self.index + 1) % 5;
        if self.count < 5 {
            self.count += 1;
        }
    }

    /// Calculates the 5-sample trimmed-mean (discarding minimum and maximum).
    /// If fewer than 5 samples are available, returns the arithmetic mean.
    pub fn smoothed_energy(&self) -> u64 {
        if self.count == 0 {
            return 0;
        }
        if self.count < 5 {
            let mut sum: u64 = 0;
            let mut i = 0;
            while i < self.count {
                sum = sum.saturating_add(self.samples[i]);
                i += 1;
            }
            return sum / (self.count as u64);
        }

        // 5 samples: find min and max
        let mut min_val = self.samples[0];
        let mut max_val = self.samples[0];
        let mut sum: u64 = 0;

        let mut i = 0;
        while i < 5 {
            let s = self.samples[i];
            if s < min_val {
                min_val = s;
            }
            if s > max_val {
                max_val = s;
            }
            sum = sum.saturating_add(s);
            i += 1;
        }

        // Subtract min and max to retain middle 3 samples
        let trimmed_sum = sum.saturating_sub(min_val).saturating_sub(max_val);
        trimmed_sum / 3
    }
}

/// Evaluates process thermodynamic state against the physical barrier.
pub struct MechanicalKillSwitch;

impl MechanicalKillSwitch {
    /// Returns true if the smoothed energy consumption violates the deployment envelope.
    pub fn should_kill(filter: &TrimmedMeanFilter5) -> bool {
        filter.smoothed_energy() > ENERGY_BARRIER_UJ
    }
}

/// PCIe Function Level Reset (FLR) Guillotine (RunuX v13.0)
///
/// Hardware defense against MXU "Power Virus" di/dt thermal attacks.
pub struct PcieFlrGuillotine {
    /// Simulated I2C/SMBus control register for triggering FLR.
    flr_register: u64,
}

impl PcieFlrGuillotine {
    /// Initializes a new FLR Guillotine defense module.
    pub const fn new(flr_register: u64) -> Self {
        Self { flr_register }
    }

    /// Evaluates RAPL telemetry for di/dt attacks.
    ///
    /// # Arguments
    /// * `delta_t` - Thermal gradient ($\Delta T / \Delta t$) in milli-degrees Celsius per second.
    /// * `current_spike_ma` - Current spike amplitude in milliamperes.
    pub fn evaluate_and_trigger(&self, delta_t: i32, current_spike_ma: u32) -> Result<(), &'static str> {
        // Thresholds for power virus detection
        if delta_t > 50_000 || current_spike_ma > 100_000 {
            // Trigger PCIe FLR (mock hardware trigger)
            // SAFETY: In physical deployment this writes to the PCIe config space.
            unsafe {
                core::ptr::write_volatile(self.flr_register as *mut u32, 1);
            }
            return Err("HARDWARE_FLR_TRIGGERED");
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transient_spike_rejection() {
        let mut filter = TrimmedMeanFilter5::new();
        // 4 normal samples and 1 massive transient power spike
        filter.push(100);
        filter.push(120);
        filter.push(110);
        filter.push(5_000_000); // Transient spike: 5x barrier!
        filter.push(105);

        let smoothed = filter.smoothed_energy();
        // Middle three are 105, 110, 120 -> mean is 111
        assert_eq!(smoothed, 111);
        assert!(!MechanicalKillSwitch::should_kill(&filter));
    }

    #[test]
    fn test_sustained_burn_triggers_kill() {
        let mut filter = TrimmedMeanFilter5::new();
        // 5 sustained high-energy samples
        filter.push(1_200_000);
        filter.push(1_300_000);
        filter.push(1_400_000);
        filter.push(1_500_000);
        filter.push(1_600_000);

        let smoothed = filter.smoothed_energy();
        assert!(smoothed > ENERGY_BARRIER_UJ);
        assert!(MechanicalKillSwitch::should_kill(&filter));
    }

    #[test]
    fn test_pcie_flr_guillotine() {
        let mut dummy_reg = 0u32;
        let guillotine = PcieFlrGuillotine::new(&mut dummy_reg as *mut u32 as u64);
        
        // Normal state
        assert!(guillotine.evaluate_and_trigger(1000, 5000).is_ok());
        
        // Thermal attack
        assert!(guillotine.evaluate_and_trigger(60_000, 5000).is_err());
        assert_eq!(dummy_reg, 1); // FLR triggered
        
        dummy_reg = 0;
        
        // Current spike attack
        assert!(guillotine.evaluate_and_trigger(1000, 150_000).is_err());
        assert_eq!(dummy_reg, 1); // FLR triggered
    }
}
