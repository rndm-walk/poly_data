#!/usr/bin/env python3
"""
Test Gemini 3 Pro with actual protocol analysis use case.
"""

import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY not found")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# Sample transaction data similar to what you'll analyze
sample_data = {
    "wallet": "0x123abc",
    "protocols": ["Uniswap", "Aave", "Compound"],
    "transaction_count": 150,
    "total_volume_usd": 50000
}

def test_model_with_real_prompt(model_name: str):
    print(f"\n{'='*60}")
    print(f"Testing {model_name} with real analysis prompt")
    print(f"{'='*60}\n")

    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )

        prompt = f"""Analyze this DeFi user's activity:

Wallet: {sample_data['wallet']}
Protocols used: {', '.join(sample_data['protocols'])}
Total transactions: {sample_data['transaction_count']}
Total volume: ${sample_data['total_volume_usd']:,}

Based on this data, write a 2-sentence summary of this user's behavior pattern."""

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=1.0,
                max_output_tokens=200,
            )
        )

        # Extract response text
        response_text = None
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]

            # Print debug info
            finish_reasons = {
                0: "UNSPECIFIED", 1: "STOP", 2: "RECITATION",
                3: "SAFETY", 4: "MAX_TOKENS", 5: "OTHER"
            }
            finish_reason = finish_reasons.get(candidate.finish_reason, f"UNKNOWN({candidate.finish_reason})")
            print(f"Finish reason: {finish_reason}")

            if hasattr(candidate, 'content') and candidate.content.parts:
                text_parts = [part.text for part in candidate.content.parts if hasattr(part, 'text')]
                if text_parts:
                    response_text = "".join(text_parts).strip()

        if response_text:
            print(f"✅ SUCCESS!\n")
            print(f"Response:\n{response_text}\n")
            return True
        else:
            print(f"❌ No response text generated")
            return False

    except Exception as e:
        print(f"❌ ERROR: {str(e)}\n")

        # Check error type
        error_str = str(e)
        if "404" in error_str or "NOT_FOUND" in error_str:
            print("This model is NOT available with your API key.")
        elif "403" in error_str or "PERMISSION_DENIED" in error_str:
            print("You don't have permission to access this model.")
        elif "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            print("Quota exceeded or billing not enabled.")
        else:
            print(f"Unexpected error: {error_str[:200]}")
        return False

print("\n" + "="*60)
print("REAL USE CASE TEST")
print("="*60)

print("\nThis tests Gemini models with the actual protocol analysis prompt")
print("that you'll be using in your scripts.\n")

models_to_test = ["gemini-3-pro-preview", "gemini-2.5-flash"]

results = {}
for model_name in models_to_test:
    results[model_name] = test_model_with_real_prompt(model_name)

print("="*60)
print("RESULTS")
print("="*60)
for model, success in results.items():
    status = "✅ WORKING" if success else "❌ FAILED"
    print(f"{model}: {status}")

if results.get("gemini-3-pro-preview"):
    print("\n🎉 Gemini 3 Pro is working! You can use it for analysis.")
else:
    print("\n⚠️  Gemini 3 Pro didn't work with this test.")
    if results.get("gemini-2.5-flash"):
        print("You can use gemini-2.5-flash instead.")

print("\n" + "="*60 + "\n")
