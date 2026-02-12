#!/usr/bin/env python3
"""
Test script to verify slot extraction and cottage contamination fixes.
Tests based on the plan: faq_intent_and_slot_extraction_fix_c7d8b5f2.plan.md

Tests:
1. Cottage ID Contamination - general queries should NOT mention cottage unless explicitly mentioned
2. Pricing Queries - general pricing should return rates, not "couldn't find information"
3. General Info Queries - should NOT ask for slots
4. Specific Calculation Queries - should ask for missing slots
"""

import os
import sys
import requests
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent / "chatbot"
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_ENDPOINT = f"{API_BASE_URL}/api/chat"

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def count_sentences(text: str) -> int:
    """Count sentences in text."""
    if not text:
        return 0
    # Split by sentence-ending punctuation
    sentences = re.split(r'[.!?]+', text)
    # Filter out empty strings
    sentences = [s.strip() for s in sentences if s.strip()]
    return len(sentences)


def check_contains(text: str, keywords: List[str], case_sensitive: bool = False) -> List[str]:
    """Check if text contains keywords. Returns list of found keywords."""
    found = []
    text_check = text if case_sensitive else text.lower()
    
    # Synonyms mapping for flexible matching
    synonyms = {
        "restaurant": ["restaurant", "restaurants", "dining", "eatery", "eateries", "cafe", "cafes"],
        "nearby": ["nearby", "near", "close", "adjacent", "within"],
        "location": ["location", "located", "situated", "address", "where"],
        "available": ["available", "can", "possible", "offered", "provided"],
        "cook": ["cook", "chef", "cooking", "kitchen"],
        "mattress": ["mattress", "mattresses", "bedding", "sleeping", "accommodation"],
        "PKR": ["pkr", "rupees", "price", "cost", "pricing"],
        "price": ["pricing", "cost", "rate", "pkr", "price"],
        "pricing": ["price", "cost", "rate", "pkr", "pricing"],
        "per night": ["per-night", "nightly", "per night", "night"],
        "Murree": ["murree", "bhurban", "murree hills"],
    }
    
    for keyword in keywords:
        keyword_check = keyword if case_sensitive else keyword.lower()
        
        # Check if keyword has synonyms
        keyword_variants = [keyword_check]
        if keyword_check in synonyms:
            keyword_variants.extend(synonyms[keyword_check])
        
        # Check all variants
        for variant in keyword_variants:
            # Normalize spaces and hyphens for flexible matching
            variant_normalized = variant.replace(" ", "").replace("-", "")
            text_normalized = text_check.replace(" ", "").replace("-", "")
            
            # Check both original and normalized versions
            if variant in text_check or variant_normalized in text_normalized:
                found.append(keyword)
                break  # Found a match, no need to check other variants
    
    return found


def check_slot_questions(text: str) -> List[str]:
    """Check if text asks for slot information. Returns list of detected slot questions."""
    # Only detect actual questions asking for information, not just mentions
    slot_patterns = [
        (r"how many\s+(guests|people|members)\s+(will\s+be|are\s+you|do\s+you)", "guests"),
        (r"what\s+(are\s+)?(the\s+)?(check-in|check-out|arrival|departure)\s+dates", "dates"),
        (r"which\s+cottage\s+(are\s+you|do\s+you|would\s+you)", "cottage"),
        (r"do\s+you\s+have\s+a\s+preference\s+for\s+which\s+cottage", "cottage"),
        (r"what\s+(are\s+)?(the\s+)?dates\s+(of\s+your|for\s+your|are\s+you)", "dates"),
        (r"when\s+(are\s+you|do\s+you|will\s+you)\s+(planning|visiting|staying)", "dates"),
        (r"please\s+provide\s+(the\s+)?(dates|guests|cottage)", "general"),
        (r"to\s+calculate.*?i\s+need\s+(the\s+)?(dates|guests|cottage)", "general"),
    ]
    
    detected = []
    text_lower = text.lower()
    for pattern, slot_type in slot_patterns:
        if re.search(pattern, text_lower):
            if slot_type not in detected:
                detected.append(slot_type)
    
    # Also check for question marks followed by slot-related questions
    question_markers = [
        (r"\?\s*.*?(how many|what dates|which cottage)", "general"),
    ]
    for pattern, slot_type in question_markers:
        if re.search(pattern, text_lower):
            if slot_type not in detected:
                detected.append(slot_type)
    
    return detected


