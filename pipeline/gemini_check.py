#!/usr/bin/env python3
"""Smoke test: one Gemini call from Python through Application Default Credentials."""
from google import genai

client = genai.Client(vertexai=True, project="panopticon-hackathon", location="us-central1")
resp = client.models.generate_content(model="gemini-2.5-flash", contents="Reply with the single word: ready")
print(resp.text.strip(), "| tokens:", resp.usage_metadata.total_token_count)
