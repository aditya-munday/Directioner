//! Discord runtime implementation.
//!
//! This module provides a simplified Discord runtime that supports text messaging
//! without voice functionality. Voice features are skipped as per configuration.

use pyo3::prelude::*;

/// Configuration for the Discord bot.
#[pyclass]
#[derive(Default)]
pub struct DiscordBotConfig {
    /// Discord bot token
    #[pyo3(get, set)]
    pub token: Option<String>,
    /// Gateway intents (not used in text-only mode)
    #[pyo3(get, set)]
    pub intents: u64,
    /// Number of shards
    #[pyo3(get, set)]
    pub shard_count: u32,
    /// Current cluster ID
    #[pyo3(get, set)]
    pub cluster_id: u32,
    /// Total number of clusters
    #[pyo3(get, set)]
    pub cluster_count: u32,
    /// Number of threads in the native pool
    #[pyo3(get, set)]
    pub pool_threads: u32,
    /// Whether to use voice compression
    #[pyo3(get, set)]
    pub compressed: bool,
    /// Whether to use ETF serialization
    #[pyo3(get, set)]
    pub use_etf: bool,
    /// Whether to register global commands
    #[pyo3(get, set)]
    pub register_global_commands: bool,
}

#[pymethods]
impl DiscordBotConfig {
    #[new]
    pub fn new() -> Self {
        Self::default()
    }
}

/// Text event from Discord (simplified for text-only mode).
#[pyclass]
pub struct DiscordTextEvent {
    /// Guild ID where the message was sent
    #[pyo3(get)]
    pub guild_id: u64,
    /// Channel ID where the message was sent
    #[pyo3(get)]
    pub channel_id: u64,
    /// Message ID
    #[pyo3(get)]
    pub message_id: u64,
    /// Author's user ID
    #[pyo3(get)]
    pub author_id: u64,
    /// Message content
    #[pyo3(get)]
    pub content: String,
    /// Whether the author is a bot
    #[pyo3(get)]
    pub author_is_bot: bool,
}

/// Voice gateway statistics (placeholder for compatibility).
#[pyclass]
#[derive(Default)]
pub struct VoiceGatewayStats {
    /// Number of text messages received
    #[pyo3(get)]
    pub text_messages_received: u64,
    /// Number of voice frames received (always 0 in text-only mode)
    #[pyo3(get)]
    pub voice_frames_received: u64,
    /// Number of voice bytes received (always 0 in text-only mode)
    #[pyo3(get)]
    pub voice_bytes_received: u64,
    /// Number of PCM bytes sent (always 0 in text-only mode)
    #[pyo3(get)]
    pub pcm_bytes_sent: u64,
    /// Number of voice ready events (always 0 in text-only mode)
    #[pyo3(get)]
    pub voice_ready_events: u64,
    /// Number of reconnects (always 0 in text-only mode)
    #[pyo3(get)]
    pub reconnects: u64,
    /// Number of errors (always 0 in text-only mode)
    #[pyo3(get)]
    pub errors: u64,
}

/// Embed for rich Discord messages.
#[pyclass]
#[derive(Default)]
pub struct DiscordEmbed {
    #[pyo3(get, set)]
    pub title: Option<String>,
    #[pyo3(get, set)]
    pub description: Option<String>,
    #[pyo3(get, set)]
    pub url: Option<String>,
    #[pyo3(get, set)]
    pub color: Option<u32>,
    #[pyo3(get, set)]
    pub footer_text: Option<String>,
    #[pyo3(get, set)]
    pub footer_icon_url: Option<String>,
    #[pyo3(get, set)]
    pub thumbnail_url: Option<String>,
    #[pyo3(get, set)]
    pub image_url: Option<String>,
    #[pyo3(get, set)]
    pub author_name: Option<String>,
    #[pyo3(get, set)]
    pub author_url: Option<String>,
    #[pyo3(get, set)]
    pub author_icon_url: Option<String>,
}

/// Attachment for Discord messages.
#[pyclass]
#[derive(Default)]
pub struct DiscordAttachment {
    #[pyo3(get, set)]
    pub filename: Option<String>,
    #[pyo3(get, set)]
    pub data: Option<Vec<u8>>,
    #[pyo3(get, set)]
    pub content_type: Option<String>,
}

/// Placeholder voice frame (always empty in text-only mode).
#[pyclass]
pub struct DiscordVoiceFrame {
    #[pyo3(get)]
    pub user_id: u64,
    #[pyo3(get)]
    pub pcm_s16le_stereo_48khz: Vec<u8>,
}

