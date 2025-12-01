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
    "gemini-2.5-flash",  # Fallback to verify API key works
]

def test_model(model_name: str) -> dict:
    """Test a specific Gemini model with a simple request."""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print(f"{'='*60}")

    try:
        # Configure model with permissive safety settings
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        model = genai.GenerativeModel(
            model_name=model_name,
            safety_settings=safety_settings
        )

        # Simple arithmetic test to avoid RECITATION
        import random
        num1 = random.randint(10, 99)
        num2 = random.randint(10, 99)
        response = model.generate_content(
            f"Calculate: {num1} + {num2} = ?",
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  # Low temperature for deterministic output
                max_output_tokens=50,
            )
        )

        # Debug: Print full response structure
        print(f"Response candidates: {len(response.candidates)}")
        if response.candidates:
            candidate = response.candidates[0]
            # Map finish reason enum to readable name
            finish_reasons = {
                0: "FINISH_REASON_UNSPECIFIED",
                1: "STOP",
                2: "RECITATION",
                3: "SAFETY",
                4: "MAX_TOKENS",
                5: "OTHER"
            }
            finish_reason_name = finish_reasons.get(candidate.finish_reason, f"UNKNOWN({candidate.finish_reason})")
            print(f"Finish reason: {finish_reason_name}")
            print(f"Safety ratings: {candidate.safety_ratings}")
            print(f"Parts: {candidate.content.parts if hasattr(candidate, 'content') else 'N/A'}")

        # Try to get text from parts directly
        response_text = None
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                # Try to extract text from parts
                text_parts = [part.text for part in candidate.content.parts if hasattr(part, 'text')]
                if text_parts:
                    response_text = "".join(text_parts).strip()

        # Check if we got valid text
        expected_answer = num1 + num2
        if response_text and str(expected_answer) in response_text:
            result = {
                "model": model_name,
                "status": "✅ WORKING",
                "response": response_text,
                "error": None
            }
            print(f"Status: ✅ WORKING")
            print(f"Response: {response_text}")
            return result
        elif response_text:
            # Got text but wrong answer - still means model is accessible
            result = {
                "model": model_name,
                "status": "✅ ACCESSIBLE",
                "response": response_text,
                "error": None
            }
            print(f"Status: ✅ ACCESSIBLE (got response)")
            print(f"Response: {response_text}")
            return result
        else:
            # No valid text - check why
            error_details = []
            if response.candidates:
                candidate = response.candidates[0]
                finish_reasons = {
                    0: "FINISH_REASON_UNSPECIFIED",
                    1: "STOP",
                    2: "RECITATION",
                    3: "SAFETY",
                    4: "MAX_TOKENS",
                    5: "OTHER"
                }
                finish_reason_name = finish_reasons.get(candidate.finish_reason, f"UNKNOWN({candidate.finish_reason})")
                error_details.append(f"Finish reason: {finish_reason_name}")
                if candidate.safety_ratings:
                    blocked = [sr for sr in candidate.safety_ratings if sr.blocked]
                    if blocked:
                        error_details.append(f"Blocked by safety: {blocked}")

            error_msg = "; ".join(error_details) if error_details else "No text in response"
            raise Exception(error_msg)

    except Exception as e:
        error_msg = str(e)

        # Check for specific error types
        if "429" in error_msg or "quota" in error_msg.lower() or "RESOURCE_EXHAUSTED" in error_msg:
            status = "❌ QUOTA EXCEEDED (Free tier or no subscription)"
        elif "404" in error_msg or "NOT_FOUND" in error_msg:
            status = "❌ MODEL NOT FOUND"
        elif "403" in error_msg or "PERMISSION_DENIED" in error_msg:
            status = "❌ FORBIDDEN (Check API key permissions)"
        elif "RECITATION" in error_msg:
            status = "❌ RECITATION (Response blocked due to training data match)"
        elif "Finish reason" in error_msg:
            status = f"❌ {error_msg}"
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
    elif any("gemini-3-pro" in r["model"] and "RECITATION" in r["status"] for r in results):
        print("\n⚠️  Gemini 3 Pro responded but with RECITATION blocking.")
        print("\nThis actually means you HAVE ACCESS to the model!")
        print("RECITATION occurs when the model's response too closely matches training data.")
        print("\nThis test failure is a FALSE POSITIVE - your API key has access.")
        print("\nTo confirm, you can:")
        print("  1. Try running your actual analysis script")
        print("  2. Use a different test prompt (this script now uses a better one)")
        print("  3. Re-run this test")
        print(f"\n💡 You should be able to use: gemini-3-pro-preview")
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
