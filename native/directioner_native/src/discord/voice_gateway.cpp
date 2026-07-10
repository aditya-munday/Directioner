#include "directioner_native/discord/voice_gateway.hpp"

#include "directioner_native/audio/frame.hpp"
#include "directioner_native/shared_memory/mapped_region.hpp"
#include "directioner_native/shared_memory/spsc_ring_buffer.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <span>
#include <sstream>
#include <stdexcept>
#include <utility>

#if DIRECTIONER_WITH_DPP
#include <dpp/dpp.h>
#include <dpp/version.h>
#endif

namespace directioner_native::discord {
namespace {

constexpr std::size_t max_text_queue = 4096;
constexpr std::size_t max_voice_queue = 2048;

#if DIRECTIONER_WITH_DPP
std::uint32_t default_intents() {
  return dpp::i_default_intents | dpp::i_guild_voice_states | dpp::i_guild_messages |
         dpp::i_direct_messages | dpp::i_message_content;
}

std::uint32_t shard_for_guild(const dpp::cluster& bot, const std::uint64_t guild_id) {
  const auto shard_count = std::max<std::uint32_t>(bot.numshards, 1);
  return static_cast<std::uint32_t>((guild_id >> 22U) % shard_count);
}
#endif

}  // namespace

std::string dpp_construct_smoke(const DiscordBotConfig& config) {
#if DIRECTIONER_WITH_DPP
  if (config.token.empty()) {
    throw std::invalid_argument("Discord bot token is required");
  }
  const auto intents = config.intents == 0 ? default_intents() : config.intents;
  dpp::cluster bot(
      config.token,
      intents,
      config.shard_count,
      config.cluster_id,
      config.cluster_count,
      config.compressed,
      dpp::cache_policy::cpol_default,
      config.pool_threads == 0 ? 1 : config.pool_threads);
  std::ostringstream out;
  out << "constructed dpp::cluster version=" << DPP_VERSION_TEXT
      << " shards=" << bot.numshards
      << " pool_threads=" << (config.pool_threads == 0 ? 1 : config.pool_threads);
  return out.str();
#else
  (void)config;
  throw std::runtime_error("Directioner was built without DPP support");
#endif
}

class DppDiscordRuntime::Impl {
 public:
  Impl() = default;
  Impl(const Impl&) = delete;
  Impl& operator=(const Impl&) = delete;

  ~Impl() {
    stop();
  }

  void start(const DiscordBotConfig& config) {
#if DIRECTIONER_WITH_DPP
    if (config.token.empty()) {
      throw std::invalid_argument("Discord bot token is required");
    }

    std::scoped_lock lock(lifecycle_mutex_);
    if (running_.load(std::memory_order_acquire)) {
      return;
    }

    const auto intents = config.intents == 0 ? default_intents() : config.intents;
    bot_ = std::make_unique<dpp::cluster>(
        config.token,
        intents,
        config.shard_count,
        config.cluster_id,
        config.cluster_count,
        config.compressed,
        dpp::cache_policy::cpol_default,
        config.pool_threads == 0 ? 1 : config.pool_threads);

    if (config.use_etf) {
      bot_->set_websocket_protocol(dpp::ws_etf);
    }

    attach_handlers(config.register_global_commands);
    running_.store(true, std::memory_order_release);
    bot_->start(dpp::st_return);
#else
    (void)config;
    throw std::runtime_error("Directioner was built without DPP support");
#endif
  }

  void stop() noexcept {
#if DIRECTIONER_WITH_DPP
    std::scoped_lock lock(lifecycle_mutex_);
    if (bot_ != nullptr) {
      bot_.reset();
    }
#endif
    running_.store(false, std::memory_order_release);
  }

  [[nodiscard]] bool running() const noexcept {
    return running_.load(std::memory_order_acquire);
  }

