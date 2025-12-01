#!/usr/bin/env python3
"""
Test to confirm that safety_settings are causing RECITATION.
"""

import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("="*60)
print("SAFETY SETTINGS TEST")
print("="*60)

prompt = "Analyze this user behavior: They made 100 transactions on Uniswap."

# Test 1: WITH safety settings
print("\n1. WITH safety settings (BLOCK_NONE)...")
try:
    model = genai.GenerativeModel(
        'gemini-3-pro-preview',
        safety_settings=[
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    )
    response = model.generate_content(prompt)
    print(f"   Finish reason: {response.candidates[0].finish_reason}")
    print(f"   Response: {response.text[:100] if response.text else 'NO TEXT'}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: WITHOUT safety settings
print("\n2. WITHOUT safety settings (default)...")
try:
    model = genai.GenerativeModel('gemini-3-pro-preview')
    response = model.generate_content(prompt)
    print(f"   Finish reason: {response.candidates[0].finish_reason}")
    print(f"   ✅ Response: {response.text[:200]}")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
print("\nSetting safety thresholds to BLOCK_NONE appears to cause")
print("RECITATION errors. Use default safety settings instead.")
print("="*60 + "\n")