/// Discord runtime for text-only operations.
///
/// This is a placeholder implementation that provides the expected API
/// but indicates that voice functionality is disabled.
#[pyclass]
pub struct DppDiscordRuntime {
    /// Whether the runtime is currently running
    running: bool,
    /// Statistics for the runtime
    stats: VoiceGatewayStats,
    /// Pending text events queue (placeholder)
    pending_events: Vec<DiscordTextEvent>,
}

impl Default for DppDiscordRuntime {
    fn default() -> Self {
        Self {
            running: false,
            stats: VoiceGatewayStats::default(),
            pending_events: Vec::new(),
        }
    }
}

#[pymethods]
impl DppDiscordRuntime {
    #[new]
    pub fn new() -> Self {
        Self::default()
    }

    /// Constructs a smoke test message (static method).
    /// This verifies that the runtime can be instantiated.
    #[staticmethod]
    pub fn construct_smoke_static(config: &DiscordBotConfig) -> String {
        format!(
            "DppDiscordRuntime smoke test - voice disabled, token configured: {}",
            config.token.as_ref().map(|_| true).unwrap_or(false)
        )
    }

    /// Starts the Discord runtime.
    /// In text-only mode, this logs a message indicating voice is disabled.
    pub fn start(&mut self, config: &DiscordBotConfig) {
        if config.token.is_none() {
            return;
        }
        self.running = true;
        self.stats.text_messages_received = 0;
    }

    /// Stops the Discord runtime.
    pub fn stop(&mut self) {
        self.running = false;
    }

    /// Returns whether the runtime is running.
    pub fn running(&self) -> bool {
        self.running
    }

    /// Returns runtime statistics.
    pub fn stats(&self) -> Option<VoiceGatewayStats> {
        if !self.running {
            None
        } else {
            Some(self.stats.clone())
        }
    }

    /// Placeholder for joining a user's voice channel.
    /// Always returns false in text-only mode.
    pub fn join_user_voice(&self, _guild_id: u64, _user_id: u64) -> bool {
        false
    }

    /// Placeholder for connecting to a voice channel.
    /// Always returns false in text-only mode.
    pub fn connect_voice(
        &self,
        _guild_id: u64,
        _channel_id: u64,
        _self_mute: bool,
        _self_deaf: bool,
    ) -> bool {
        false
    }

    /// Placeholder for disconnecting from a voice channel.
    pub fn disconnect_voice(&self, _guild_id: u64) {}

    /// Placeholder for sending a text message.
    /// Always returns false in text-only mode.
    pub fn send_text_message(&self, _channel_id: u64, _content: &str) -> bool {
        false
    }

    /// Placeholder for sending voice PCM data.
    /// Always returns false in text-only mode.
    pub fn send_voice_pcm(&self, _guild_id: u64, _pcm_s16le_stereo_48khz: Vec<u8>) -> bool {
        false
    }

    /// Placeholder for attaching a voice input ring buffer.
    /// Voice functionality is disabled.
    pub fn attach_voice_input_ring(
        &self,
        _name: &str,
        _capacity_bytes: usize,
        _initialize: bool,
    ) -> bool {
        false
    }

    /// Returns whether a voice input ring is attached.
    pub fn voice_input_ring_attached(&self) -> bool {
        false
    }

    /// Placeholder for attaching a voice output ring buffer.
    /// Voice functionality is disabled.
    pub fn attach_voice_output_ring(
        &self,
        _name: &str,
        _capacity_bytes: usize,
        _initialize: bool,
    ) -> bool {
        false
    }

    /// Returns whether a voice output ring is attached.
    pub fn voice_output_ring_attached(&self) -> bool {
        false
    }

    /// Placeholder for pumping voice output.
    /// Always returns false in text-only mode.
    pub fn pump_voice_output_once(&self, _guild_id: u64, _max_frame_bytes: usize) -> bool {
        false
    }

    /// Returns the next text event, if any.
    pub fn pop_text_event(&mut self) -> Option<DiscordTextEvent> {
        self.pending_events.pop()
    }

    /// Returns the next voice frame, if any.
    /// Always returns None in text-only mode.
    pub fn pop_voice_frame(&mut self) -> Option<DiscordVoiceFrame> {
        None
    }
}

impl Clone for VoiceGatewayStats {
    fn clone(&self) -> Self {
        Self {
            text_messages_received: self.text_messages_received,
            voice_frames_received: self.voice_frames_received,
            voice_bytes_received: self.voice_bytes_received,
            pcm_bytes_sent: self.pcm_bytes_sent,
            voice_ready_events: self.voice_ready_events,
            reconnects: self.reconnects,
            errors: self.errors,
        }
    }
}
