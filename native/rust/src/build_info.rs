//! Build information for the native extension.

/// Project name
pub const PROJECT_NAME: &str = env!("CARGO_PKG_NAME");

/// Version string from Cargo.toml
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Native ABI version (semantic versioning)
pub const NATIVE_ABI: &str = "1.0";

/// Bridge type used to expose the native module
pub const BRIDGE: &str = "PyO3";

/// Returns a formatted build info string.
pub fn build_info() -> String {
    format!(
        "{} native ABI {} via {} (version {})",
        PROJECT_NAME, NATIVE_ABI, BRIDGE, VERSION
    )
}
