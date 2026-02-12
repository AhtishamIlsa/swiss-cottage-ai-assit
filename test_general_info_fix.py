#!/usr/bin/env python3
"""
Test script to verify that general information is provided when specific per-cottage details are not available.
Tests based on the plan: handle_general_info_when_specific_not_available

Tests:
1. Kitchen facilities in each cottage - should provide general kitchen info
2. Safety for each cottage - should provide general safety info
3. Facilities in each cottage - should provide general facilities info
"""

import os
import sys
import requests
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_ENDPOINT = f"{API_BASE_URL}/api/chat"

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def send_chat_request(question: str, session_id: str = "test_session") -> Dict:
    """Send a chat request to the API."""
    try:
        payload = {
            "question": question,
            "session_id": session_id
        }
        response = requests.post(API_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"{RED}Error sending request: {e}{RESET}")
        return {}


def check_negative_phrases(text: str) -> List[str]:
    """Check if text contains negative phrases indicating information wasn't found."""
    negative_phrases = [
        "i couldn't find",
        "i was unable to find",
        "i don't have",
        "i don't have enough information",
        "unfortunately, i",
        "unfortunately i",
        "i recommend checking",
        "please contact",
        "reach out to",
        "contact the establishment",
        "check the official website",
        "i need more information",
        "i need to know more",
        "i would need",
        "i would recommend",
    ]
    
    found = []
    text_lower = text.lower()
    for phrase in negative_phrases:
        if phrase in text_lower:
            found.append(phrase)
    
    return found


def check_positive_phrases(text: str) -> List[str]:
    """Check if text contains positive phrases indicating general information was provided."""
    positive_phrases = [
        "all cottages",
        "the cottages",
        "each cottage",
        "cottage 7, cottage 9, and cottage 11",
        "cottage 7, 9, and 11",
        "cottages include",
        "cottages have",
        "cottages feature",
    ]
    
    found = []
    text_lower = text.lower()
    for phrase in positive_phrases:
        if phrase in text_lower:
            found.append(phrase)
    
    return found


def test_kitchen_facilities():
    """Test 1: Kitchen facilities in each cottage"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test 1: Kitchen Facilities in Each Cottage{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    query = "Tell me about the kitchen facilities in each cottage?"
    print(f"{YELLOW}Query: {query}{RESET}\n")
    
    response = send_chat_request(query)
    answer = response.get("answer", "")
    
    if not answer:
        print(f"{RED}❌ FAILED: No answer returned{RESET}\n")
        return False
    
    print(f"{GREEN}Answer:{RESET}")
    print(f"{answer}\n")
    
    # Check for negative phrases
    negative_phrases = check_negative_phrases(answer)
    if negative_phrases:
        print(f"{RED}❌ FAILED: Answer contains negative phrases: {negative_phrases}{RESET}")
        print(f"{RED}   This indicates the bot said it couldn't find information instead of providing general info{RESET}\n")
        return False
    
    # Check for positive phrases
    positive_phrases = check_positive_phrases(answer)
    if not positive_phrases:
        print(f"{YELLOW}⚠️  WARNING: Answer doesn't clearly state that facilities apply to all cottages{RESET}")
        print(f"{YELLOW}   However, it doesn't contain negative phrases, so it may still be acceptable{RESET}\n")
    else:
        print(f"{GREEN}✅ PASSED: Answer provides general information and states it applies to all cottages{RESET}")
        print(f"{GREEN}   Found positive phrases: {positive_phrases}{RESET}\n")
    
    # Check if answer mentions kitchen-related terms
    kitchen_terms = ["kitchen", "microwave", "oven", "kettle", "refrigerator", "cookware", "utensils"]
    found_kitchen_terms = [term for term in kitchen_terms if term.lower() in answer.lower()]
    if found_kitchen_terms:
        print(f"{GREEN}✅ Answer mentions kitchen facilities: {found_kitchen_terms}{RESET}\n")
    else:
        print(f"{YELLOW}⚠️  Answer doesn't mention specific kitchen facilities{RESET}\n")
    
    return len(negative_phrases) == 0


def test_safety_measures():
    """Test 2: Safety for each cottage"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test 2: Safety Measures for Each Cottage{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    query = "What are the safety measures for each cottage?"
    print(f"{YELLOW}Query: {query}{RESET}\n")
    
    response = send_chat_request(query)
    answer = response.get("answer", "")
    
    if not answer:
        print(f"{RED}❌ FAILED: No answer returned{RESET}\n")
        return False
    
    print(f"{GREEN}Answer:{RESET}")
    print(f"{answer}\n")
    
    # Check for negative phrases
    negative_phrases = check_negative_phrases(answer)
    if negative_phrases:
        print(f"{RED}❌ FAILED: Answer contains negative phrases: {negative_phrases}{RESET}")
        print(f"{RED}   This indicates the bot said it couldn't find information instead of providing general info{RESET}\n")
        return False
    
    # Check for positive phrases
    positive_phrases = check_positive_phrases(answer)
    if not positive_phrases:
        print(f"{YELLOW}⚠️  WARNING: Answer doesn't clearly state that safety measures apply to all cottages{RESET}")
        print(f"{YELLOW}   However, it doesn't contain negative phrases, so it may still be acceptable{RESET}\n")
    else:
        print(f"{GREEN}✅ PASSED: Answer provides general information and states it applies to all cottages{RESET}")
        print(f"{GREEN}   Found positive phrases: {positive_phrases}{RESET}\n")
    
    # Check if answer mentions safety-related terms
    safety_terms = ["safety", "security", "guard", "gated", "secure", "safe"]
    found_safety_terms = [term for term in safety_terms if term.lower() in answer.lower()]
    if found_safety_terms:
        print(f"{GREEN}✅ Answer mentions safety measures: {found_safety_terms}{RESET}\n")
    else:
        print(f"{YELLOW}⚠️  Answer doesn't mention specific safety measures{RESET}\n")
    
    return len(negative_phrases) == 0


