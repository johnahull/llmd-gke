"""
Locust load testing configuration for vLLM

Run with:
    locust -f locustfile.py --host http://136.116.159.221:8000

Or headless mode:
    locust -f locustfile.py \\
        --host http://136.116.159.221:8000 \\
        --users 50 \\
        --spawn-rate 10 \\
        --run-time 10m \\
        --html results/locust_report.html
"""

from locust import HttpUser, task, between
import random


# Sample prompts categorized by length
SHORT_PROMPTS = [
    "Explain quantum computing in one sentence:",
    "What is Python?",
    "How does machine learning work?",
    "Define artificial intelligence.",
    "What are neural networks?",
]

MEDIUM_PROMPTS = [
    "Write a detailed explanation of how neural networks work, including input layers, hidden layers, output layers, weights, biases, and activation functions.",
    "Explain the differences between supervised learning, unsupervised learning, and reinforcement learning with examples.",
    "Compare and contrast REST APIs and GraphQL APIs, including when to use each.",
]

LONG_PROMPTS = [
    """Given the following Python code, provide a detailed code review:

    ```python
    from flask import Flask, request, jsonify
    import sqlite3

    app = Flask(__name__)

    @app.route('/users/<id>')
    def get_user(id):
        db = sqlite3.connect('database.db')
        cursor = db.cursor()
        query = f"SELECT * FROM users WHERE id = {id}"
        result = cursor.execute(query).fetchone()
        db.close()
        return jsonify(result)
    ```

    Please identify security vulnerabilities, potential bugs, and suggest improvements.""",
]


class VLLMUser(HttpUser):
    """Simulates a user making requests to vLLM API

    Implements realistic usage patterns with mixed prompt sizes
    and appropriate think time between requests.
    """

    # Wait 1-5 seconds between requests (simulates user think time)
    wait_time = between(1, 5)

    # Model to use for all requests
    model = "google/gemma-2b-it"

    @task(4)  # 40% of requests - short prompts
    def short_completion(self):
        """Short completion request (50-100 token prompts)"""
        prompt = random.choice(SHORT_PROMPTS)
        max_tokens = random.randint(50, 100)

        with self.client.post(
            "/v1/completions",
            json={
                "model": self.model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.7
            },
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        response.success()
                    else:
                        response.failure("No choices in response")
                except Exception as e:
                    response.failure(f"Failed to parse JSON: {e}")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(4)  # 40% of requests - medium prompts
    def medium_completion(self):
        """Medium completion request (200-500 token prompts)"""
        prompt = random.choice(MEDIUM_PROMPTS)
        max_tokens = random.randint(100, 200)

        with self.client.post(
            "/v1/completions",
            json={
                "model": self.model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.7
            },
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "choices" in data:
                        response.success()
                    else:
                        response.failure("Invalid response format")
                except:
                    response.failure("JSON parse error")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(2)  # 20% of requests - long prompts
    def long_completion(self):
        """Long completion request (1000-2000 token prompts)"""
        prompt = random.choice(LONG_PROMPTS)
        max_tokens = random.randint(200, 500)

        with self.client.post(
            "/v1/completions",
            json={
                "model": self.model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.7
            },
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "choices" in data:
                        response.success()
                    else:
                        response.failure("No choices in response")
                except:
                    response.failure("JSON parse error")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)  # 10% of requests - chat completions
    def chat_completion(self):
        """Chat completion request"""
        messages = [
            {"role": "user", "content": random.choice(SHORT_PROMPTS)}
        ]

        with self.client.post(
            "/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": 100,
                "temperature": 0.7
            },
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "choices" in data:
                        response.success()
                    else:
                        response.failure("Invalid response")
                except:
                    response.failure("JSON parse error")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)  # 10% of requests - health check
    def health_check(self):
        """Health check endpoint"""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: HTTP {response.status_code}")


# Configuration for different load profiles
class LightLoadUser(VLLMUser):
    """Light load profile - fewer requests, longer wait times"""
    wait_time = between(3, 8)


class HeavyLoadUser(VLLMUser):
    """Heavy load profile - more requests, shorter wait times"""
    wait_time = between(0.5, 2)