  [[nodiscard]] VoiceGatewayStats stats() const noexcept {
    return VoiceGatewayStats{
        text_messages_received_.load(std::memory_order_relaxed),
        voice_frames_received_.load(std::memory_order_relaxed),
        voice_bytes_received_.load(std::memory_order_relaxed),
        pcm_bytes_sent_.load(std::memory_order_relaxed),
        voice_ready_events_.load(std::memory_order_relaxed),
        reconnects_.load(std::memory_order_relaxed),
        errors_.load(std::memory_order_relaxed)};
  }

  [[nodiscard]] bool join_user_voice(const std::uint64_t guild_id, const std::uint64_t user_id) {
#if DIRECTIONER_WITH_DPP
    std::scoped_lock lock(lifecycle_mutex_);
    if (!bot_) {
      return false;
    }

    auto* guild = dpp::find_guild(dpp::snowflake(guild_id));
    if (guild == nullptr) {
      return false;
    }
    return guild->connect_member_voice(*bot_, dpp::snowflake(user_id));
#else
    (void)guild_id;
    (void)user_id;
    return false;
#endif
  }

  [[nodiscard]] bool connect_voice(
      const std::uint64_t guild_id,
      const std::uint64_t channel_id,
      const bool self_mute,
      const bool self_deaf) {
#if DIRECTIONER_WITH_DPP
    std::scoped_lock lock(lifecycle_mutex_);
    auto* shard = shard_for_guild_locked(guild_id);
    if (shard == nullptr) {
      return false;
    }

    shard->connect_voice(
        dpp::snowflake(guild_id),
        dpp::snowflake(channel_id),
        self_mute,
        self_deaf);
    return true;
#else
    (void)guild_id;
    (void)channel_id;
    (void)self_mute;
    (void)self_deaf;
    return false;
#endif
  }

  void disconnect_voice(const std::uint64_t guild_id) {
#if DIRECTIONER_WITH_DPP
    std::scoped_lock lock(lifecycle_mutex_);
    auto* shard = shard_for_guild_locked(guild_id);
    if (shard != nullptr) {
      shard->disconnect_voice(dpp::snowflake(guild_id));
    }
#else
    (void)guild_id;
#endif
  }

  [[nodiscard]] bool send_text_message(
      const std::uint64_t channel_id,
      const std::string& content) {
#if DIRECTIONER_WITH_DPP
    std::scoped_lock lock(lifecycle_mutex_);
    if (!bot_ || content.empty()) {
      return false;
    }

    bot_->message_create(dpp::message(dpp::snowflake(channel_id), content));
    return true;
#else
    (void)channel_id;
    (void)content;
    return false;
#endif
  }

  [[nodiscard]] bool send_voice_pcm(
      const std::uint64_t guild_id,
      const std::vector<std::uint8_t>& pcm_s16le_stereo_48khz) {
#if DIRECTIONER_WITH_DPP
    std::scoped_lock lock(lifecycle_mutex_);
    if (!bot_ || pcm_s16le_stereo_48khz.empty() || pcm_s16le_stereo_48khz.size() % 2U != 0U) {
      return false;
    }

    auto* shard = shard_for_guild_locked(guild_id);
    if (shard == nullptr) {
      return false;
    }

    auto* voice = shard->get_voice(dpp::snowflake(guild_id));
    if (voice == nullptr || !voice->voiceclient || !voice->voiceclient->is_ready()) {
      return false;
    }

    auto* samples = reinterpret_cast<std::uint16_t*>(
        const_cast<std::uint8_t*>(pcm_s16le_stereo_48khz.data()));
    voice->voiceclient->send_audio_raw(samples, pcm_s16le_stereo_48khz.size());
    pcm_bytes_sent_.fetch_add(pcm_s16le_stereo_48khz.size(), std::memory_order_relaxed);
    return true;
#else
    (void)guild_id;
    (void)pcm_s16le_stereo_48khz;
    return false;
#endif
  }