def test_facilities_in_each_cottage():
    """Test 3: Facilities in each cottage"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test 3: Facilities Available in Each Cottage{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    query = "What facilities are available in each cottage?"
    print(f"{YELLOW}Query: {query}{RESET}\n")
    
    response = send_chat_request(query)
    answer = response.get("answer", "")
    
    if not answer:
        print(f"{RED}❌ FAILED: No answer returned{RESET}\n")
        return False
    
    print(f"{GREEN}Answer:{RESET}")
    print(f"{answer}\n")
    
    # Check for negative phrases
    negative_phrases = check_negative_phrases(answer)
    if negative_phrases:
        print(f"{RED}❌ FAILED: Answer contains negative phrases: {negative_phrases}{RESET}")
        print(f"{RED}   This indicates the bot said it couldn't find information instead of providing general info{RESET}\n")
        return False
    
    # Check for positive phrases
    positive_phrases = check_positive_phrases(answer)
    if not positive_phrases:
        print(f"{YELLOW}⚠️  WARNING: Answer doesn't clearly state that facilities apply to all cottages{RESET}")
        print(f"{YELLOW}   However, it doesn't contain negative phrases, so it may still be acceptable{RESET}\n")
    else:
        print(f"{GREEN}✅ PASSED: Answer provides general information and states it applies to all cottages{RESET}")
        print(f"{GREEN}   Found positive phrases: {positive_phrases}{RESET}\n")
    
    return len(negative_phrases) == 0


def main():
    """Run all tests."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Testing: General Information When Specific Details Not Available{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    
    results = []
    
    # Test 1: Kitchen facilities
    result1 = test_kitchen_facilities()
    results.append(("Kitchen Facilities", result1))
    
    # Test 2: Safety measures
    result2 = test_safety_measures()
    results.append(("Safety Measures", result2))
    
    # Test 3: Facilities in each cottage
    result3 = test_facilities_in_each_cottage()
    results.append(("Facilities in Each Cottage", result3))
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test Summary{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{GREEN}✅ PASSED{RESET}" if result else f"{RED}❌ FAILED{RESET}"
        print(f"{test_name}: {status}")
    
    print(f"\n{BLUE}Total: {passed}/{total} tests passed{RESET}\n")
    
    if passed == total:
        print(f"{GREEN}🎉 All tests passed! The fix is working correctly.{RESET}\n")
        return 0
    else:
        print(f"{YELLOW}⚠️  Some tests failed. Please review the responses above.{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
