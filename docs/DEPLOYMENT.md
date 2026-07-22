# Directioner Deployment Guide

This guide covers deploying Directioner to production with Docker and Kubernetes.

## Prerequisites

- Docker 20.10+ or Kubernetes 1.24+
- Discord bot token (from [Discord Developer Portal](https://discord.com/developers/applications))
- (Optional) LLM API key (Groq, OpenAI, etc.)
- (Optional) Supabase project for distributed storage

## Quick Start with Docker

### 1. Clone and Configure

```bash
git clone https://github.com/aditya-munday/Directioner.git
cd Directioner
cp .env.example .env
```

### 2. Edit .env

```bash
# Required
DISCORD_BOT_TOKEN=your_bot_token_here

# Optional - for better AI responses
DIRECTIONER_LLM_PROVIDER=groq
DIRECTIONER_LLM_API_KEY=your_groq_api_key

# Optional - for distributed deployments
DIRECTIONER_MEMORY_USE_SUPABASE=true
DIRECTIONER_SUPABASE_URL=https://your-project.supabase.co
DIRECTIONER_SUPABASE_KEY=your_anon_key
```

### 3. Build and Run

```bash
# Build the image
docker build -t directioner:latest .

# Run with docker-compose
docker-compose up -d
```

## Kubernetes Deployment

### 1. Create Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

### 2. Configure Secrets

Create a secret file or use kubectl:

```bash
kubectl create secret generic directioner-secrets \
  --from-literal=discord-bot-token=YOUR_TOKEN \
  --from-literal=discord-application-id=YOUR_APP_ID \
  --from-literal=llm-api-key=YOUR_LLM_KEY \
  --namespace=directioner
```

### 3. Deploy

```bash
kubectl apply -f k8s/service-account.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

### 4. Verify Deployment

```bash
kubectl get pods -n directioner
kubectl logs -n directioner -l app.kubernetes.io/name=directioner
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | - | **Required.** Discord bot token |
| `DISCORD_APPLICATION_ID` | - | Discord application ID |
| `DIRECTIONER_LLM_PROVIDER` | `mock` | LLM provider: `mock`, `groq`, `openai-compatible` |
| `DIRECTIONER_LLM_API_KEY` | - | API key for external LLM providers |
| `DIRECTIONER_LLM_MODEL` | `llama-3.1-70b-versatile` | Model to use |
| `DIRECTIONER_MEMORY_ENABLED` | `true` | Enable memory features |
| `DIRECTIONER_MEMORY_MAX_TURNS` | `200` | Max conversation turns |
| `DIRECTIONER_MEMORY_USE_SUPABASE` | `false` | Use Supabase for storage |
| `DIRECTIONER_RATE_LIMIT_USER` | `60` | Requests per user/minute |
| `DIRECTIONER_RATE_LIMIT_CHANNEL` | `300` | Requests per channel/minute |
| `DIRECTIONER_RATE_LIMIT_GUILD` | `1000` | Requests per guild/minute |
| `DIRECTIONER_MAX_CONVERSATIONS` | `100000` | Max concurrent conversations |
| `DIRECTIONER_LOG_LEVEL` | `INFO` | Log level |

### Kubernetes Resources

#### Horizontal Pod Autoscaler

The deployment includes an HPA that automatically scales pods based on CPU and memory:

```yaml
minReplicas: 2
maxReplicas: 10
metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Monitoring

### Prometheus Metrics

The bot exposes Prometheus metrics at `/metrics` when the HTTP server is enabled.

Key metrics:
- `directioner_requests_total` - Total requests by guild/channel
- `directioner_request_latency_seconds` - Request latency histogram
- `directioner_active_conversations` - Active conversation count
- `directioner_llm_latency_seconds` - LLM API latency
- `directioner_rate_limit_hits_total` - Rate limit violations

### Grafana Dashboard

Import the dashboard from `configs/grafana/provisioning/dashboards/directioner.json`.

## Supabase Setup

### 1. Create Supabase Project

1. Go to [supabase.com](https://supabase.com)
2. Create a new project
3. Note the URL and anon key

### 2. Run Schema

In the Supabase SQL Editor, run `configs/supabase_schema.sql`.

### 3. Configure Environment

```bash
DIRECTIONER_MEMORY_USE_SUPABASE=true
DIRECTIONER_SUPABASE_URL=https://your-project.supabase.co
DIRECTIONER_SUPABASE_KEY=your_anon_key
```

## Scaling

### Horizontal Scaling

The bot is designed for horizontal scaling:

1. **Stateless Design** - Conversations are isolated by ID
2. **Connection Pooling** - Supabase connections are pooled
3. **Rate Limiting** - Per-user, per-channel, per-guild limits
4. **Memory Management** - Automatic cleanup of idle conversations

### Kubernetes Scaling

```bash
# Manual scaling
kubectl scale deployment directioner --replicas=5 -n directioner

# Enable HPA
kubectl autoscale deployment directioner --min=2 --max=10 --cpu-percent=70 -n directioner
```

### Redis (Optional)

For multi-instance deployments with shared state:

```yaml
# docker-compose.yml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
```

## Troubleshooting

### Bot Not Responding

1. Check bot token is valid
2. Verify bot is invited to server with correct permissions
3. Check logs: `kubectl logs -n directioner -l app.kubernetes.io/name=directioner`

### Rate Limited

- Check `directioner_rate_limit_hits_total` metric
- Adjust rate limits in environment
- Consider scaling horizontally

### High Latency

1. Check LLM provider status
2. Enable response caching
3. Scale horizontally for more capacity

### Memory Issues

1. Reduce `DIRECTIONER_MAX_CONVERSATIONS`
2. Lower `DIRECTIONER_IDLE_TIMEOUT`
3. Enable Supabase for persistent storage

## Security

### Best Practices

1. **Secrets Management**: Use Kubernetes secrets or a secrets manager
2. **Network Policies**: Restrict traffic between pods
3. **Resource Limits**: Set CPU/memory limits to prevent resource exhaustion
4. **Rate Limiting**: Adjust limits based on expected traffic
5. **Input Validation**: User content is validated and sanitized

### Discord Permissions

Required bot permissions:
- `Send Messages`
- `Embed Links`
- `Read Message History`

## Backup & Recovery

### Local Storage Backup

```bash
# Create backup
cp ./data/memory/turns.jsonl ./data/memory/turns.jsonl.bak

# Restore
cp ./data/memory/turns.jsonl.bak ./data/memory/turns.jsonl
```

### Supabase

Enable Point-in-Time Recovery (PITR) in Supabase settings.

## Support

- GitHub Issues: https://github.com/aditya-munday/Directioner/issues
- Discord: Join the support server
