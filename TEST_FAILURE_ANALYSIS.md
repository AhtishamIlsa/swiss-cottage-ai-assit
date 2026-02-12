# Test Failure Analysis - What Needs to be Fixed

## Critical Issues Found

### 1. **WRONG PRICING INFORMATION** ❌ CRITICAL

**Problem**: The chatbot is returning incorrect pricing:
- Returns: PKR 24,000 (weekend) and PKR 18,000 (weekday) for general pricing
- Returns: PKR 18,000 (weekend) and PKR 12,000 (weekday) in some cases

**Actual FAQ Prices**:
- Cottage 11: PKR 32,000 (weekend), PKR 26,000 (weekday)
- Cottage 9: PKR 38,000 (weekend), PKR 33,000 (weekday)
- Cottage 7: Not found in FAQs (needs to be added or extracted)

**Root Cause**: 
- The LLM is **hallucinating** prices that don't exist in the FAQ files
- The `_extract_general_pricing_from_context()` method in `pricing_handler.py` may not be extracting prices correctly
- OR the LLM is generating prices instead of using the extracted context

**What to Check**:
1. Check what documents are being retrieved for pricing queries
2. Check if `_extract_general_pricing_from_context()` is finding the correct prices
3. Check if the LLM prompt is instructing it to use ONLY context, not generate prices
4. Verify the pricing extraction regex patterns are working correctly

**Files to Review**:
- `chatbot/bot/conversation/pricing_handler.py` (lines 86-184)
- `chatbot/bot/client/prompt.py` (PRICING_PROMPT_TEMPLATE)
- Check what documents are retrieved for "what is the pricing per night"

---

### 2. **Cottage Contamination Still Happening** ⚠️

**Test 1.1 Failure**: "are restaurants nearby"
- Answer mentions "Cottage 9" when it shouldn't
- This means `should_use_current_cottage()` or slot extraction is still using `current_cottage` for general queries

**What to Check**:
1. Check if `slot_manager.should_use_current_cottage()` is being called correctly
2. Check if `main.py` is clearing `cottage_id` for general info intents (LOCATION, FACILITIES, FAQ_QUESTION)
3. Check logs to see if `current_cottage` is being set inappropriately

**Files to Review**:
- `chatbot/bot/conversation/slot_manager.py` (should_use_current_cottage method)
- `chatbot/api/main.py` (where cottage_id is cleared for general intents)

---

### 3. **Missing Keywords in Test Checks** ⚠️

Some tests are failing because the test script is too strict:
- "are restaurants nearby" - answer says "restaurants near the cottages" but test looks for exact word "nearby"
- "do you provide chef service" - answer mentions "chef" but test looks for "cook"
- "where is swiss cottages located" - answer may say "Bhurban, Murree" but test looks for exact word "location" and "Murree"

**Solution**: Make test keyword matching more flexible (synonyms, related terms)

---

### 4. **Pricing Query Not Returning PKR Amounts** ❌

**Test 2.2**: "what are the prices for cottage 11"
- Should return: PKR 32,000 (weekend), PKR 26,000 (weekday)
- But test shows it's not returning PKR amounts

**What to Check**:
1. Is the FAQ document for Cottage 11 being retrieved?
2. Is the pricing extraction working for cottage-specific queries?
3. Is the LLM using the extracted pricing template correctly?

---

### 5. **General Pricing Query Structure** ⚠️

**Test 2.1**: "tell me the pricing per night"
- Returns pricing structure but amounts are wrong (PKR 24,000 / PKR 18,000)
- Should return general rates OR cottage-specific rates if available

**Issue**: There's no "general" pricing FAQ - only cottage-specific pricing (Cottage 9, Cottage 11)
- Need to decide: Should general pricing query return ALL cottage prices, or average, or ask which cottage?

---

## Recommended Actions

### Priority 1: Fix Pricing Information (CRITICAL)
1. **Debug pricing extraction**:
   - Add logging to `_extract_general_pricing_from_context()` to see what it's extracting
   - Test the regex patterns against actual FAQ content
   - Verify the extracted prices match FAQ files

2. **Fix LLM prompt**:
   - Ensure PRICING_PROMPT_TEMPLATE explicitly forbids generating prices
   - Must use ONLY extracted pricing from context
   - Add validation that returned prices exist in FAQ files

3. **Add Cottage 7 pricing**:
   - Either add to FAQ files or handle gracefully when not found

### Priority 2: Fix Cottage Contamination
1. **Verify slot_manager logic**:
   - Check `should_use_current_cottage()` is working correctly
   - Ensure `current_cottage` is NOT used for LOCATION, FACILITIES, FAQ_QUESTION intents

2. **Check main.py**:
   - Verify `cottage_id` is being cleared for general info queries
   - Check if intent classification is correct

### Priority 3: Improve Test Script
1. **Make keyword matching flexible**:
   - Use synonyms (restaurant/nearby, chef/cook, location/where)
   - Check for related terms, not just exact matches

2. **Add better debugging**:
   - Show retrieved documents for each query
   - Show extracted pricing information
   - Show slot extraction results

---

## Test Results Summary

**Total Tests**: 13
**Passed**: 3-4 (23-30%)
**Failed**: 9-10 (70-77%)

**Critical Failures**:
1. Wrong pricing (hallucinated prices)
2. Cottage contamination (still happening)
3. Missing PKR amounts in responses

**Minor Issues**:
- Test keyword matching too strict
- Some answers are correct but don't match exact keywords

---

## Next Steps

1. **First**: Debug why pricing is wrong - check logs, retrieved documents, extraction logic
2. **Second**: Fix cottage contamination - verify slot_manager logic
3. **Third**: Improve test script to be more flexible
4. **Fourth**: Re-run tests and verify fixes
