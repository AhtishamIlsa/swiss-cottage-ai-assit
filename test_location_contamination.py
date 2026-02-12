#!/usr/bin/env python3
"""
Automated Test Script for Location Contamination and Chat History Issues

This script tests various scenarios to ensure:
1. Location queries don't get contaminated by chat history
2. Pronoun expansion works correctly
3. Sequential queries don't contaminate each other
4. Forbidden locations (Azad Kashmir, Patriata, Bhubaneswar) don't appear in answers
"""

import requests
import json
import time
import sys
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

# Configuration
API_BASE_URL = "http://localhost:8000"  # Adjust if needed
API_CHAT_ENDPOINT = f"{API_BASE_URL}/api/chat"
API_STREAM_ENDPOINT = f"{API_BASE_URL}/api/chat/stream"

# Forbidden locations that should NEVER appear in location answers
FORBIDDEN_LOCATIONS = [
    "azad kashmir",
    "patriata",
    "bhubaneswar",
    "lahore",
    "karachi",
    "islamabad"
]

# Correct location that SHOULD appear
CORRECT_LOCATION_PATTERNS = [
    "bhurban, murree, pakistan",
    "murree hills, bhurban, pakistan",
    "swiss cottages bhurban, bhurban, murree, pakistan"
]


class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIP = "SKIP"


@dataclass
class TestCase:
    name: str
    description: str
    conversation: List[Tuple[str, str]]  # List of (user_query, expected_keywords)
    expected_behavior: str
    critical: bool = False
    result: Optional[TestResult] = None
    actual_answer: Optional[str] = None
    error: Optional[str] = None