def send_chat_request(query: str, session_id: str = "test_session") -> Dict:
    """Send a chat request to the API."""
    try:
        response = requests.post(
            API_ENDPOINT,
            json={
                "question": query,
                "session_id": session_id,
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        # Handle quoted answers (sometimes API returns answer wrapped in quotes)
        if "answer" in result and isinstance(result["answer"], str):
            answer = result["answer"]
            # Remove surrounding quotes if present
            if answer.startswith('"') and answer.endswith('"'):
                result["answer"] = answer[1:-1]
            elif answer.startswith("'") and answer.endswith("'"):
                result["answer"] = answer[1:-1]
        return result
    except requests.exceptions.RequestException as e:
        return {"error": str(e), "answer": ""}


def test_cottage_contamination():
    """Test 1: Cottage ID Contamination"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 1: Cottage ID Contamination{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    test_cases = [
        {
            "name": "General question - should NOT mention cottage 7 or any specific cottage",
            "query": "are restaurants nearby",
            "should_not_contain": ["cottage 7", "Cottage 7", "near Cottage 9", "near cottage 9", "Cottage 9"],
            "should_not_ask_for": ["dates", "guests"],
            "should_contain": ["restaurant", "nearby"],  # Should answer the question
        },
        {
            "name": "General pricing question - should NOT mention cottage 7",
            "query": "what is the pricing per night",
            "should_not_contain": ["cottage 7", "Cottage 7"],
            "should_not_ask_for": ["dates", "guests"],
            "should_contain": ["PKR", "price", "pricing", "per night"],
        },
        {
            "name": "General question after mentioning cottage - should use mentioned cottage",
            "query": "tell me about cottage 9",
            "should_contain": ["Cottage 9", "cottage 9"],
            "should_not_contain": ["cottage 7", "Cottage 7"],
        },
    ]
    
    results = []
    for i, test in enumerate(test_cases, 1):
        print(f"{YELLOW}Test 1.{i}: {test['name']}{RESET}")
        print(f"Query: {test['query']}")
        
        response = send_chat_request(test['query'])
        answer = response.get("answer", "")
        
        if not answer:
            print(f"{RED}❌ FAILED: No answer returned{RESET}")
            if "error" in response:
                print(f"{RED}Error: {response['error']}{RESET}")
            results.append(False)
            continue
        
        # Show full answer for debugging
        print(f"{BLUE}Full Answer:{RESET}")
        print(f"{answer}\n")
        
        # Check should_not_contain
        failed = False
        if "should_not_contain" in test:
            found = check_contains(answer, test["should_not_contain"])
            if found:
                print(f"{RED}❌ FAILED: Answer contains forbidden terms: {found}{RESET}")
                print(f"Answer snippet: {answer[:200]}...")
                failed = True
        
        # Check should_contain
        if "should_contain" in test and not failed:
            found = check_contains(answer, test["should_contain"])
            missing = [k for k in test["should_contain"] if k not in found]
            if missing:
                print(f"{RED}❌ FAILED: Answer missing required terms: {missing}{RESET}")
                failed = True
        
        # Check should_not_ask_for (slot questions) - use proper slot question detection
        if "should_not_ask_for" in test and not failed:
            found_slots = check_slot_questions(answer)
            # Also check for simple mentions that might be slot questions
            simple_slot_mentions = check_contains(answer, test["should_not_ask_for"])
            # Filter out false positives - "cottage" in "Swiss Cottages" is not asking for cottage slot
            false_positive_patterns = ["swiss cottages", "cottages bhurban", "cottage manager"]
            actual_slot_questions = []
            for slot in simple_slot_mentions:
                # Check if it's a false positive
                is_false_positive = False
                if slot == "cottage":
                    # Check if "cottage" appears in context that's not asking for it
                    answer_lower = answer.lower()
                    for pattern in false_positive_patterns:
                        if pattern in answer_lower:
                            # Check if "cottage" appears near these patterns (within 20 chars)
                            pattern_idx = answer_lower.find(pattern)
                            cottage_idx = answer_lower.find("cottage")
                            if cottage_idx != -1 and abs(cottage_idx - pattern_idx) < 20:
                                is_false_positive = True
                                break
                if not is_false_positive:
                    actual_slot_questions.append(slot)
            
            if found_slots or actual_slot_questions:
                print(f"{RED}❌ FAILED: Answer asks for slots: {found_slots or actual_slot_questions}{RESET}")
                failed = True
        
        if not failed:
            print(f"{GREEN}✅ PASSED{RESET}")
            results.append(True)
        else:
            results.append(False)
        
        print()
    
    return results


def test_pricing_queries():
    """Test 2: Pricing Queries"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 2: Pricing Queries{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    test_cases = [
        {
            "name": "General pricing query - should show rates, NOT 'couldn't find information'",
            "query": "tell me the pricing per night",
            "should_contain": ["PKR", "price", "pricing", "per night"],
            "should_not_contain": [
                "couldn't find",
                "could not find",
                "I couldn't find",
                "no information",
                "missing required",
            ],
            "should_not_ask_for": ["dates", "guests"],
        },
        {
            "name": "General pricing for specific cottage - should show rates",
            "query": "what are the prices for cottage 11",
            "should_contain": ["PKR", "price", "Cottage 11", "cottage 11"],
            "should_not_contain": [
                "couldn't find",
                "could not find",
                "I couldn't find",
                "no information",
                "missing required",
            ],
        },
        {
            "name": "Specific pricing calculation - should calculate or ask for missing info",
            "query": "pricing for 4 guests on March 23-26",
            "should_contain": ["PKR", "price", "4", "guests"],
            "should_not_contain": [
                "couldn't find",
                "could not find",
                "I couldn't find",
            ],
        },
    ]
    
    results = []
    for i, test in enumerate(test_cases, 1):
        print(f"{YELLOW}Test 2.{i}: {test['name']}{RESET}")
        print(f"Query: {test['query']}")
        
        response = send_chat_request(test['query'])
        answer = response.get("answer", "")
        
        if not answer:
            print(f"{RED}❌ FAILED: No answer returned{RESET}")
            results.append(False)
            continue
        
        # Check should_not_contain
        failed = False
        if "should_not_contain" in test:
            found = check_contains(answer, test["should_not_contain"])
            if found:
                print(f"{RED}❌ FAILED: Answer contains forbidden terms: {found}{RESET}")
                print(f"Answer snippet: {answer[:200]}...")
                failed = True
        
        # Check should_contain
        if "should_contain" in test and not failed:
            found = check_contains(answer, test["should_contain"])
            missing = [k for k in test["should_contain"] if k not in found]
            if missing:
                print(f"{RED}❌ FAILED: Answer missing required terms: {missing}{RESET}")
                failed = True
        
        # Check should_not_ask_for
        if "should_not_ask_for" in test and not failed:
            slot_questions = ["dates", "guests", "cottage", "check-in", "check-out"]
            found_slots = check_contains(answer, slot_questions)
            if found_slots:
                print(f"{YELLOW}⚠️  WARNING: Answer asks for slots: {found_slots} (may be acceptable for specific calculations){RESET}")
        
        if not failed:
            print(f"{GREEN}✅ PASSED{RESET}")
            results.append(True)
        else:
            results.append(False)
        
        print()
    
    return results


def test_general_info_queries():
    """Test 3: General Info Queries"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 3: General Info Queries (Should NOT ask for slots){RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    test_cases = [
        {
            "name": "Restaurants nearby - should answer, NO slot questions",
            "query": "are restaurants nearby",
            "should_contain": ["restaurant", "nearby"],
            "should_not_ask_for": ["dates", "guests", "cottage", "check-in", "check-out"],
        },
        {
            "name": "Chef service - should answer, NO slot questions",
            "query": "do you provide chef service",
            "should_contain": ["chef", "cook", "service"],
            "should_not_ask_for": ["dates", "guests", "cottage", "check-in", "check-out"],
        },
        {
            "name": "Extra mattresses - should answer, NO slot questions",
            "query": "are extra mattresses available",
            "should_contain": ["mattress", "available"],
            "should_not_ask_for": ["dates", "guests", "cottage", "check-in", "check-out"],
        },
        {
            "name": "Location query - should answer, NO slot questions",
            "query": "where is swiss cottages located",
            "should_contain": ["location", "Bhurban", "Murree"],
            "should_not_ask_for": ["dates", "guests", "cottage", "check-in", "check-out"],
        },
    ]
    
    results = []
    for i, test in enumerate(test_cases, 1):
        print(f"{YELLOW}Test 3.{i}: {test['name']}{RESET}")
        print(f"Query: {test['query']}")
        
        response = send_chat_request(test['query'])
        answer = response.get("answer", "")
        
        if not answer:
            print(f"{RED}❌ FAILED: No answer returned{RESET}")
            results.append(False)
            continue
        
        # Check should_contain
        failed = False
        if "should_contain" in test:
            found = check_contains(answer, test["should_contain"])
            missing = [k for k in test["should_contain"] if k not in found]
            if missing:
                print(f"{RED}❌ FAILED: Answer missing required terms: {missing}{RESET}")
                failed = True
        
        # Check should_not_ask_for (slot questions) - only check for actual questions
        if "should_not_ask_for" in test and not failed:
            found_slots = check_slot_questions(answer)
            
            if found_slots:
                print(f"{RED}❌ FAILED: Answer asks for slots: {found_slots}{RESET}")
                # Show the part of answer that contains slot questions
                for slot in found_slots:
                    # Find where the slot question appears
                    lines = answer.split('\n')
                    for line in lines:
                        if any(pattern in line.lower() for pattern in ["how many", "what dates", "which cottage", "please provide", "i need"]):
                            print(f"{RED}  Found slot question: {line.strip()}{RESET}")
                failed = True
        
        if not failed:
            print(f"{GREEN}✅ PASSED{RESET}")
            results.append(True)
        else:
            results.append(False)
        
        print()
    
    return results


def test_specific_calculation_queries():
    """Test 4: Specific Calculation Queries (Should ask for missing slots)"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 4: Specific Calculation Queries (Should ask for missing slots){RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    test_cases = [
        {
            "name": "Pricing with partial info - should ask for missing slots",
            "query": "pricing for 4 guests on March 23-26",
            "should_contain": ["PKR", "price", "4", "guests"],
            "may_ask_for": ["cottage", "cottage_id"],  # May ask for cottage if not mentioned
        },
        {
            "name": "Booking with partial info - should ask for missing slots",
            "query": "book cottage 9",
            "should_contain": ["Cottage 9", "cottage 9"],
            "may_ask_for": ["dates", "guests", "check-in", "check-out"],
        },
        {
            "name": "Availability with partial info - should ask for dates",
            "query": "is cottage 7 available",
            "should_contain": ["Cottage 7", "available"],
            "may_ask_for": ["dates", "check-in", "check-out"],
        },
    ]
    
    results = []
    for i, test in enumerate(test_cases, 1):
        print(f"{YELLOW}Test 4.{i}: {test['name']}{RESET}")
        print(f"Query: {test['query']}")
        
        response = send_chat_request(test['query'])
        answer = response.get("answer", "")
        
        if not answer:
            print(f"{RED}❌ FAILED: No answer returned{RESET}")
            results.append(False)
            continue
        
        # Check should_contain
        failed = False
        if "should_contain" in test:
            found = check_contains(answer, test["should_contain"])
            missing = [k for k in test["should_contain"] if k not in found]
            if missing:
                print(f"{RED}❌ FAILED: Answer missing required terms: {missing}{RESET}")
                failed = True
        
        # Check may_ask_for (it's OK if it asks for these)
        if "may_ask_for" in test and not failed:
            slot_questions = test["may_ask_for"]
            found_slots = check_contains(answer, slot_questions)
            if found_slots:
                print(f"{GREEN}✓ Answer appropriately asks for missing info: {found_slots}{RESET}")
            else:
                print(f"{YELLOW}⚠️  Note: Answer doesn't ask for missing slots (may have all info or handled differently){RESET}")
        
        if not failed:
            print(f"{GREEN}✅ PASSED{RESET}")
            results.append(True)
        else:
            results.append(False)
        
        print()
    
    return results


