#include "directioner_native/discord/voice_gateway.hpp"
#include "directioner_native/runtime/build_info.hpp"
#include "directioner_native/runtime/worker_pool.hpp"
#include "directioner_native/shared_memory/mapped_region.hpp"
#include "directioner_native/shared_memory/spsc_ring_buffer.hpp"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <span>
#include <sstream>
#include <string>
#include <vector>

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

namespace nb = nanobind;

namespace {

std::mutex runtime_mutex;
std::unique_ptr<directioner_native::runtime::WorkerPool> runtime_pool;
std::string runtime_namespace;

std::span<const std::byte> bytes_as_byte_span(nb::bytes bytes) {
  char* buffer = nullptr;
  Py_ssize_t size = 0;
  if (PyBytes_AsStringAndSize(bytes.ptr(), &buffer, &size) != 0) {
    throw nb::python_error();
  }
  return {reinterpret_cast<const std::byte*>(buffer), static_cast<std::size_t>(size)};
}

std::vector<std::uint8_t> bytes_as_u8_vector(nb::bytes bytes) {
  const auto span = bytes_as_byte_span(bytes);
  const auto* begin = reinterpret_cast<const std::uint8_t*>(span.data());
  return {begin, begin + span.size()};
}

void start_audio_runtime(const std::string& shared_memory_namespace, const std::size_t worker_threads) {
  std::scoped_lock lock(runtime_mutex);
  if (runtime_pool != nullptr && runtime_pool->running()) {
    return;
  }

  runtime_namespace = shared_memory_namespace;
  runtime_pool = std::make_unique<directioner_native::runtime::WorkerPool>();
  runtime_pool->start(worker_threads == 0 ? 1 : worker_threads);
}

void stop_audio_runtime() {
  std::scoped_lock lock(runtime_mutex);
  if (runtime_pool == nullptr) {
    return;
  }

  runtime_pool->stop();
  runtime_pool.reset();
  runtime_namespace.clear();
}

std::string native_build_info() {
  std::ostringstream out;
  out << directioner_native::runtime::project_name << " native ABI "
      << directioner_native::runtime::native_abi << " via "
      << directioner_native::runtime::bridge;
  return out.str();
}

}  // namespace

