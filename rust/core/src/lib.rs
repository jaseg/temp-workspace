//! The mesh layout's settling for yanartas-pillowbox, in Rust: called from Python (a PyO3
//! extension, on all cores) and in the browser (WebAssembly). The algorithm follows
//! `sfc._settle` and `sfc._match`; see ARCHITECTURE.md.

pub mod arcs;
pub mod closed;
pub mod curve;
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
