#!/usr/bin/env python3
"""
Test script to verify intent classification and response quality.
Tests the issues reported by the user:
1. Pricing leakage in non-pricing queries
2. Location errors (Azad Kashmir)
3. Response length (too long)
4. Template output in pricing queries
"""

import os
import sys
import requests
import json
from pathlib import Path

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent / "chatbot"
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

# Try to import intent router for direct testing
try:
    from bot.conversation.intent_router import IntentRouter, IntentType
    from bot.client.groq_client import GroqClient
    INTENT_ROUTER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import intent router: {e}")
    INTENT_ROUTER_AVAILABLE = False

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_ENDPOINT = f"{API_BASE_URL}/api/chat"

# Test cases
TEST_CASES = [
    {
        "name": "General cottage query - should NOT have pricing",
        "query": "tell me about the swiss cottages bhurban",
        "expected_intent": "rooms",  # or "general"
        "should_not_contain": ["PKR", "32,000", "38,000", "price", "pricing", "cost"],
        "should_contain": ["Bhurban", "Pakistan"],
        "should_not_contain_location": ["Azad Kashmir", "Patriata", "PC Bhurban"],
        "max_sentences": 6,
    },
    {
        "name": "Which cottage is best - should NOT have pricing",
        "query": "which cottage is best in your collections",
        "expected_intent": "rooms",
        "should_not_contain": ["PKR", "32,000", "38,000", "price", "pricing", "cost"],
        "should_contain": ["cottage"],
        "max_sentences": 6,
    },
    {
        "name": "Cottage 9 description - should NOT have pricing",
        "query": "tell me about cottage 9",
        "expected_intent": "rooms",
        "should_not_contain": ["PKR", "32,000", "38,000", "price", "pricing", "cost"],
        "should_contain": ["Cottage 9", "Bhurban", "Pakistan"],
        "should_not_contain_location": ["Azad Kashmir", "Patriata"],
        "max_sentences": 4,
    },
    {
        "name": "Location query - should NOT have pricing, correct location",
        "query": "where is bhurban",
        "expected_intent": "location",
        "should_not_contain": ["PKR", "32,000", "38,000", "price", "pricing", "cost"],
        "should_contain": ["Bhurban", "Pakistan"],
        "should_not_contain_location": ["Azad Kashmir", "Patriata"],
        "max_sentences": 4,
    },
    {
        "name": "Nearby attractions - should NOT have pricing",
        "query": "tell me the nearby attraction",
        "expected_intent": "location",
        "should_not_contain": ["PKR", "32,000", "38,000", "price", "pricing", "cost"],
        "should_contain": ["attraction", "nearby"],
        "max_sentences": 4,
    },
    {
        "name": "Capacity query - should NOT have pricing",
        "query": "we are a family of 5 can we stay in cottage 9",
        "expected_intent": "rooms",  # or "availability"
        "should_not_contain": ["PKR", "32,000", "38,000", "price", "pricing", "cost"],
        "should_contain": ["Cottage 9", "5", "guests", "family"],
        "max_sentences": 4,
    },
    {
        "name": "Pricing query - should have pricing, NO template output",
        "query": "tell me the pricing of cottage 9",
        "expected_intent": "pricing",
        "should_contain": ["PKR", "price", "pricing", "cost"],
        "should_not_contain": [
            "🚨 CRITICAL PRICING INFORMATION",
            "STRUCTURED PRICING ANALYSIS",
            "⚠️ MANDATORY INSTRUCTIONS FOR LLM",
            "USE ONLY THIS DATA",
            "DO NOT USE DOLLAR PRICES",
        ],
        "max_sentences": 5,
    },
    {
        "name": "Safety query - should NOT have pricing",
        "query": "is this cottage 9 is secure",
        "expected_intent": "safety",
        "should_not_contain": ["PKR", "32,000", "38,000", "price", "pricing", "cost"],
        "should_contain": ["secure", "safe", "security"],
        "max_sentences": 4,
    },
]


def test_intent_classification_direct(query: str) -> str:
    """Test intent classification directly using IntentRouter."""
    if not INTENT_ROUTER_AVAILABLE:
        return "unknown"
    
    try:
        # Initialize intent router with LLM (optional)
        groq_api_key = os.getenv("GROQ_API_KEY")
        if groq_api_key:
            llm = GroqClient(api_key=groq_api_key, model_name="llama-3.1-8b-instant")
            router = IntentRouter(llm=llm, use_llm_fallback=True)
        else:
            router = IntentRouter(llm=None, use_llm_fallback=False)
        
        intent = router.classify(query)
        return intent.value if intent else "unknown"
    except Exception as e:
        print(f"Error in direct intent classification: {e}")
        return "error"


def test_api_query(query: str, session_id: str = "test_session") -> dict:
    """Test a query via the API."""
    try:
        response = requests.post(
            API_ENDPOINT,
            json={
                "question": query,
                "session_id": session_id,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e), "answer": None, "intent": None}


def count_sentences(text: str) -> int:
    """Count sentences in text."""
    if not text:
        return 0
    # Simple sentence counting
    sentences = text.replace("!", ".").replace("?", ".").split(".")
    return len([s for s in sentences if s.strip()])


def check_contains(text: str, items: list, case_sensitive: bool = False) -> list:
    """Check if text contains any of the items. Returns list of found items."""
    if not text:
        return []
    text_check = text if case_sensitive else text.upper()
    found = []
    for item in items:
        item_check = item if case_sensitive else item.upper()
        if item_check in text_check:
            found.append(item)
    return found


