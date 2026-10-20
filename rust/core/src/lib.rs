//! The mesh layout's settling for yanartas-pillowbox, in Rust: called from Python (a PyO3
//! extension, on all cores) and in the browser (WebAssembly). The algorithm follows
//! `sfc._settle` and `sfc._match`; see ARCHITECTURE.md.

pub mod geom;
pub mod grid;
mod par;
pub mod settle;
pub mod traces;
pub mod zones;

pub use settle::{settle, Input, Params, Status};