  void attach_voice_input_ring(
      std::string name,
      const std::size_t capacity_bytes,
      const bool initialize) {
    auto region_value = shared_memory::SharedMemoryRegion::create_or_open(
        std::move(name),
        shared_memory::SpscRingBufferView::required_bytes(capacity_bytes));
    auto region = std::make_unique<shared_memory::SharedMemoryRegion>(std::move(region_value));
    if (initialize) {
      shared_memory::SpscRingBufferView::initialize(region->bytes(), capacity_bytes);
    }

    auto ring = std::make_unique<shared_memory::SpscRingBufferView>(region->bytes());
    std::scoped_lock lock(ring_mutex_);
    voice_pcm_in_region_ = std::move(region);
    voice_pcm_in_ring_ = std::move(ring);
  }

  [[nodiscard]] bool voice_input_ring_attached() const {
    std::scoped_lock lock(ring_mutex_);
    return voice_pcm_in_ring_ != nullptr;
  }

  void attach_voice_output_ring(
      std::string name,
      const std::size_t capacity_bytes,
      const bool initialize) {
    auto region_value = shared_memory::SharedMemoryRegion::create_or_open(
        std::move(name),
        shared_memory::SpscRingBufferView::required_bytes(capacity_bytes));
    auto region = std::make_unique<shared_memory::SharedMemoryRegion>(std::move(region_value));
    if (initialize) {
      shared_memory::SpscRingBufferView::initialize(region->bytes(), capacity_bytes);
    }

    auto ring = std::make_unique<shared_memory::SpscRingBufferView>(region->bytes());
    std::scoped_lock lock(output_ring_mutex_);
    voice_pcm_out_region_ = std::move(region);
    voice_pcm_out_ring_ = std::move(ring);
  }

  [[nodiscard]] bool voice_output_ring_attached() const {
    std::scoped_lock lock(output_ring_mutex_);
    return voice_pcm_out_ring_ != nullptr;
  }

  [[nodiscard]] bool pump_voice_output_once(
      const std::uint64_t guild_id,
      const std::size_t max_frame_bytes) {
    std::vector<std::byte> frame(max_frame_bytes);
    std::size_t bytes_read = 0;

    {
      std::scoped_lock lock(output_ring_mutex_);
      if (voice_pcm_out_ring_ == nullptr || !voice_pcm_out_ring_->try_read(frame, bytes_read)) {
        return false;
      }
    }

    std::vector<std::uint8_t> pcm(bytes_read);
    std::memcpy(pcm.data(), frame.data(), bytes_read);
    return send_voice_pcm(guild_id, pcm);
  }

  [[nodiscard]] bool pop_text_event(DiscordTextEvent& event) {
    std::scoped_lock lock(queue_mutex_);
    if (text_events_.empty()) {
      return false;
    }

    event = std::move(text_events_.front());
    text_events_.pop_front();
    return true;
  }

  [[nodiscard]] bool pop_voice_frame(DiscordVoiceFrame& frame) {
    std::scoped_lock lock(queue_mutex_);
    if (voice_frames_.empty()) {
      return false;
    }

    frame = std::move(voice_frames_.front());
    voice_frames_.pop_front();
    return true;
  }

