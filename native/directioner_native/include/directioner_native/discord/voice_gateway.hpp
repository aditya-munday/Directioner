#pragma once

#include <cstddef>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace directioner_native::discord {

struct DiscordBotConfig {
  std::string token;
  std::uint32_t intents = 0;
  std::uint32_t shard_count = 0;
  std::uint32_t cluster_id = 0;
  std::uint32_t cluster_count = 1;
  std::uint32_t pool_threads = 1;
  bool compressed = false;
  bool use_etf = false;
  bool register_global_commands = false;
};

[[nodiscard]] std::string dpp_construct_smoke(const DiscordBotConfig& config);

struct DiscordTextEvent {
  std::uint64_t guild_id = 0;
  std::uint64_t channel_id = 0;
  std::uint64_t message_id = 0;
  std::uint64_t author_id = 0;
  std::string content;
  bool author_is_bot = false;
};

struct DiscordVoiceFrame {
  std::uint64_t user_id = 0;
  std::vector<std::uint8_t> pcm_s16le_stereo_48khz;
};

struct VoiceGatewayStats {
  std::uint64_t text_messages_received = 0;
  std::uint64_t voice_frames_received = 0;
  std::uint64_t voice_bytes_received = 0;
  std::uint64_t pcm_bytes_sent = 0;
  std::uint64_t voice_ready_events = 0;
  std::uint64_t reconnects = 0;
  std::uint64_t errors = 0;
};

struct DiscordEmbed {
  std::string title;
  std::string description;
  std::string url;
  std::uint32_t color = 0;
  std::string footer_text;
  std::string footer_icon_url;
  std::string thumbnail_url;
  std::string image_url;
  std::string author_name;
  std::string author_url;
  std::string author_icon_url;
};

struct DiscordAttachment {
  std::string filename;
  std::vector<std::uint8_t> data;
  std::string content_type;
};

class DppDiscordRuntime {
 public:
  DppDiscordRuntime();
  DppDiscordRuntime(const DppDiscordRuntime&) = delete;
  DppDiscordRuntime& operator=(const DppDiscordRuntime&) = delete;
  ~DppDiscordRuntime();

  void start(const DiscordBotConfig& config);
  void stop() noexcept;

  [[nodiscard]] bool running() const noexcept;
  [[nodiscard]] VoiceGatewayStats stats() const noexcept;

  [[nodiscard]] bool join_user_voice(std::uint64_t guild_id, std::uint64_t user_id);
  [[nodiscard]] bool connect_voice(
      std::uint64_t guild_id,
      std::uint64_t channel_id,
      bool self_mute = false,
      bool self_deaf = false);
  void disconnect_voice(std::uint64_t guild_id);

  [[nodiscard]] bool send_text_message(std::uint64_t channel_id, const std::string& content);
  [[nodiscard]] bool send_embed(
      std::uint64_t channel_id,
      const DiscordEmbed& embed,
      std::uint64_t reply_to_message_id = 0);
  [[nodiscard]] bool send_message_with_embed(
      std::uint64_t channel_id,
      const std::string& content,
      const DiscordEmbed& embed,
      std::uint64_t reply_to_message_id = 0);
  [[nodiscard]] bool send_message_with_attachment(
      std::uint64_t channel_id,
      const std::string& content,
      const DiscordAttachment& attachment,
      std::uint64_t reply_to_message_id = 0);
  [[nodiscard]] bool send_voice_pcm(
      std::uint64_t guild_id,
      const std::vector<std::uint8_t>& pcm_s16le_stereo_48khz);

  void attach_voice_input_ring(std::string name, std::size_t capacity_bytes, bool initialize);
  [[nodiscard]] bool voice_input_ring_attached() const;
  void attach_voice_output_ring(std::string name, std::size_t capacity_bytes, bool initialize);
  [[nodiscard]] bool voice_output_ring_attached() const;
  [[nodiscard]] bool pump_voice_output_once(std::uint64_t guild_id, std::size_t max_frame_bytes);

  [[nodiscard]] bool pop_text_event(DiscordTextEvent& event);
  [[nodiscard]] bool pop_voice_frame(DiscordVoiceFrame& frame);

 private:
  class Impl;

  std::unique_ptr<Impl> impl_;
};

using VoiceGateway = DppDiscordRuntime;

}  // namespace directioner_native::discord
