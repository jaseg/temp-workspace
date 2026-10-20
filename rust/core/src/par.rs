//! Per-item work, on all cores with the `parallel` feature (rayon), else in turn (wasm).

#[cfg(feature = "parallel")]
use rayon::prelude::*;

/// `f` of each of `0..n`, in order.
pub fn pmap<T: Send, F: Fn(usize) -> T + Sync + Send>(n: usize, f: F) -> Vec<T> {
    #[cfg(feature = "parallel")]
    {
        (0..n).into_par_iter().map(f).collect()
    }
    #[cfg(not(feature = "parallel"))]
    {
        (0..n).map(f).collect()
    }
}
