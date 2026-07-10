#include <chrono>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>

#include <dpp/dpp.h>
#include <dpp/version.h>

namespace {

std::uint32_t default_intents() {
  return dpp::i_default_intents | dpp::i_guild_voice_states | dpp::i_guild_messages |
         dpp::i_direct_messages | dpp::i_message_content;
}

}  // namespace

int main(int argc, char** argv) {
  const char* token_env = std::getenv("DISCORD_BOT_TOKEN");
  std::string token = token_env == nullptr ? "" : token_env;
  bool start = false;
  int timeout_seconds = 10;

  for (int index = 1; index < argc; ++index) {
    const std::string arg = argv[index];
    if (arg == "--start") {
      start = true;
    } else if (arg == "--timeout" && index + 1 < argc) {
      timeout_seconds = std::stoi(argv[++index]);
    } else if (arg == "--token" && index + 1 < argc) {
      token = argv[++index];
    }
  }

  if (token.empty()) {
    std::cerr << "DISCORD_BOT_TOKEN or --token is required\n";
    return 2;
  }

  std::cout << "DPP probe version: " << DPP_VERSION_TEXT << "\n";
  std::cout << "Constructing dpp::cluster...\n";
  dpp::cluster bot(
      token,
      default_intents(),
      0,
      0,
      1,
      false,
      dpp::cache_policy::cpol_default,
      1);

  bot.on_log([](const dpp::log_t& event) {
    std::cout << "[dpp] " << event.message << "\n";
  });

  std::cout << "Constructed dpp::cluster shards=" << bot.numshards << "\n";
  if (!start) {
    std::cout << "Probe completed without gateway start.\n";
    return 0;
  }

  std::cout << "Starting gateway with st_return...\n";
  bot.start(dpp::st_return);
  std::cout << "Gateway start returned; sleeping for " << timeout_seconds << " seconds.\n";
  std::this_thread::sleep_for(std::chrono::seconds(timeout_seconds));
  std::cout << "Probe timeout reached; exiting.\n";
  return 0;
}