NB_MODULE(_native, m) {
  m.doc() = "Directioner native real-time audio bridge";

  nb::class_<directioner_native::discord::DiscordBotConfig>(m, "DiscordBotConfig")
      .def(nb::init<>())
      .def_rw("token", &directioner_native::discord::DiscordBotConfig::token)
      .def_rw("intents", &directioner_native::discord::DiscordBotConfig::intents)
      .def_rw("shard_count", &directioner_native::discord::DiscordBotConfig::shard_count)
      .def_rw("cluster_id", &directioner_native::discord::DiscordBotConfig::cluster_id)
      .def_rw("cluster_count", &directioner_native::discord::DiscordBotConfig::cluster_count)
      .def_rw("pool_threads", &directioner_native::discord::DiscordBotConfig::pool_threads)
      .def_rw("compressed", &directioner_native::discord::DiscordBotConfig::compressed)
      .def_rw("use_etf", &directioner_native::discord::DiscordBotConfig::use_etf)
      .def_rw(
          "register_global_commands",
          &directioner_native::discord::DiscordBotConfig::register_global_commands);

  nb::class_<directioner_native::discord::DiscordTextEvent>(m, "DiscordTextEvent")
      .def_ro("guild_id", &directioner_native::discord::DiscordTextEvent::guild_id)
      .def_ro("channel_id", &directioner_native::discord::DiscordTextEvent::channel_id)
      .def_ro("message_id", &directioner_native::discord::DiscordTextEvent::message_id)
      .def_ro("author_id", &directioner_native::discord::DiscordTextEvent::author_id)
      .def_ro("content", &directioner_native::discord::DiscordTextEvent::content)
      .def_ro("author_is_bot", &directioner_native::discord::DiscordTextEvent::author_is_bot);

  nb::class_<directioner_native::discord::VoiceGatewayStats>(m, "VoiceGatewayStats")
      .def_ro(
          "text_messages_received",
          &directioner_native::discord::VoiceGatewayStats::text_messages_received)
      .def_ro(
          "voice_frames_received",
          &directioner_native::discord::VoiceGatewayStats::voice_frames_received)
      .def_ro(
          "voice_bytes_received",
          &directioner_native::discord::VoiceGatewayStats::voice_bytes_received)
      .def_ro("pcm_bytes_sent", &directioner_native::discord::VoiceGatewayStats::pcm_bytes_sent)
      .def_ro(
          "voice_ready_events",
          &directioner_native::discord::VoiceGatewayStats::voice_ready_events)
      .def_ro("reconnects", &directioner_native::discord::VoiceGatewayStats::reconnects)
      .def_ro("errors", &directioner_native::discord::VoiceGatewayStats::errors);

  nb::class_<directioner_native::discord::DiscordEmbed>(m, "DiscordEmbed")
      .def(nb::init<>())
      .def_rw("title", &directioner_native::discord::DiscordEmbed::title)
      .def_rw("description", &directioner_native::discord::DiscordEmbed::description)
      .def_rw("url", &directioner_native::discord::DiscordEmbed::url)
      .def_rw("color", &directioner_native::discord::DiscordEmbed::color)
      .def_rw("footer_text", &directioner_native::discord::DiscordEmbed::footer_text)
      .def_rw("footer_icon_url", &directioner_native::discord::DiscordEmbed::footer_icon_url)
      .def_rw("thumbnail_url", &directioner_native::discord::DiscordEmbed::thumbnail_url)
      .def_rw("image_url", &directioner_native::discord::DiscordEmbed::image_url)
      .def_rw("author_name", &directioner_native::discord::DiscordEmbed::author_name)
      .def_rw("author_url", &directioner_native::discord::DiscordEmbed::author_url)
      .def_rw("author_icon_url", &directioner_native::discord::DiscordEmbed::author_icon_url);

  nb::class_<directioner_native::discord::DiscordAttachment>(m, "DiscordAttachment")
      .def(nb::init<>())
      .def_rw("filename", &directioner_native::discord::DiscordAttachment::filename)
      .def_rw("data", &directioner_native::discord::DiscordAttachment::data)
      .def_rw("content_type", &directioner_native::discord::DiscordAttachment::content_type);

  nb::class_<directioner_native::discord::DppDiscordRuntime>(m, "DppDiscordRuntime")
      .def(nb::init<>())
      .def("start", &directioner_native::discord::DppDiscordRuntime::start, nb::arg("config"))
      .def("stop", &directioner_native::discord::DppDiscordRuntime::stop)
      .def("running", &directioner_native::discord::DppDiscordRuntime::running)
      .def("stats", &directioner_native::discord::DppDiscordRuntime::stats)
      .def(
          "join_user_voice",
          &directioner_native::discord::DppDiscordRuntime::join_user_voice,
          nb::arg("guild_id"),
          nb::arg("user_id"))
      .def(
          "connect_voice",
          &directioner_native::discord::DppDiscordRuntime::connect_voice,
          nb::arg("guild_id"),
          nb::arg("channel_id"),
          nb::arg("self_mute") = false,
          nb::arg("self_deaf") = false)
      .def(
          "disconnect_voice",
          &directioner_native::discord::DppDiscordRuntime::disconnect_voice,
          nb::arg("guild_id"))
      .def(
          "send_text_message",
          &directioner_native::discord::DppDiscordRuntime::send_text_message,
          nb::arg("channel_id"),
          nb::arg("content"))
      .def(
          "send_embed",
          &directioner_native::discord::DppDiscordRuntime::send_embed,
          nb::arg("channel_id"),
          nb::arg("embed"),
          nb::arg("reply_to_message_id") = 0)
      .def(
          "send_message_with_embed",
          &directioner_native::discord::DppDiscordRuntime::send_message_with_embed,
          nb::arg("channel_id"),
          nb::arg("content"),
          nb::arg("embed"),
          nb::arg("reply_to_message_id") = 0)
      .def(
          "send_message_with_attachment",
          &directioner_native::discord::DppDiscordRuntime::send_message_with_attachment,
          nb::arg("channel_id"),
          nb::arg("content"),
          nb::arg("attachment"),
          nb::arg("reply_to_message_id") = 0)
      .def(
          "send_voice_pcm",
          [](directioner_native::discord::DppDiscordRuntime& runtime,
             const std::uint64_t guild_id,
             nb::bytes pcm) {
            const std::vector<std::uint8_t> payload = bytes_as_u8_vector(pcm);
            return runtime.send_voice_pcm(guild_id, payload);
          },
          nb::arg("guild_id"),
          nb::arg("pcm_s16le_stereo_48khz"))
      .def(
          "attach_voice_input_ring",
          &directioner_native::discord::DppDiscordRuntime::attach_voice_input_ring,
          nb::arg("name"),
          nb::arg("capacity_bytes"),
          nb::arg("initialize") = true)
      .def(
          "voice_input_ring_attached",
          &directioner_native::discord::DppDiscordRuntime::voice_input_ring_attached)
      .def(
          "attach_voice_output_ring",
          &directioner_native::discord::DppDiscordRuntime::attach_voice_output_ring,
          nb::arg("name"),
          nb::arg("capacity_bytes"),
          nb::arg("initialize") = true)
      .def(
          "voice_output_ring_attached",
          &directioner_native::discord::DppDiscordRuntime::voice_output_ring_attached)
      .def(
          "pump_voice_output_once",
          &directioner_native::discord::DppDiscordRuntime::pump_voice_output_once,
          nb::arg("guild_id"),
          nb::arg("max_frame_bytes"))
      .def(
          "pop_text_event",
          [](directioner_native::discord::DppDiscordRuntime& runtime) -> nb::object {
            directioner_native::discord::DiscordTextEvent event;
            if (!runtime.pop_text_event(event)) {
              return nb::none();
            }
            return nb::cast(event);
          })
      .def(
          "pop_voice_frame",
          [](directioner_native::discord::DppDiscordRuntime& runtime) -> nb::object {
            directioner_native::discord::DiscordVoiceFrame frame;
            if (!runtime.pop_voice_frame(frame)) {
              return nb::none();
            }

            nb::dict out;
            out["user_id"] = frame.user_id;
            out["pcm_s16le_stereo_48khz"] = nb::bytes(
                reinterpret_cast<const char*>(frame.pcm_s16le_stereo_48khz.data()),
                frame.pcm_s16le_stereo_48khz.size());
            return std::move(out);
          });

  m.def(
      "dpp_construct_smoke",
      &directioner_native::discord::dpp_construct_smoke,
      nb::arg("config"));

  nb::class_<directioner_native::shared_memory::SharedMemoryRegion>(m, "SharedMemoryRegion")
      .def_static(
          "create_or_open",
          &directioner_native::shared_memory::SharedMemoryRegion::create_or_open,
          nb::arg("name"),
          nb::arg("bytes"))
      .def_static(
          "open_existing",
          &directioner_native::shared_memory::SharedMemoryRegion::open_existing,
          nb::arg("name"),
          nb::arg("bytes"))
      .def("name", &directioner_native::shared_memory::SharedMemoryRegion::name)
      .def("size", &directioner_native::shared_memory::SharedMemoryRegion::size)
      .def("mapped", &directioner_native::shared_memory::SharedMemoryRegion::mapped)
      .def("close", &directioner_native::shared_memory::SharedMemoryRegion::close)
      .def(
          "initialize_ring",
          [](directioner_native::shared_memory::SharedMemoryRegion& region,
             const std::size_t capacity_bytes) {
            directioner_native::shared_memory::SpscRingBufferView::initialize(
                region.bytes(),
                capacity_bytes);
          },
          nb::arg("capacity_bytes"))
      .def(
          "read_ring_frame",
          [](directioner_native::shared_memory::SharedMemoryRegion& region,
             const std::size_t max_bytes) -> nb::object {
            directioner_native::shared_memory::SpscRingBufferView ring(region.bytes());
            std::vector<std::byte> out(max_bytes);
            std::size_t bytes_read = 0;
            if (!ring.try_read(out, bytes_read)) {
              return nb::none();
            }
            return nb::bytes(reinterpret_cast<const char*>(out.data()), bytes_read);
          },
          nb::arg("max_bytes"))
      .def(
          "write_ring_frame",
          [](directioner_native::shared_memory::SharedMemoryRegion& region,
             nb::bytes payload) {
            directioner_native::shared_memory::SpscRingBufferView ring(region.bytes());
            return ring.try_write(bytes_as_byte_span(payload));
          },
          nb::arg("payload"));

  m.def("native_build_info", &native_build_info);
  m.def(
      "required_ring_bytes",
      &directioner_native::shared_memory::SpscRingBufferView::required_bytes,
      nb::arg("capacity_bytes"));
  m.def(
      "start_audio_runtime",
      &start_audio_runtime,
      nb::arg("shared_memory_namespace"),
      nb::arg("worker_threads") = 1);
  m.def("stop_audio_runtime", &stop_audio_runtime);
}
