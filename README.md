# Directioner

A production-ready Discord text AI assistant built with Python and Rust. Directioner provides conversational AI capabilities for Discord servers with enterprise-grade scaling, monitoring, and reliability.

## ✨ Features

### Core Features
- **Text Chat AI**: Respond to Discord messages with LLM-powered responses
- **Conversation Memory**: Maintains context across conversations with semantic search
- **Tool Integration**: Built-in tools for calculator, web search, and file operations
- **Rust-Powered Native Layer**: Fast native extensions via PyO3

### Enterprise-Grade Scaling
- **Per-Guild/Channel/User Isolation**: Complete data isolation between Discord entities
- **Rate Limiting**: Per-user (60/min), per-channel (300/min), per-guild (1000/min)
- **Auto-Cleanup**: Idle conversations auto-evict after 1 hour
- **100K+ Concurrent Conversations**: Designed for massive Discord servers

### Production Ready
- **Health Checks**: Comprehensive system health monitoring
- **Prometheus Metrics**: Full observability with Prometheus/Grafana integration
- **Circuit Breakers**: Graceful degradation under load
- **Response Caching**: LRU cache with TTL for fast responses
- **Write-Ahead Logging**: Crash recovery and durability

### Security
- **Input Validation**: Discord ID format validation
- **Content Sanitization**: XSS/injection prevention
- **Rate Limiting**: Spam and abuse protection
- **Safe Tool Execution**: Sandboxed file operations

## Architecture

```
Discord -> Gateway -> Conversation Router -> Memory Store -> LLM Client -> Response Router -> Discord
                |              |                  |              |
                v              v                  v              v
           Rate Limit    State Manager      PostgreSQL     Circuit Breaker
           Security      Per-guild/channel  (Supabase)    Retry Logic
```

## Quick Start

```bash
# Linux/macOS - One command to setup and run
./run.sh setup && ./run.sh check

# Windows or Python - Alternative
python run.py setup && python run.py check
```

## Single-Command Usage

```bash
# Setup - Build Rust extension, install dependencies
./run.sh setup        # or: python run.py setup

# Verify configuration
./run.sh check        # or: python run.py check

# Comprehensive health check
./run.sh health       # or: python run.py health

# Run tests (133 tests)
./run.sh test        # or: python run.py test

# Start the bot
./run.sh run          # or: python run.py run

# Clean build artifacts
./run.sh clean        # or: python run.py clean

# Help
./run.sh help         # or: python run.py
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Required
DISCORD_BOT_TOKEN=your_discord_bot_token

# Optional - for better AI responses
DIRECTIONER_LLM_PROVIDER=groq
DIRECTIONER_LLM_API_KEY=your_groq_api_key

# Optional - for distributed deployments
DIRECTIONER_MEMORY_USE_SUPABASE=true
DIRECTIONER_SUPABASE_URL=https://your-project.supabase.co
```

## Project Structure

```
directioner/
├── run.sh              # Bash runner (Linux/macOS)
├── run.py              # Python runner (cross-platform)
├── Dockerfile          # Production Docker image
├── docker-compose.yml  # Local development with monitoring
├── .env.example        # Environment template
├── src/directioner/    # Python source code
│   ├── app.py          # CLI entry point
│   ├── security/        # Security hardening
│   ├── database/        # Supabase client + pooling
│   ├── conversation/    # Conversation management
│   ├── llm/            # LLM client with caching
│   ├── memory/          # Memory store + rate limiting
│   ├── monitoring/      # Metrics + performance
│   └── tools/           # Built-in tools
├── k8s/                # Kubernetes manifests
├── configs/            # Configuration files
│   ├── prometheus.yml   # Prometheus config
│   └── grafana/        # Grafana dashboards
└── tests/              # Test suite (133 tests)
    ├── unit/           # Unit tests
    ├── integration/     # Integration tests
    ├── benchmarks/      # Performance benchmarks
    └── load/            # Load tests (Locust)
```

## Built-in Tools

- `calculator` - Safe arithmetic evaluation
- `web_search` - DuckDuckGo web search
- `read_file` / `list_directory` - File exploration (sandboxed)
- `switch_persona` / `list_personas` - Bot persona management

## Scaling Capabilities

| Metric | Value |
|--------|-------|
| Max Concurrent Conversations | 100,000 |
| Max per Guild | 10,000 |
| Max per Channel | 1,000 |
| User Rate Limit | 60 req/min |
| Channel Rate Limit | 300 req/min |
| Guild Rate Limit | 1000 req/min |
| Idle Timeout | 1 hour |

## Deployment

### Docker
```bash
docker build -t directioner:latest .
docker-compose up -d
```

### Kubernetes
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/deployment.yaml
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full deployment guide.

## Monitoring

### Health Check Output

```json
{
  "status": "ok",
  "checks": {
    "configuration": { "ok": true },
    "native_extension": { "ok": true },
    "llm_provider": { "ok": true, "cache": { "cache_size": 0 } },
    "memory": {
      "ok": true,
      "rate_limiting": {
        "user": { "max_requests": 60 },
        "channel": { "max_requests": 300 },
        "guild": { "max_requests": 1000 }
      }
    },
    "tools": { "ok": true, "count": 6 },
    "performance": { "ok": true },
    "database": { "ok": true }
  }
}
```

### Prometheus Metrics

Key metrics:
- `directioner_requests_total` - Total requests by guild/channel
- `directioner_request_latency_seconds` - Request latency histogram
- `directioner_active_conversations` - Active conversation count
- `directioner_llm_latency_seconds` - LLM API latency
- `directioner_rate_limit_hits_total` - Rate limit violations
- `directioner_cache_hits_total` - Cache hit rate

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run benchmarks
pytest tests/benchmarks/ -v

# Load testing
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Lint
ruff check src/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

- GitHub Issues: https://github.com/aditya-munday/Directioner/issues
- Discord: Join the support server

