//! The mesh layout's settling for yanartas-pillowbox, in Rust: called from Python (a PyO3
//! extension, on all cores) and in the browser (WebAssembly). The algorithm follows
//! `sfc._settle` and `sfc._match`; see ARCHITECTURE.md.

pub mod arcs;
pub mod closed;
pub mod curve;
pub mod density;
pub mod geom;
pub mod graph;
pub mod grid;
pub mod lanes;
pub(crate) mod par;
pub mod poly;
pub mod segs;
pub mod settle;
pub mod traces;
pub mod zones;

pub use settle::{settle, Input, Params, Status};

use std::sync::atomic::{AtomicBool, Ordering};

static CANCEL: AtomicBool = AtomicBool::new(false);

/// Stop the layout under way (settling, the curve's relaxation, its graph) at its next
/// step: what it has so far is returned, and the caller's progress callback, which asked
/// for it, reports why (`cancel(false)` before the next layout).
pub fn cancel(on: bool) {
    CANCEL.store(on, Ordering::Relaxed);
}

/// Whether the layout under way is to stop.
pub fn cancelled() -> bool {
    CANCEL.load(Ordering::Relaxed)
}