def run_test(test_case: dict, test_number: int) -> dict:
    """Run a single test case."""
    print(f"\n{'='*80}")
    print(f"Test {test_number}: {test_case['name']}")
    print(f"{'='*80}")
    print(f"Query: {test_case['query']}")
    print(f"Expected Intent: {test_case['expected_intent']}")
    
    results = {
        "test_name": test_case["name"],
        "query": test_case["query"],
        "expected_intent": test_case["expected_intent"],
        "passed": True,
        "issues": [],
    }
    
    # Test intent classification directly
    if INTENT_ROUTER_AVAILABLE:
        detected_intent = test_intent_classification_direct(test_case["query"])
        print(f"Detected Intent (direct): {detected_intent}")
        results["detected_intent_direct"] = detected_intent
        if detected_intent != test_case["expected_intent"]:
            results["issues"].append(
                f"Intent mismatch: expected {test_case['expected_intent']}, got {detected_intent}"
            )
    
    # Test via API
    api_result = test_api_query(test_case["query"])
    
    if "error" in api_result:
        print(f"❌ API Error: {api_result['error']}")
        results["passed"] = False
        results["issues"].append(f"API Error: {api_result['error']}")
        return results
    
    answer = api_result.get("answer", "")
    intent = api_result.get("intent", "unknown")
    
    print(f"Detected Intent (API): {intent}")
    results["detected_intent_api"] = intent
    
    if not answer:
        print("❌ No answer returned")
        results["passed"] = False
        results["issues"].append("No answer returned")
        return results
    
    print(f"\nAnswer ({len(answer)} chars):")
    print("-" * 80)
    print(answer)
    print("-" * 80)
    
    # Check for forbidden content
    if "should_not_contain" in test_case:
        found_forbidden = check_contains(answer, test_case["should_not_contain"])
        if found_forbidden:
            print(f"❌ Found forbidden content: {found_forbidden}")
            results["passed"] = False
            results["issues"].append(f"Found forbidden content: {found_forbidden}")
        else:
            print(f"✅ No forbidden content found")
    
    # Check for required content
    if "should_contain" in test_case:
        found_required = check_contains(answer, test_case["should_contain"])
        if found_required:
            print(f"✅ Found required content: {found_required}")
        else:
            print(f"⚠️  Missing some required content. Expected: {test_case['should_contain']}")
            results["issues"].append(f"Missing required content: {test_case['should_contain']}")
    
    # Check location errors
    if "should_not_contain_location" in test_case:
        found_location_errors = check_contains(answer, test_case["should_not_contain_location"])
        if found_location_errors:
            print(f"❌ Found location errors: {found_location_errors}")
            results["passed"] = False
            results["issues"].append(f"Location errors: {found_location_errors}")
        else:
            print(f"✅ No location errors")
    
    # Check response length
    sentence_count = count_sentences(answer)
    max_sentences = test_case.get("max_sentences", 10)
    print(f"Sentence count: {sentence_count} (max: {max_sentences})")
    if sentence_count > max_sentences:
        print(f"⚠️  Response too long: {sentence_count} sentences (max: {max_sentences})")
        results["issues"].append(f"Response too long: {sentence_count} sentences (max: {max_sentences})")
    else:
        print(f"✅ Response length OK")
    
    # Check for template output
    template_indicators = [
        "🚨 CRITICAL PRICING INFORMATION",
        "STRUCTURED PRICING ANALYSIS",
        "⚠️ MANDATORY INSTRUCTIONS FOR LLM",
        "USE ONLY THIS DATA",
    ]
    found_templates = check_contains(answer, template_indicators)
    if found_templates:
        print(f"❌ Found template output: {found_templates}")
        results["passed"] = False
        results["issues"].append(f"Template output found: {found_templates}")
    else:
        print(f"✅ No template output")
    
    if results["passed"] and len(results["issues"]) == 0:
        print(f"\n✅ Test PASSED")
    else:
        print(f"\n❌ Test FAILED")
        for issue in results["issues"]:
            print(f"  - {issue}")
    
    results["answer"] = answer
    results["sentence_count"] = sentence_count
    
    return results


def main():
    """Run all tests."""
    print("=" * 80)
    print("INTENT CLASSIFICATION AND RESPONSE QUALITY TEST")
    print("=" * 80)
    print(f"API Endpoint: {API_ENDPOINT}")
    print(f"Intent Router Available: {INTENT_ROUTER_AVAILABLE}")
    print()
    
    # Check if API is accessible
    try:
        health_response = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ API is accessible")
        else:
            print(f"⚠️  API returned status {health_response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to API: {e}")
        print("Make sure the API server is running on", API_BASE_URL)
        return
    
    all_results = []
    
    for i, test_case in enumerate(TEST_CASES, 1):
        result = run_test(test_case, i)
        all_results.append(result)
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for r in all_results if r["passed"] and len(r["issues"]) == 0)
    failed = len(all_results) - passed
    
    print(f"Total Tests: {len(all_results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed > 0:
        print("\nFailed Tests:")
        for result in all_results:
            if not result["passed"] or len(result["issues"]) > 0:
                print(f"  - {result['test_name']}")
                for issue in result["issues"]:
                    print(f"    • {issue}")
    
    # Save results to file
    results_file = Path(__file__).parent / "test_results.json"
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    main()
