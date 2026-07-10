#include <atomic>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <dpp/dpp.h>
#include <dpp/version.h>

namespace {

std::atomic_bool keep_running{true};
std::mutex output_mutex;

void handle_signal(int) {
  keep_running.store(false, std::memory_order_release);
}

std::uint32_t default_intents() {
  return dpp::i_default_intents | dpp::i_guild_voice_states | dpp::i_guild_messages |
         dpp::i_direct_messages | dpp::i_message_content;
}

bool has_arg(int argc, char** argv, const std::string& expected) {
  for (int index = 1; index < argc; ++index) {
    if (argv[index] == expected) {
      return true;
    }
  }
  return false;
}

int int_arg(int argc, char** argv, const std::string& expected, const int fallback) {
  for (int index = 1; index + 1 < argc; ++index) {
    if (argv[index] == expected) {
      return std::stoi(argv[index + 1]);
    }
  }
  return fallback;
}

std::string string_arg(int argc, char** argv, const std::string& expected, std::string fallback) {
  for (int index = 1; index + 1 < argc; ++index) {
    if (argv[index] == expected) {
      return argv[index + 1];
    }
  }
  return fallback;
}

std::string base64_encode(const std::string& input) {
  static constexpr char alphabet[] =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string output;
  output.reserve(((input.size() + 2) / 3) * 4);

  std::uint32_t buffer = 0;
  int bits = -6;
  for (const unsigned char byte : input) {
    buffer = (buffer << 8) | byte;
    bits += 8;
    while (bits >= 0) {
      output.push_back(alphabet[(buffer >> bits) & 0x3F]);
      bits -= 6;
    }
  }
  if (bits > -6) {
    output.push_back(alphabet[((buffer << 8) >> (bits + 8)) & 0x3F]);
  }
  while (output.size() % 4 != 0) {
    output.push_back('=');
  }
  return output;
}

std::string base64_decode(const std::string& input) {
  static constexpr unsigned char invalid = 255;
  static unsigned char table[256];
  static bool initialized = false;
  if (!initialized) {
    std::fill(std::begin(table), std::end(table), invalid);
    const std::string alphabet =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    for (std::size_t index = 0; index < alphabet.size(); ++index) {
      table[static_cast<unsigned char>(alphabet[index])] = static_cast<unsigned char>(index);
    }
    initialized = true;
  }

  std::string output;
  std::uint32_t buffer = 0;
  int bits = -8;
  for (const unsigned char byte : input) {
    if (byte == '=') {
      break;
    }
    if (table[byte] == invalid) {
      continue;
    }
    buffer = (buffer << 6) | table[byte];
    bits += 6;
    if (bits >= 0) {
      output.push_back(static_cast<char>((buffer >> bits) & 0xFF));
      bits -= 8;
    }
  }
  return output;
}

std::vector<std::string> split_tabs(const std::string& line) {
  std::vector<std::string> parts;
  std::stringstream stream(line);
  std::string item;
  while (std::getline(stream, item, '\t')) {
    parts.push_back(item);
  }
  return parts;
}

void emit_text_event(const dpp::message& message) {
  std::scoped_lock lock(output_mutex);
  std::cout << "DIRECTIONER_EVENT\tTEXT_MESSAGE\t" << message.guild_id << "\t"
            << message.channel_id << "\t" << message.id << "\t" << message.author.id << "\t"
            << (message.author.is_bot() ? "1" : "0") << "\t" << base64_encode(message.content)
            << "\n";
  std::cout.flush();
}

void log_line(const std::string& message) {
  std::cerr << message << "\n";
}

}  // namespace

