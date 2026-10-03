// Störmer-Verlet vs explicit Euler for the harmonic oscillator.
// Independent Rust implementation, used to cross-verify the Python numerics:
// two languages, two authors of the arithmetic, one required answer.
//
// Emits JSON on stdout. Every number printed is computed here.

fn verlet(q0: f64, p0: f64, h: f64, w: f64, n: usize) -> (f64, f64, f64, f64, f64) {
    let (mut q, mut p) = (q0, p0);
    let w2 = w * w;
    // shadow Hamiltonian coefficient, derived by SymPy: (w^2/2)(1 - w^2 h^2/4)
    let shadow_c = 0.5 * w2 * (1.0 - w2 * h * h / 4.0);
    let mut h_min = f64::INFINITY;
    let mut h_max = f64::NEG_INFINITY;
    let mut s_min = f64::INFINITY;
    let mut s_max = f64::NEG_INFINITY;
    for _ in 0..n {
        let ph = p - 0.5 * h * w2 * q;
        q += h * ph;
        p = ph - 0.5 * h * w2 * q;
        let e = 0.5 * p * p + 0.5 * w2 * q * q;
        let s = 0.5 * p * p + shadow_c * q * q;
        if e < h_min { h_min = e }
        if e > h_max { h_max = e }
        if s < s_min { s_min = s }
        if s > s_max { s_max = s }
    }
    let e_final = 0.5 * p * p + 0.5 * w2 * q * q;
    (h_min, h_max, s_min, s_max, e_final)
}

fn euler(q0: f64, p0: f64, h: f64, w: f64, n: usize) -> f64 {
    let (mut q, mut p) = (q0, p0);
    let w2 = w * w;
    for _ in 0..n {
        let qn = q + h * p;
        p -= h * w2 * q;
        q = qn;
    }
    0.5 * p * p + 0.5 * w2 * q * q
}

fn main() {
    let w = 1.0_f64;
    let n = 200_000_usize;
    let e0 = 0.5_f64; // q0=1, p0=0  =>  H = w^2/2

    println!("{{");
    println!("  \"language\": \"rust\",");
    println!("  \"omega\": {}, \"steps\": {}, \"H0\": {},", w, n, e0);
    println!("  \"runs\": [");

    let hs = [0.2_f64, 0.1, 0.05, 0.025];
    for (i, &h) in hs.iter().enumerate() {
        let (hmin, hmax, smin, smax, efin) = verlet(1.0, 0.0, h, w, n);
        let amp = (hmax - hmin) / e0;
        let shadow_drift = (smax - smin) / (0.5 * w * w * (1.0 - w * w * h * h / 4.0));
        let eu = euler(1.0, 0.0, h, w, n);
        println!("    {{");
        println!("      \"h\": {},", h);
        println!("      \"verlet_energy_amplitude_rel\": {:.17e},", amp);
        println!("      \"verlet_amplitude_over_h2\": {:.17e},", amp / (h * h));
        println!("      \"verlet_shadow_drift_rel\": {:.17e},", shadow_drift);
        println!("      \"verlet_energy_final\": {:.17e},", efin);
        println!("      \"euler_energy_final\": {:.17e},", eu);
        println!("      \"euler_finite\": {}", eu.is_finite());
        print!("    }}");
        if i + 1 < hs.len() { println!(","); } else { println!(); }
    }
    println!("  ]");
    println!("}}");
}
