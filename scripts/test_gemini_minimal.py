#!/usr/bin/env python3
"""
Minimal Gemini API test to diagnose RECITATION issues.
"""

import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

print("="*60)
print("MINIMAL GEMINI TEST")
print("="*60)

# First, list available models
print("\n1. Checking available models...")
try:
    models = genai.list_models()
    gemini_models = [m for m in models if 'gemini' in m.name.lower()]
    print(f"Found {len(gemini_models)} Gemini models:")
    for m in gemini_models[:10]:  # Show first 10
        print(f"   - {m.name}")
        if 'gemini-3' in m.name.lower() or 'gemini-2' in m.name.lower():
            print(f"     Supported methods: {m.supported_generation_methods}")
except Exception as e:
    print(f"Error listing models: {e}")

# Test 1: Absolute minimal prompt with gemini-2.5-flash
print("\n2. Testing gemini-2.5-flash with minimal prompt (NO safety settings)...")
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content("Hello")
    print(f"   Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
    if response.text:
        print(f"   ✅ Response: {response.text[:100]}")
    else:
        print(f"   ❌ No text in response")
        print(f"   Parts: {response.candidates[0].content.parts if response.candidates else 'N/A'}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Same with gemini-3-pro-preview
print("\n3. Testing gemini-3-pro-preview with minimal prompt (NO safety settings)...")
try:
    model = genai.GenerativeModel('gemini-3-pro-preview')
    response = model.generate_content("Hello")
    print(f"   Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
    if response.text:
        print(f"   ✅ Response: {response.text[:100]}")
    else:
        print(f"   ❌ No text in response")
        print(f"   Parts: {response.candidates[0].content.parts if response.candidates else 'N/A'}")
except Exception as e:
    error_str = str(e)
    print(f"   ❌ Error: {e}")
    if "404" in error_str or "not found" in error_str.lower():
        print("   → Model not found (not available on your account)")
    elif "403" in error_str or "permission" in error_str.lower():
        print("   → Permission denied (not authorized)")
    elif "429" in error_str or "quota" in error_str.lower():
        print("   → Quota exceeded (billing issue)")

# Test 3: Try with temperature=0
print("\n4. Testing with temperature=0...")
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(
        "What is 2+2?",
        generation_config=genai.types.GenerationConfig(temperature=0)
    )
    print(f"   Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
    if response.text:
        print(f"   ✅ Response: {response.text[:100]}")
    else:
        print(f"   ❌ No text")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "="*60 + "\n")