def send_chat_request(question: str, session_id: str = "test_session") -> Dict:
    """Send a chat request to the API."""
    try:
        response = requests.post(
            API_CHAT_ENDPOINT,
            json={
                "question": question,
                "session_id": session_id
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def check_forbidden_locations(text: str) -> List[str]:
    """Check if text contains forbidden locations."""
    text_lower = text.lower()
    found = []
    for location in FORBIDDEN_LOCATIONS:
        if location in text_lower:
            found.append(location)
    return found


def check_correct_location(text: str) -> bool:
    """Check if text contains correct location."""
    text_lower = text.lower()
    for pattern in CORRECT_LOCATION_PATTERNS:
        if pattern in text_lower:
            return True
    return False


def check_keywords(text: str, keywords: List[str], all_required: bool = False) -> bool:
    """Check if text contains keywords."""
    text_lower = text.lower()
    if all_required:
        return all(keyword.lower() in text_lower for keyword in keywords)
    else:
        return any(keyword.lower() in text_lower for keyword in keywords)


def run_test_case(test_case: TestCase, session_id: str) -> TestCase:
    """Run a single test case."""
    print(f"\n{'='*80}")
    print(f"Test: {test_case.name}")
    print(f"Description: {test_case.description}")
    print(f"{'='*80}")
    
    conversation_history = []
    test_case.actual_answer = None
    test_case.error = None
    
    try:
        for i, (user_query, expected_keywords) in enumerate(test_case.conversation):
            print(f"\n[Turn {i+1}] User: {user_query}")
            
            # Send request
            response = send_chat_request(user_query, session_id)
            
            if "error" in response:
                test_case.error = response["error"]
                test_case.result = TestResult.FAIL
                print(f"❌ Error: {response['error']}")
                return test_case
            
            answer = response.get("answer", "")
            conversation_history.append((user_query, answer))
            
            print(f"[Turn {i+1}] Bot: {answer[:200]}...")
            
            # Check if this is the final turn (location query)
            if i == len(test_case.conversation) - 1:
                test_case.actual_answer = answer
                
                # Check for forbidden locations
                forbidden_found = check_forbidden_locations(answer)
                if forbidden_found:
                    print(f"❌ FAIL: Found forbidden locations: {forbidden_found}")
                    test_case.result = TestResult.FAIL
                    return test_case
                
                # Check for correct location (for location queries)
                if "location" in test_case.name.lower() or "where" in user_query.lower():
                    if not check_correct_location(answer):
                        print(f"⚠️  WARNING: Correct location pattern not found")
                        test_case.result = TestResult.WARNING
                    else:
                        print(f"✅ Correct location found")
                
                # Check for expected keywords
                if expected_keywords:
                    if isinstance(expected_keywords, str):
                        expected_keywords = [expected_keywords]
                    
                    if check_keywords(answer, expected_keywords):
                        print(f"✅ Expected keywords found: {expected_keywords}")
                    else:
                        print(f"⚠️  WARNING: Expected keywords not found: {expected_keywords}")
                        if test_case.result != TestResult.FAIL:
                            test_case.result = TestResult.WARNING
                
                # If no failures, mark as pass
                if test_case.result is None:
                    test_case.result = TestResult.PASS
                    print(f"✅ PASS")
            
            # Small delay between requests
            time.sleep(0.5)
        
    except Exception as e:
        test_case.error = str(e)
        test_case.result = TestResult.FAIL
        print(f"❌ Exception: {e}")
    
    return test_case


def create_test_cases() -> List[TestCase]:
    """Create all test cases."""
    test_cases = []
    
    # ========== LOCATION CONTAMINATION TESTS ==========
    
    test_cases.append(TestCase(
        name="TC1: Direct Location Query (Baseline)",
        description="Verify direct location query works without chat history",
        conversation=[
            ("where is it located", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="Should return correct location without forbidden locations",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC2: Location After Facilities Query",
        description="Location query after facilities query",
        conversation=[
            ("Facilities and amenities", []),
            ("where is it located", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="Should return correct location",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC3: Location After Nearby Attractions Query (CRITICAL)",
        description="Location query after nearby attractions query - most likely to fail",
        conversation=[
            ("nearby attractions", []),
            ("where is it located", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="Should return correct location, NOT Azad Kashmir",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC4: Location After Multiple Azad Kashmir Mentions",
        description="Location query after multiple queries mentioning Azad Kashmir",
        conversation=[
            ("What activities can we do?", []),
            ("What nearby picnic spots are available?", []),
            ("where is it located", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="Should return correct location despite multiple Azad Kashmir mentions",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC5: Location Query with Pronoun After Attractions",
        description="Pronoun expansion test after attractions query",
        conversation=[
            ("nearby attractions", []),
            ("tell me its location", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="Pronoun 'it' should expand to Swiss Cottages, not Azad Kashmir",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC6: Explicit Location Query After Attractions",
        description="Explicit location query (no pronoun) after attractions",
        conversation=[
            ("nearby attractions", []),
            ("where is Swiss Cottages located", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="Should return correct location",
        critical=False
    ))
    
    # ========== SAFETY QUERIES ==========
    
    test_cases.append(TestCase(
        name="TC7: Safety Query (Baseline)",
        description="Direct safety query",
        conversation=[
            ("Is it safe?", ["safe", "security", "gated"])
        ],
        expected_behavior="Should return safety information",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC8: Safety Query After Location Query",
        description="Safety query after location query",
        conversation=[
            ("where is it located", []),
            ("Is it safe?", ["safe", "security", "gated"])
        ],
        expected_behavior="Should return safety information without location contamination",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC9: Safety Query After Attractions Query",
        description="Safety query after attractions query",
        conversation=[
            ("nearby attractions", []),
            ("Is it safe?", ["safe", "security", "gated"])
        ],
        expected_behavior="Should return safety information",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC10: Safety for Each Cottage",
        description="Safety query asking about each cottage",
        conversation=[
            ("Is it safe for each cottage?", ["safe", "security", "gated"])
        ],
        expected_behavior="Should return safety information for all cottages",
        critical=False
    ))
    
    # ========== REASONING QUERIES (GROUP SIZE) ==========
    
    test_cases.append(TestCase(
        name="TC11: Reasoning Query - Group Size 7",
        description="Reasoning query about suitable cottage for 7 people",
        conversation=[
            ("We are 7 people, which cottage is suitable?", ["cottage", "suitable", "7"])
        ],
        expected_behavior="Should recommend appropriate cottage for 7 people",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC12: Reasoning Query - Group Size 7 Then Pricing",
        description="Group size query followed by pricing query",
        conversation=[
            ("We are 7 people, which cottage is suitable?", []),
            ("What is the price?", ["pkr", "price", "cost"])
        ],
        expected_behavior="Should provide pricing without location contamination",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC13: Reasoning Query - Group Size 7 Then Availability",
        description="Group size query followed by availability query",
        conversation=[
            ("We are 7 people, which cottage is suitable?", []),
            ("Is it available?", ["available", "availability"])
        ],
        expected_behavior="Should provide availability without location contamination",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC14: Reasoning Query - Group Size 7 Then Location",
        description="Group size query followed by location query",
        conversation=[
            ("We are 7 people, which cottage is suitable?", []),
            ("where is it located", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="Should return correct location, not contaminated by group size query",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC15: Reasoning Query - Group Size 10",
        description="Reasoning query about suitable cottage for 10 people",
        conversation=[
            ("We are 10 people, which cottage is suitable?", ["cottage", "suitable", "10"])
        ],
        expected_behavior="Should recommend appropriate cottage for 10 people",
        critical=False
    ))
    
    # ========== PRICING QUERIES ==========
    
    test_cases.append(TestCase(
        name="TC16: Pricing Query (Baseline)",
        description="Direct pricing query",
        conversation=[
            ("What is the price?", ["pkr", "price", "cost"])
        ],
        expected_behavior="Should return pricing information",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC17: Pricing Query After Location Query",
        description="Pricing query after location query",
        conversation=[
            ("where is it located", []),
            ("What is the price?", ["pkr", "price", "cost"])
        ],
        expected_behavior="Should return pricing without location contamination",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC18: Pricing Query After Attractions Query",
        description="Pricing query after attractions query",
        conversation=[
            ("nearby attractions", []),
            ("What is the price?", ["pkr", "price", "cost"])
        ],
        expected_behavior="Should return pricing without location contamination",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC19: Pricing Query After Safety Query",
        description="Pricing query after safety query",
        conversation=[
            ("Is it safe?", []),
            ("What is the price?", ["pkr", "price", "cost"])
        ],
        expected_behavior="Should return pricing without safety information contamination",
        critical=False
    ))
    
    # ========== AVAILABILITY QUERIES ==========
    
    test_cases.append(TestCase(
        name="TC20: Availability Query (Baseline)",
        description="Direct availability query",
        conversation=[
            ("Is it available?", ["available", "availability"])
        ],
        expected_behavior="Should return availability information",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC21: Availability Query After Pricing Query",
        description="Availability query after pricing query",
        conversation=[
            ("What is the price?", []),
            ("Is it available?", ["available", "availability"])
        ],
        expected_behavior="Should return availability without pricing contamination",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC22: Availability Query After Location Query",
        description="Availability query after location query",
        conversation=[
            ("where is it located", []),
            ("Is it available?", ["available", "availability"])
        ],
        expected_behavior="Should return availability without location contamination",
        critical=False
    ))
    
    # ========== BOOKING QUERIES ==========
    
    test_cases.append(TestCase(
        name="TC23: Booking Query (Baseline)",
        description="Direct booking query",
        conversation=[
            ("I want to book", ["book", "booking", "available"])
        ],
        expected_behavior="Should return booking information",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC24: Booking Query After Pricing Query",
        description="Booking query after pricing query",
        conversation=[
            ("What is the price?", []),
            ("I want to book", ["book", "booking", "available"])
        ],
        expected_behavior="Should return booking information",
        critical=False
    ))
    
    test_cases.append(TestCase(
        name="TC25: Booking Query After Availability Query",
        description="Booking query after availability query",
        conversation=[
            ("Is it available?", []),
            ("I want to book", ["book", "booking", "available"])
        ],
        expected_behavior="Should return booking information",
        critical=False
    ))
    
    # ========== COMPLEX SEQUENTIAL QUERIES ==========
    
    test_cases.append(TestCase(
        name="TC26: Full Booking Flow - Group Size → Pricing → Availability → Booking",
        description="Complete booking flow with multiple sequential queries",
        conversation=[
            ("We are 7 people, which cottage is suitable?", []),
            ("What is the price?", []),
            ("Is it available?", []),
            ("I want to book", ["book", "booking"])
        ],
        expected_behavior="Should handle complete booking flow without contamination",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC27: Attractions → Location → Safety → Pricing",
        description="Multiple sequential queries that might contaminate each other",
        conversation=[
            ("nearby attractions", []),
            ("where is it located", ["bhurban", "murree", "pakistan"]),
            ("Is it safe?", []),
            ("What is the price?", [])
        ],
        expected_behavior="Each query should return correct answer without contamination",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC28: Facilities → Attractions → Location (CRITICAL)",
        description="Facilities, then attractions, then location - high contamination risk",
        conversation=[
            ("Facilities and amenities", []),
            ("nearby attractions", []),
            ("where is it located", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="Location query should return correct location despite previous queries",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC29: Group Size → Attractions → Location → Pricing",
        description="Reasoning query, attractions, location, then pricing",
        conversation=[
            ("We are 7 people, which cottage is suitable?", []),
            ("nearby attractions", []),
            ("where is it located", ["bhurban", "murree", "pakistan"]),
            ("What is the price?", [])
        ],
        expected_behavior="All queries should work correctly without contamination",
        critical=True
    ))
    
    test_cases.append(TestCase(
        name="TC30: Multiple Location Queries",
        description="Multiple location queries in sequence",
        conversation=[
            ("where is it located", ["bhurban", "murree", "pakistan"]),
            ("tell me its location again", ["bhurban", "murree", "pakistan"]),
            ("where is Swiss Cottages located", ["bhurban", "murree", "pakistan"])
        ],
        expected_behavior="All location queries should return correct location",
        critical=True
    ))
    
    return test_cases


def print_summary(test_cases: List[TestCase]):
    """Print test summary."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total = len(test_cases)
    passed = sum(1 for tc in test_cases if tc.result == TestResult.PASS)
    failed = sum(1 for tc in test_cases if tc.result == TestResult.FAIL)
    warnings = sum(1 for tc in test_cases if tc.result == TestResult.WARNING)
    skipped = sum(1 for tc in test_cases if tc.result == TestResult.SKIP)
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Warnings: {warnings}")
    print(f"⏭️  Skipped: {skipped}")
    
    # Critical tests
    critical_tests = [tc for tc in test_cases if tc.critical]
    critical_passed = sum(1 for tc in critical_tests if tc.result == TestResult.PASS)
    critical_failed = sum(1 for tc in critical_tests if tc.result == TestResult.FAIL)
    
    print(f"\nCritical Tests: {len(critical_tests)}")
    print(f"✅ Passed: {critical_passed}")
    print(f"❌ Failed: {critical_failed}")
    
    # Failed tests
    if failed > 0:
        print("\n" + "="*80)
        print("FAILED TESTS")
        print("="*80)
        for tc in test_cases:
            if tc.result == TestResult.FAIL:
                print(f"\n❌ {tc.name}")
                print(f"   Error: {tc.error}")
                if tc.actual_answer:
                    forbidden = check_forbidden_locations(tc.actual_answer)
                    if forbidden:
                        print(f"   Found forbidden locations: {forbidden}")
                    print(f"   Answer preview: {tc.actual_answer[:200]}...")
    
    # Warnings
    if warnings > 0:
        print("\n" + "="*80)
        print("WARNINGS")
        print("="*80)
        for tc in test_cases:
            if tc.result == TestResult.WARNING:
                print(f"\n⚠️  {tc.name}")
                if tc.actual_answer:
                    print(f"   Answer preview: {tc.actual_answer[:200]}...")


def main():
    """Main test execution."""
    print("="*80)
    print("LOCATION CONTAMINATION TEST SUITE")
    print("="*80)
    print(f"API Endpoint: {API_CHAT_ENDPOINT}")
    print(f"Testing for forbidden locations: {FORBIDDEN_LOCATIONS}")
    print(f"Testing for correct location patterns: {CORRECT_LOCATION_PATTERNS}")
    
    # Check API availability
    try:
        health_response = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
        if health_response.status_code != 200:
            print(f"⚠️  Warning: API health check returned {health_response.status_code}")
    except Exception as e:
        print(f"⚠️  Warning: Could not check API health: {e}")
        print("   Continuing anyway...")
    
    # Create test cases
    test_cases = create_test_cases()
    
    # Run tests
    results = []
    for i, test_case in enumerate(test_cases, 1):
        session_id = f"test_session_{i}"
        result = run_test_case(test_case, session_id)
        results.append(result)
        time.sleep(1)  # Delay between test cases
    
    # Print summary
    print_summary(results)
    
    # Exit code
    critical_failures = sum(1 for tc in results if tc.critical and tc.result == TestResult.FAIL)
    if critical_failures > 0:
        print(f"\n❌ {critical_failures} critical test(s) failed!")
        sys.exit(1)
    else:
        print("\n✅ All critical tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
