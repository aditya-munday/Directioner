//! Directioner native real-time audio bridge
//!
//! This crate provides native functionality for the Directioner project,
//! including shared memory and Discord integration.
//!
//! Note: Voice functionality is disabled in this build.

pub mod build_info;
pub mod discord;
pub mod shared_memory;

use pyo3::prelude::*;

/// Returns build information about the native extension.
#[pyfunction]
fn native_build_info() -> String {
    build_info::build_info()
}

/// Starts the audio runtime with the specified shared memory namespace and thread count.
/// This is a no-op in text-only mode.
#[pyfunction]
fn start_audio_runtime(_shared_memory_namespace: &str, _worker_threads: usize) {}

/// Stops the audio runtime.
/// This is a no-op in text-only mode.
#[pyfunction]
fn stop_audio_runtime() {}

/// DPP smoke test function exposed to Python.
#[pyfunction]
fn dpp_construct_smoke(config: &discord::DiscordBotConfig) -> String {
    discord::DppDiscordRuntime::construct_smoke_static(config)
}

/// Python module definition
#[pymodule]
#[pyo3(name = "directioner_native")]
pub fn directioner_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Build info
    m.add_function(pyo3::wrap_pyfunction!(native_build_info, m)?)?;

    // Runtime functions
    m.add_function(pyo3::wrap_pyfunction!(start_audio_runtime, m)?)?;
    m.add_function(pyo3::wrap_pyfunction!(stop_audio_runtime, m)?)?;

    // Shared memory types
    m.add_class::<shared_memory::PySharedMemoryRegion>()?;
    m.add_function(pyo3::wrap_pyfunction!(shared_memory::required_ring_bytes, m)?)?;

    // Discord types
    m.add_class::<discord::DiscordBotConfig>()?;
    m.add_class::<discord::DiscordTextEvent>()?;
    m.add_class::<discord::VoiceGatewayStats>()?;
    m.add_class::<discord::DiscordEmbed>()?;
    m.add_class::<discord::DiscordAttachment>()?;
    m.add_class::<discord::DiscordVoiceFrame>()?;
    m.add_class::<discord::DppDiscordRuntime>()?;

    // DPP smoke test
    m.add_function(pyo3::wrap_pyfunction!(dpp_construct_smoke, m)?)?;

    Ok(())
}