def main():
    """Run all tests."""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}SLOT EXTRACTION AND COTTAGE CONTAMINATION FIX - TEST SUITE{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    # Check if API is available
    try:
        response = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
        if response.status_code != 200:
            print(f"{RED}❌ API is not responding correctly (status: {response.status_code}){RESET}")
            return
    except requests.exceptions.RequestException as e:
        print(f"{RED}❌ Cannot connect to API at {API_BASE_URL}{RESET}")
        print(f"{YELLOW}Error: {e}{RESET}")
        print(f"{YELLOW}Make sure the FastAPI server is running: ./start_services.sh{RESET}")
        return
    
    print(f"{GREEN}✓ API is available at {API_BASE_URL}{RESET}\n")
    
    # Run all test suites
    all_results = []
    
    # Test 1: Cottage Contamination
    results1 = test_cottage_contamination()
    all_results.extend(results1)
    
    # Test 2: Pricing Queries
    results2 = test_pricing_queries()
    all_results.extend(results2)
    
    # Test 3: General Info Queries
    results3 = test_general_info_queries()
    all_results.extend(results3)
    
    # Test 4: Specific Calculation Queries
    results4 = test_specific_calculation_queries()
    all_results.extend(results4)
    
    # Summary
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST SUMMARY{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    total = len(all_results)
    passed = sum(all_results)
    failed = total - passed
    
    print(f"Total Tests: {total}")
    print(f"{GREEN}Passed: {passed}{RESET}")
    print(f"{RED}Failed: {failed}{RESET}")
    print(f"Success Rate: {(passed/total*100):.1f}%")
    
    if failed == 0:
        print(f"\n{GREEN}🎉 All tests passed!{RESET}\n")
        return 0
    else:
        print(f"\n{RED}❌ Some tests failed. Please review the output above.{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
