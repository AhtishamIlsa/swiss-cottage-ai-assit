# Required Slots Debug Analysis

## Problem Summary

**21 general info questions incorrectly have `required_slots` when they should be empty.**

These questions are asking for general information (policies, processes, descriptions) and don't need any slots extracted from the user. However, they're being assigned required slots because:

1. They're classified with intents that normally require slots (`booking`, `pricing`, `availability`)
2. The `INTENT_TO_SLOTS` mapping assigns slots based on intent type only
3. There's no logic to distinguish "general info" vs "specific calculation" questions

## Root Cause

The `enrich_faq_metadata.py` script uses this logic:

```python
INTENT_TO_SLOTS = {
    "booking": {
        "required": ["guests", "dates", "cottage_id", "family"],  # ALL booking questions get these
    },
    "pricing": {
        "required": ["guests", "dates", "cottage_id"],  # ALL pricing questions get these
    },
    # ...
}
```

**Problem**: This assigns slots to ALL questions of an intent type, but:
- "What is the cancellation policy?" (booking intent) → General info, doesn't need slots
- "I want to book for 2 guests" (booking intent) → Specific action, needs slots

## Affected Files (21 files)

### Booking Intent - General Info Questions (13 files)
- `cancellation_refunds_faq_101.md`: "What is the cancellation policy?"
- `cancellation_refunds_faq_102.md`: "Will I get a refund if I cancel?"
- `cancellation_refunds_faq_104.md`: "Is the cancellation policy different..."
- `check_in_check_out_faq_105.md`: "What is the check-in process?"
- `check_in_check_out_faq_106.md`: "What is the check-out process?"
- `guest_support_faq_117.md`: "Is there an on-site caretaker available?"
- `guest_support_faq_118.md`: "Who is the owner or main point of contact?"
- `guest_support_faq_120.md`: "Is there security at the main gate?"
- `guest_support_faq_121.md`: "Who is the on-site caretaker..."
- `guest_support_faq_122.md`: "Who is the cottage manager..."
- `guest_support_faq_123.md`: "Is there an alternate contact number..."
- `guest_support_faq_124.md`: "Who is the business owner..."
- `guest_support_faq_125.md`: "Who is responsible for security..."
- `host_owner_poc_faq_126.md`: "Who is the point of contact?"

### Pricing Intent - General Info Questions (7 files)
- `damage_liability_faq_112.md`: "What happens if something is damaged?"
- `pricing_payments_faq_084.md`: "What are the prices for Cottage 11?"
- `pricing_payments_faq_085.md`: "What are the prices for Cottage 9?"
- `pricing_payments_faq_086.md`: "What is the difference between Cottage 9 and Cottage 11?"
- `pricing_payments_faq_093.md`: "Is there a minimum stay requirement?"
- `pricing_payments_faq_094.md`: "What is the advance payment or booking confirmation process?"
- `pricing_payments_faq_095.md`: "What is the maximum number of guests allowed in each cottage?"

### Availability Intent - General Info Questions (1 file)
- `availability_dates_faq_082.md`: "How can I check availability?"

## Solution

Add a function to detect "general info" questions and override `required_slots` to `[]` for them:

```python
def is_general_info_question(question: str, intent: str) -> bool:
    """
    Determine if a question is asking for general information vs specific calculation.
    
    General info questions don't need slots - they're asking about policies, processes, descriptions.
    Specific calculation questions need slots - they're asking for a specific price/booking.
    """
    question_lower = question.lower()
    
    # General info question patterns
    general_patterns = [
        "what is", "what are", "tell me about", "explain", "describe",
        "how do you", "how does", "do you have", "is there", "are there",
        "can i", "can we", "is it", "does it", "will i", "what happens",
        "what about", "how to", "how can", "where is", "where are",
        "when is", "when are", "who is", "who are"
    ]
    
    # Check if question starts with general info pattern
    if any(question_lower.startswith(pattern) for pattern in general_patterns):
        return True
    
    # Additional checks for specific intents
    if intent == "booking":
        # Policy/process questions are general info
        if any(word in question_lower for word in ["policy", "process", "procedure", "who is", "who are", "is there", "are there"]):
            return True
    
    if intent == "pricing":
        # General pricing info questions (not specific calculations)
        if any(word in question_lower for word in ["what are the prices", "what is the price", "what are prices", "difference between", "minimum stay", "maximum number"]):
            return True
        # But exclude specific calculation requests
        if any(word in question_lower for word in ["for", "cost for", "price for", "how much for"]):
            return False
    
    if intent == "availability":
        # "How can I check" is general info
        if "how can" in question_lower or "how do" in question_lower:
            return True
    
    return False
```

Then modify the slot assignment logic:

```python
# Get slots for intent
slots = get_slots_for_intent(intent)

# Override for general info questions
if is_general_info_question(question, intent):
    slots = {"required": [], "optional": slots["optional"]}
```

## Statistics

- **Total FAQ files**: 160
- **Files with required_slots**: 43
- **Files without required_slots**: 117
- **❌ General info questions WITH required_slots (WRONG)**: 21

## Intent Distribution

- `booking`: 23 files (13 general info with slots - WRONG)
- `pricing`: 18 files (7 general info with slots - WRONG)
- `availability`: 2 files (1 general info with slots - WRONG)
- `facilities`: 23 files (all correct - no slots)
- `faq_question`: 47 files (all correct - no slots)
- `location`: 18 files (all correct - no slots)
- `rooms`: 27 files (all correct - no slots)
- `safety`: 2 files (all correct - no slots)