 private:
#if DIRECTIONER_WITH_DPP
  void attach_handlers(const bool register_global_commands) {
    bot_->on_log([this](const dpp::log_t& event) {
      if (event.severity >= dpp::ll_error) {
        errors_.fetch_add(1, std::memory_order_relaxed);
      }
    });

    bot_->on_ready([this, register_global_commands](const dpp::ready_t&) {
      if (!register_global_commands || !bot_) {
        return;
      }
      if (dpp::run_once<struct directioner_register_dpp_commands>()) {
        bot_->global_bulk_command_create({
            dpp::slashcommand("join", "Join your current voice channel.", bot_->me.id),
            dpp::slashcommand("leave", "Leave the current voice channel.", bot_->me.id),
        });
      }
    });

    bot_->on_slashcommand([this](const dpp::slashcommand_t& event) {
      const auto command_name = event.command.get_command_name();
      if (command_name == "join") {
        auto* guild = dpp::find_guild(event.command.guild_id);
        if (guild == nullptr ||
            !guild->connect_member_voice(*event.owner, event.command.get_issuing_user().id)) {
          event.reply("I could not join your voice channel.");
          return;
        }
        event.reply("Joined your voice channel.");
        return;
      }

      if (command_name == "leave") {
        event.from()->disconnect_voice(event.command.guild_id);
        event.reply("Left the voice channel.");
      }
    });

    bot_->on_message_create([this](const dpp::message_create_t& event) {
      const auto& msg = event.msg;
      DiscordTextEvent text_event{
          static_cast<std::uint64_t>(msg.guild_id),
          static_cast<std::uint64_t>(msg.channel_id),
          static_cast<std::uint64_t>(msg.id),
          static_cast<std::uint64_t>(msg.author.id),
          msg.content,
          msg.author.is_bot()};
      push_text_event(std::move(text_event));
    });

    bot_->on_voice_receive([this](const dpp::voice_receive_t& event) {
      DiscordVoiceFrame frame;
      frame.user_id = static_cast<std::uint64_t>(event.user_id);
      const auto* audio = reinterpret_cast<const std::uint8_t*>(event.audio);
      frame.pcm_s16le_stereo_48khz.assign(audio, audio + event.audio_size);
      voice_bytes_received_.fetch_add(event.audio_size, std::memory_order_relaxed);
      voice_frames_received_.fetch_add(1, std::memory_order_relaxed);
      write_voice_frame_to_ring(
          static_cast<std::uint64_t>(event.user_id),
          std::span<const std::uint8_t>(audio, event.audio_size));
      push_voice_frame(std::move(frame));
    });

    bot_->on_voice_ready([this](const dpp::voice_ready_t&) {
      voice_ready_events_.fetch_add(1, std::memory_order_relaxed);
    });
  }

  dpp::discord_client* shard_for_guild_locked(const std::uint64_t guild_id) const {
    if (!bot_) {
      return nullptr;
    }
    return bot_->get_shard(shard_for_guild(*bot_, guild_id));
  }
#endif

  void push_text_event(DiscordTextEvent event) {
    std::scoped_lock lock(queue_mutex_);
    if (text_events_.size() >= max_text_queue) {
      text_events_.pop_front();
    }
    text_events_.push_back(std::move(event));
    text_messages_received_.fetch_add(1, std::memory_order_relaxed);
  }

  void push_voice_frame(DiscordVoiceFrame frame) {
    std::scoped_lock lock(queue_mutex_);
    if (voice_frames_.size() >= max_voice_queue) {
      voice_frames_.pop_front();
    }
    voice_frames_.push_back(std::move(frame));
  }

  void write_voice_frame_to_ring(
      const std::uint64_t user_id,
      std::span<const std::uint8_t> pcm_s16le_stereo_48khz) {
    std::scoped_lock lock(ring_mutex_);
    if (voice_pcm_in_ring_ == nullptr || pcm_s16le_stereo_48khz.empty()) {
      return;
    }

    audio::PcmFrameHeader header;
    header.stream_id = user_id;
    header.sequence = voice_frames_received_.load(std::memory_order_relaxed);
    header.capture_time_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch())
            .count());
    header.sample_rate_hz = 48000;
    header.channels = 2;
    header.sample_format = audio::SampleFormat::S16Le;
    header.frame_samples = static_cast<std::uint32_t>(pcm_s16le_stereo_48khz.size() / 4U);
    header.speaker_hint = static_cast<std::uint32_t>(user_id & 0xffffffffU);
    header.flags = static_cast<std::uint32_t>(audio::PcmFrameFlag::Speech);

    std::vector<std::byte> frame(sizeof(header) + pcm_s16le_stereo_48khz.size());
    std::memcpy(frame.data(), &header, sizeof(header));
    std::memcpy(
        frame.data() + sizeof(header),
        pcm_s16le_stereo_48khz.data(),
        pcm_s16le_stereo_48khz.size());
    if (!voice_pcm_in_ring_->try_write(frame)) {
      errors_.fetch_add(1, std::memory_order_relaxed);
    }
  }

  mutable std::mutex lifecycle_mutex_;
  mutable std::mutex queue_mutex_;
  mutable std::mutex ring_mutex_;
  mutable std::mutex output_ring_mutex_;
  std::atomic_bool running_{false};

