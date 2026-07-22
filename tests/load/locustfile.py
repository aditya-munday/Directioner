"""Load testing for Directioner using Locust.

Run with:
    locust -f tests/load/locustfile.py --host=http://localhost:8000

For distributed testing:
    locust -f tests/load/locustfile.py --master
    locust -f tests/load/locustfile.py --worker --master-host=<master-ip>
"""

from __future__ import annotations

import random
import string
from typing import Any

from locust import (
    HttpUser,
    task,
    between,
    events,
    stats as locust_stats,
)
import json


def random_id(length: int = 18) -> str:
    """Generate a random Discord-style ID."""
    return ''.join(random.choices(string.digits, k=length))


def random_username() -> str:
    """Generate a random username."""
    return ''.join(random.choices(string.ascii_lowercase, k=10))


class DirectionerUser(HttpUser):
    """Simulates a Discord user interacting with Directioner."""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    weight = 10  # Most common user type

    def on_start(self) -> None:
        """Initialize user session."""
        self.guild_id = random_id()
        self.channel_id = random_id()
        self.user_id = random_id()
        self.conversation_id = f"{self.guild_id}-{self.channel_id}"
        
        # Set common headers
        self.client.headers.update({
            "Content-Type": "application/json",
            "X-Guild-ID": self.guild_id,
            "X-Channel-ID": self.channel_id,
        })

    @task(5)
    def send_message(self) -> None:
        """Send a chat message to the bot."""
        messages = [
            "Hello! How are you?",
            "What's the weather like?",
            "Can you help me with math? 2 + 2 = ?",
            "Tell me a joke",
            "What time is it?",
            "Thanks for your help!",
            "Hello there!",
            "What's new?",
            "How does this work?",
            "Nice bot!",
        ]
        
        payload = {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "content": random.choice(messages),
            "message_id": random_id(),
        }
        
        with self.client.post(
            "/api/message",
            json=payload,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Failed with {response.status_code}")

    @task(3)
    def health_check(self) -> None:
        """Check bot health."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") == "ok":
                        response.success()
                    else:
                        response.failure("Health check returned non-ok status")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(2)
    def switch_persona(self) -> None:
        """Switch bot persona."""
        personas = ["default", "interviewer", "coder", "helper"]
        payload = {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "persona": random.choice(personas),
        }
        
        with self.client.post(
            "/api/persona/switch",
            json=payload,
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                response.success()
            else:
                response.failure(f"Persona switch failed: {response.status_code}")

    @task(1)
    def list_personas(self) -> None:
        """List available personas."""
        with self.client.get(
            "/api/personas",
            params={"guild_id": self.guild_id},
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"List personas failed: {response.status_code}")

    @task(1)
    def get_metrics(self) -> None:
        """Get bot metrics."""
        with self.client.get("/metrics", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics failed: {response.status_code}")


class HighVolumeUser(HttpUser):
    """Simulates a power user sending many messages."""
    
    wait_time = between(0.1, 0.5)  # Very fast
    weight = 1  # Rare

    def on_start(self) -> None:
        """Initialize session."""
        self.guild_id = random_id()
        self.channel_id = random_id()
        self.user_id = random_id()
        self.conversation_id = f"{self.guild_id}-{self.channel_id}"

    @task
    def rapid_messages(self) -> None:
        """Send rapid-fire messages."""
        payload = {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "content": "Quick question!",
            "message_id": random_id(),
        }
        
        with self.client.post(
            "/api/message",
            json=payload,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited (expected)")
            else:
                response.failure(f"Failed: {response.status_code}")


class AdminUser(HttpUser):
    """Simulates an admin user performing management tasks."""
    
    wait_time = between(5, 10)  # Slow, deliberate actions
    weight = 1

    def on_start(self) -> None:
        """Initialize admin session."""
        self.guild_id = random_id()
        self.admin_user_id = random_id()

    @task(3)
    def get_stats(self) -> None:
        """Get bot statistics."""
        with self.client.get(
            "/api/stats",
            params={"guild_id": self.guild_id},
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Stats failed: {response.status_code}")

    @task(2)
    def list_conversations(self) -> None:
        """List active conversations."""
        with self.client.get(
            "/api/conversations",
            params={"guild_id": self.guild_id},
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"List conversations failed: {response.status_code}")

    @task(1)
    def get_guild_info(self) -> None:
        """Get guild information."""
        with self.client.get(
            "/api/guild",
            params={"guild_id": self.guild_id},
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Guild info failed: {response.status_code}")


# Event handlers for custom reporting
@events.request.add_listener
def on_request(request_type: str, name: str, response_time: float, response_length: int, **kwargs: Any) -> None:
    """Track request metrics."""
    pass


@events.request.add_listener  
def on_request_failure(request_type: str, name: str, response_time: float, exception: Exception, **kwargs: Any) -> None:
    """Track failed requests."""
    pass


# Configure Locust
locust_stats.STATS_NAME_WIDTH = 50
locust_stats.HISTORY_STATS_INTERVAL_SEC = 10
