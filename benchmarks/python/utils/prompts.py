"""Sample prompts for vLLM benchmarking

This module provides categorized prompts of different lengths for realistic testing.
"""

import random
from typing import List


# Short prompts (50-100 tokens)
SHORT_PROMPTS = [
    "Explain quantum computing in one sentence:",
    "What is Python?",
    "How does machine learning work?",
    "Define artificial intelligence.",
    "What are neural networks?",
    "Explain the concept of recursion in programming.",
    "What is cloud computing?",
    "How do databases work?",
    "What is the difference between AI and ML?",
    "Explain what an API is.",
]

# Medium prompts (200-500 tokens)
MEDIUM_PROMPTS = [
    """Write a detailed explanation of how neural networks work, including the concepts of:
    - Input layers, hidden layers, and output layers
    - Weights and biases
    - Activation functions
    - Backpropagation
    Keep your explanation clear and accessible.""",

    """Explain the differences between supervised learning, unsupervised learning, and reinforcement learning.
    For each type:
    - Provide a definition
    - Give 2-3 examples of real-world applications
    - Describe the key advantages and disadvantages""",

    """Given the following Python code, explain what it does and suggest improvements:
    def process_data(items):
        result = []
        for i in range(len(items)):
            if items[i] > 0:
                result.append(items[i] * 2)
        return result
    """,

    """Describe the software development lifecycle (SDLC) including these phases:
    planning, analysis, design, implementation, testing, deployment, and maintenance.
    For each phase, explain its purpose and key activities.""",

    """Compare and contrast REST APIs and GraphQL APIs. Include:
    - How each works
    - Advantages and disadvantages
    - When to use each
    - Example use cases""",
]

# Long prompts (1000-2000 tokens)
LONG_PROMPTS = [
    """You are conducting a code review of a Python web application. Analyze the following code and provide feedback:

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

    @app.route('/users', methods=['POST'])
    def create_user():
        data = request.json
        db = sqlite3.connect('database.db')
        cursor = db.cursor()
        cursor.execute(
            f"INSERT INTO users (name, email) VALUES ('{data['name']}', '{data['email']}')"
        )
        db.commit()
        db.close()
        return jsonify({'status': 'success'})
    ```

    In your review, please:
    1. Identify security vulnerabilities
    2. Point out potential bugs or error conditions
    3. Suggest improvements for code quality
    4. Recommend best practices that should be followed
    5. Provide example code showing how to fix the most critical issues""",

    """Design a microservices architecture for an e-commerce platform. The platform needs to handle:

    Core Requirements:
    - User authentication and authorization
    - Product catalog with search and filtering
    - Shopping cart functionality
    - Order processing and payment
    - Inventory management
    - Email notifications
    - Analytics and reporting

    For your architecture design, please:
    1. Identify the key microservices and their responsibilities
    2. Describe the data flow between services
    3. Specify which databases or data stores each service should use
    4. Explain how services will communicate (REST, message queues, events, etc.)
    5. Address scalability and fault tolerance considerations
    6. Describe the deployment strategy (containers, orchestration)
    7. Identify potential challenges and how to mitigate them

    Provide specific technology recommendations where appropriate.""",

    """You are debugging a production issue where users are experiencing slow response times. Here is the relevant information:

    Problem Description:
    - Users report that the dashboard loads very slowly (10-15 seconds)
    - The issue started appearing yesterday afternoon
    - It affects about 30% of users
    - No code deployments were made recently
    - Server metrics show CPU at 40%, memory at 60%

    Application Stack:
    - React frontend (SPA)
    - Node.js/Express backend API
    - PostgreSQL database
    - Redis for caching
    - Deployed on AWS (EC2 + RDS)

    Recent Changes:
    - Database migration added 3 new indexes two days ago
    - Marketing campaign started yesterday, bringing 50% more traffic
    - Cache TTL was increased from 5 minutes to 15 minutes

    Database Query:
    ```sql
    SELECT u.*, COUNT(o.id) as order_count, SUM(o.total) as total_spent
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    WHERE u.created_at > NOW() - INTERVAL '90 days'
    GROUP BY u.id
    ORDER BY total_spent DESC
    LIMIT 100
    ```

    Please provide:
    1. Your hypothesis about the root cause
    2. Step-by-step debugging approach
    3. Potential immediate fixes
    4. Long-term solutions to prevent recurrence
    5. Monitoring and alerting improvements""",
]


