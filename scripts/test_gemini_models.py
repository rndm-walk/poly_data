#!/usr/bin/env python3
"""
Test Gemini API models to check which ones are available with your subscription.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY not found in .env file")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# Models to test
MODELS_TO_TEST = [
    "gemini-3-pro-preview",
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash-exp",
]

def test_model(model_name: str) -> dict:
    """Test a specific Gemini model with a simple request."""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print(f"{'='*60}")

    try:
        model = genai.GenerativeModel(model_name)

        # Simple test prompt
        response = model.generate_content(
            "What is 2+2? Answer in one word.",
            generation_config=genai.types.GenerationConfig(
                temperature=0,
                max_output_tokens=10,
            )
        )

        result = {
            "model": model_name,
            "status": "✅ WORKING",
            "response": response.text.strip(),
            "error": None
        }

        print(f"Status: ✅ WORKING")
        print(f"Response: {response.text.strip()}")

        return result

    except Exception as e:
        error_msg = str(e)

        # Check for specific error types
        if "429" in error_msg and "quota" in error_msg.lower():
            status = "❌ QUOTA EXCEEDED (Free tier or no subscription)"
        elif "404" in error_msg:
            status = "❌ MODEL NOT FOUND"
        elif "403" in error_msg:
            status = "❌ FORBIDDEN (Check API key permissions)"
        else:
            status = f"❌ ERROR: {error_msg[:50]}"

        result = {
            "model": model_name,
            "status": status,
            "response": None,
            "error": error_msg
        }

        print(f"Status: {status}")
        if len(error_msg) > 100:
            print(f"Error: {error_msg[:200]}...")
        else:
            print(f"Error: {error_msg}")

        return result


def main():
    print("\n" + "="*60)
    print("GEMINI API MODEL TESTER")
    print("="*60)
    print(f"\nAPI Key: {GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-4:]}")
    print(f"Testing {len(MODELS_TO_TEST)} models...")

    results = []
    for model_name in MODELS_TO_TEST:
        result = test_model(model_name)
        results.append(result)

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    working_models = [r for r in results if "WORKING" in r["status"]]
    failed_models = [r for r in results if "WORKING" not in r["status"]]

    print(f"\n✅ Working Models ({len(working_models)}):")
    for r in working_models:
        print(f"   - {r['model']}")

    print(f"\n❌ Failed Models ({len(failed_models)}):")
    for r in failed_models:
        print(f"   - {r['model']}: {r['status']}")

    # Recommendation
    print("\n" + "="*60)
    print("RECOMMENDATION")
    print("="*60)

    if any("gemini-3-pro" in r["model"] and "WORKING" in r["status"] for r in results):
        print("\n🎉 Gemini 3 Pro is READY! You can use it in the analysis script.")
        print("\nTo enable Gemini 3 Pro, update line 50 in:")
        print("  scripts/analyze_parlay_user_protocols.py")
        print("\nChange from:")
        print('  def __init__(self, data_dir: Path, model_name: str = "gemini-2.5-flash"):')
        print("To:")
        print('  def __init__(self, data_dir: Path, model_name: str = "gemini-3-pro-preview"):')
    elif working_models:
        best_model = working_models[0]["model"]
        print(f"\n💡 Best available model: {best_model}")
        print(f"\nCurrent script uses: gemini-2.5-flash")
        if best_model != "gemini-2.5-flash":
            print(f"Consider switching to: {best_model}")
    else:
        print("\n⚠️  No models are working. Possible issues:")
        print("  1. API key may be invalid")
        print("  2. Subscription not yet activated")
        print("  3. Billing not configured")
        print("\nCheck:")
        print("  - https://ai.google.dev/gemini-api/docs/billing")
        print("  - https://aistudio.google.com/app/apikey")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    main()