int main(int argc, char** argv) {
  std::signal(SIGINT, handle_signal);
  std::signal(SIGTERM, handle_signal);

  const char* token_env = std::getenv("DISCORD_BOT_TOKEN");
  std::string token = string_arg(argc, argv, "--token", token_env == nullptr ? "" : token_env);
  const int timeout_seconds = int_arg(argc, argv, "--timeout", 0);
  const bool register_commands = has_arg(argc, argv, "--register-commands");
  const bool use_etf = has_arg(argc, argv, "--use-etf");
  const bool compressed = has_arg(argc, argv, "--compressed");
  const int pool_threads = int_arg(argc, argv, "--pool-threads", 1);

  if (token.empty()) {
    std::cerr << "DISCORD_BOT_TOKEN or --token is required\n";
    return 2;
  }

  log_line("Directioner standalone DPP runtime");
  log_line(std::string("DPP version: ") + DPP_VERSION_TEXT);
  std::cerr << "Mode: compressed=" << (compressed ? "true" : "false")
            << " etf=" << (use_etf ? "true" : "false")
            << " register_commands=" << (register_commands ? "true" : "false")
            << " pool_threads=" << pool_threads << "\n";

  dpp::cluster bot(
      token,
      default_intents(),
      0,
      0,
      1,
      compressed,
      dpp::cache_policy::cpol_default,
      pool_threads <= 0 ? 1 : static_cast<std::uint32_t>(pool_threads));

  if (use_etf) {
    bot.set_websocket_protocol(dpp::ws_etf);
  }

  bot.on_log([](const dpp::log_t& event) {
    std::cerr << "[dpp] " << event.message << "\n";
  });

  bot.on_ready([&bot, register_commands](const dpp::ready_t&) {
    std::cerr << "DPP ready as " << bot.me.username << " (" << bot.me.id << ")\n";
    if (register_commands && dpp::run_once<struct directioner_runtime_register_commands>()) {
      bot.global_bulk_command_create({
          dpp::slashcommand("join", "Join your current voice channel.", bot.me.id),
          dpp::slashcommand("leave", "Leave the current voice channel.", bot.me.id),
      });
      log_line("Requested global slash command registration.");
    }
  });

  bot.on_slashcommand([&bot](const dpp::slashcommand_t& event) {
    const auto command_name = event.command.get_command_name();
    if (command_name == "join") {
      auto* guild = dpp::find_guild(event.command.guild_id);
      if (guild == nullptr ||
          !guild->connect_member_voice(bot, event.command.get_issuing_user().id)) {
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

  bot.on_message_create([&bot](const dpp::message_create_t& event) {
    if (event.msg.author.is_bot()) {
      return;
    }
    const std::string bot_id = std::to_string(bot.me.id);
    const std::string mention_plain = "<@" + bot_id + ">";
    const std::string mention_nick = "<@!" + bot_id + ">";
    const bool mentioned = event.msg.content.find(mention_plain) != std::string::npos ||
                           event.msg.content.find(mention_nick) != std::string::npos;
    if (!mentioned) {
      return;
    }
    emit_text_event(event.msg);
  });

  bot.on_voice_ready([](const dpp::voice_ready_t&) {
    log_line("Voice connection ready.");
  });

  bot.on_voice_receive([](const dpp::voice_receive_t& event) {
    std::cerr << "Voice frame user=" << event.user_id << " bytes=" << event.audio_size << "\n";
  });

  std::thread command_thread([&bot]() {
    std::string line;
    while (std::getline(std::cin, line)) {
      const auto parts = split_tabs(line);
      if (parts.empty()) {
        continue;
      }
      if (parts[0] == "STOP") {
        keep_running.store(false, std::memory_order_release);
        break;
      }
      if (parts[0] == "SEND_TEXT" && parts.size() >= 3) {
        try {
          const auto channel_id = static_cast<dpp::snowflake>(std::stoull(parts[1]));
          bot.message_create(dpp::message(channel_id, base64_decode(parts[2])));
        } catch (const std::exception& exc) {
          std::cerr << "Invalid SEND_TEXT command: " << exc.what() << "\n";
        }
      }
    }
  });

  log_line("Starting DPP gateway...");
  bot.start(dpp::st_return);
  log_line("DPP gateway start returned. Press Ctrl+C to stop.");

  const auto start = std::chrono::steady_clock::now();
  while (keep_running.load(std::memory_order_acquire)) {
    if (timeout_seconds > 0) {
      const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
          std::chrono::steady_clock::now() - start);
      if (elapsed.count() >= timeout_seconds) {
        std::cerr << "Timeout reached after " << timeout_seconds << " seconds.\n";
        break;
      }
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(250));
  }

  keep_running.store(false, std::memory_order_release);
  if (command_thread.joinable()) {
    command_thread.detach();
  }
  log_line("Directioner standalone DPP runtime exiting.");
  return 0;
}