def get_prompt_by_length(target_tokens: int) -> str:
    """Get a random prompt with approximately target_tokens length

    Args:
        target_tokens: Desired prompt length in tokens (approximate)

    Returns:
        A random prompt from the appropriate category
    """
    if target_tokens < 150:
        return random.choice(SHORT_PROMPTS)
    elif target_tokens < 800:
        return random.choice(MEDIUM_PROMPTS)
    else:
        return random.choice(LONG_PROMPTS)


def get_prompts_for_benchmark(num_prompts: int,
                              distribution: str = "mixed") -> List[str]:
    """Get a list of prompts for benchmarking

    Args:
        num_prompts: Number of prompts to return
        distribution: Prompt distribution strategy
            - "mixed": 40% short, 40% medium, 20% long
            - "short": All short prompts
            - "medium": All medium prompts
            - "long": All long prompts

    Returns:
        List of prompt strings
    """
    prompts = []

    if distribution == "short":
        prompts = [random.choice(SHORT_PROMPTS) for _ in range(num_prompts)]
    elif distribution == "medium":
        prompts = [random.choice(MEDIUM_PROMPTS) for _ in range(num_prompts)]
    elif distribution == "long":
        prompts = [random.choice(LONG_PROMPTS) for _ in range(num_prompts)]
    else:  # mixed
        for _ in range(num_prompts):
            rand = random.random()
            if rand < 0.4:  # 40% short
                prompts.append(random.choice(SHORT_PROMPTS))
            elif rand < 0.8:  # 40% medium
                prompts.append(random.choice(MEDIUM_PROMPTS))
            else:  # 20% long
                prompts.append(random.choice(LONG_PROMPTS))

    return prompts


def generate_code_review_prompt(code_length: str = "medium") -> str:
    """Generate a code review prompt

    Args:
        code_length: Length of code snippet ("short", "medium", "long")

    Returns:
        Code review prompt string
    """
    if code_length == "short":
        return """Review this function and suggest improvements:

        ```python
        def calculate_total(items):
            total = 0
            for item in items:
                total = total + item['price']
            return total
        ```"""

    elif code_length == "long":
        return LONG_PROMPTS[0]  # Use the detailed code review prompt

    else:  # medium
        return """Review this Python class and provide feedback on:
        - Code quality and readability
        - Potential bugs or issues
        - Design patterns and best practices

        ```python
        class UserManager:
            def __init__(self):
                self.users = []

            def add_user(self, name, email):
                self.users.append({'name': name, 'email': email, 'id': len(self.users)})

            def find_user(self, id):
                for user in self.users:
                    if user['id'] == id:
                        return user
                return None

            def delete_user(self, id):
                self.users = [u for u in self.users if u['id'] != id]
        ```"""


def generate_qa_prompt(context_length: str = "medium") -> str:
    """Generate a question-answering prompt with context

    Args:
        context_length: Length of context ("short", "medium", "long")

    Returns:
        Q&A prompt string
    """
    if context_length == "short":
        context = "Python is a high-level programming language known for its simplicity and readability."
        question = "What is Python known for?"

    elif context_length == "long":
        context = """Machine learning is a subset of artificial intelligence that focuses on enabling computers
        to learn from data without being explicitly programmed. There are three main types of machine learning:

        1. Supervised Learning: The algorithm learns from labeled training data. For example, email spam
        detection uses labeled examples of spam and non-spam emails to learn patterns.

        2. Unsupervised Learning: The algorithm finds patterns in unlabeled data. For example, customer
        segmentation in marketing groups similar customers without predefined categories.

        3. Reinforcement Learning: The algorithm learns by interacting with an environment and receiving
        rewards or penalties. For example, game-playing AI learns optimal strategies through trial and error.

        Each type has different applications, advantages, and challenges depending on the problem domain."""
        question = "Explain the three types of machine learning and provide an example for each."

    else:  # medium
        context = """Cloud computing delivers computing services over the internet, including servers, storage,
        databases, networking, and software. The main benefits are cost savings (pay only for what you use),
        scalability (easily increase or decrease resources), and accessibility (access from anywhere).
        The three main types are: Infrastructure as a Service (IaaS), Platform as a Service (PaaS),
        and Software as a Service (SaaS)."""
        question = "What are the benefits of cloud computing and what are the three main service types?"

    return f"""Given the following context, answer the question:

    Context: {context}

    Question: {question}

    Answer:"""


# Export commonly used prompt lists
ALL_PROMPTS = SHORT_PROMPTS + MEDIUM_PROMPTS + LONG_PROMPTS


__all__ = [
    'SHORT_PROMPTS',
    'MEDIUM_PROMPTS',
    'LONG_PROMPTS',
    'ALL_PROMPTS',
    'get_prompt_by_length',
    'get_prompts_for_benchmark',
    'generate_code_review_prompt',
    'generate_qa_prompt',
]