#if DIRECTIONER_WITH_DPP
  std::unique_ptr<dpp::cluster> bot_;
#endif

  std::deque<DiscordTextEvent> text_events_;
  std::deque<DiscordVoiceFrame> voice_frames_;
  std::unique_ptr<shared_memory::SharedMemoryRegion> voice_pcm_in_region_;
  std::unique_ptr<shared_memory::SpscRingBufferView> voice_pcm_in_ring_;
  std::unique_ptr<shared_memory::SharedMemoryRegion> voice_pcm_out_region_;
  std::unique_ptr<shared_memory::SpscRingBufferView> voice_pcm_out_ring_;

  std::atomic_uint64_t text_messages_received_{0};
  std::atomic_uint64_t voice_frames_received_{0};
  std::atomic_uint64_t voice_bytes_received_{0};
  std::atomic_uint64_t pcm_bytes_sent_{0};
  std::atomic_uint64_t voice_ready_events_{0};
  std::atomic_uint64_t reconnects_{0};
  std::atomic_uint64_t errors_{0};
};

DppDiscordRuntime::DppDiscordRuntime() : impl_(std::make_unique<Impl>()) {}

DppDiscordRuntime::~DppDiscordRuntime() = default;

void DppDiscordRuntime::start(const DiscordBotConfig& config) {
  impl_->start(config);
}

void DppDiscordRuntime::stop() noexcept {
  impl_->stop();
}

bool DppDiscordRuntime::running() const noexcept {
  return impl_->running();
}

VoiceGatewayStats DppDiscordRuntime::stats() const noexcept {
  return impl_->stats();
}

bool DppDiscordRuntime::join_user_voice(
    const std::uint64_t guild_id,
    const std::uint64_t user_id) {
  return impl_->join_user_voice(guild_id, user_id);
}

bool DppDiscordRuntime::connect_voice(
    const std::uint64_t guild_id,
    const std::uint64_t channel_id,
    const bool self_mute,
    const bool self_deaf) {
  return impl_->connect_voice(guild_id, channel_id, self_mute, self_deaf);
}

void DppDiscordRuntime::disconnect_voice(const std::uint64_t guild_id) {
  impl_->disconnect_voice(guild_id);
}

bool DppDiscordRuntime::send_text_message(
    const std::uint64_t channel_id,
    const std::string& content) {
  return impl_->send_text_message(channel_id, content);
}

bool DppDiscordRuntime::send_voice_pcm(
    const std::uint64_t guild_id,
    const std::vector<std::uint8_t>& pcm_s16le_stereo_48khz) {
  return impl_->send_voice_pcm(guild_id, pcm_s16le_stereo_48khz);
}

void DppDiscordRuntime::attach_voice_input_ring(
    std::string name,
    const std::size_t capacity_bytes,
    const bool initialize) {
  impl_->attach_voice_input_ring(std::move(name), capacity_bytes, initialize);
}

bool DppDiscordRuntime::voice_input_ring_attached() const {
  return impl_->voice_input_ring_attached();
}

void DppDiscordRuntime::attach_voice_output_ring(
    std::string name,
    const std::size_t capacity_bytes,
    const bool initialize) {
  impl_->attach_voice_output_ring(std::move(name), capacity_bytes, initialize);
}

bool DppDiscordRuntime::voice_output_ring_attached() const {
  return impl_->voice_output_ring_attached();
}

bool DppDiscordRuntime::pump_voice_output_once(
    const std::uint64_t guild_id,
    const std::size_t max_frame_bytes) {
  return impl_->pump_voice_output_once(guild_id, max_frame_bytes);
}

bool DppDiscordRuntime::pop_text_event(DiscordTextEvent& event) {
  return impl_->pop_text_event(event);
}

bool DppDiscordRuntime::pop_voice_frame(DiscordVoiceFrame& frame) {
  return impl_->pop_voice_frame(frame);
}

}  // namespace directioner_native::discord
