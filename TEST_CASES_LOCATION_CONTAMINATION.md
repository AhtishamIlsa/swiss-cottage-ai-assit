# Test Cases: Location Contamination from Chat History

## Problem Statement
When users ask multiple questions in sequence, chat history might contaminate location answers:
1. User asks about facilities/amenities
2. User asks about nearby attractions (mentions "viewpoints overlooking Azad Kashmir")
3. User asks "where is it located" → Bot might think user is asking about attractions' location, not cottages' location

## Test Scenarios

### Test Case 1: Direct Location Query (Baseline)
**Purpose**: Verify direct location query works correctly without chat history contamination

**Conversation Flow**:
1. User: "where is it located"
2. Expected: "Swiss Cottages is located adjacent to Pearl Continental (PC) Bhurban in the Murree Hills, within a secure gated community in Bhurban, Pakistan"
3. Should NOT contain: "Azad Kashmir", "Patriata", "Bhubaneswar"

**Expected Behavior**: ✅ Should work correctly (no chat history)

---

### Test Case 2: Location Query After Facilities Query
**Purpose**: Verify location query after facilities query doesn't get contaminated

**Conversation Flow**:
1. User: "Facilities and amenities"
2. Bot: [Responds about facilities]
3. User: "where is it located"
4. Expected: Correct location (Bhurban, Murree, Pakistan)
5. Should NOT contain: "Azad Kashmir"

**Expected Behavior**: ✅ Should work (facilities query doesn't mention Azad Kashmir)

---

### Test Case 3: Location Query After Nearby Attractions Query (CRITICAL)
**Purpose**: Verify location query after nearby attractions query doesn't get contaminated by "Azad Kashmir" mention

**Conversation Flow**:
1. User: "nearby attractions" or "What nearby attractions are there?"
2. Bot: [Responds about attractions, mentions "viewpoints overlooking Azad Kashmir"]
3. User: "where is it located" or "tell me its location"
4. Expected: "Swiss Cottages is located adjacent to Pearl Continental (PC) Bhurban in the Murree Hills, within a secure gated community in Bhurban, Pakistan"
5. Should NOT contain: "Azad Kashmir" for cottage location
6. Should NOT say: "Bhurban, Azad Kashmir" or "located in Azad Kashmir"

**Expected Behavior**: ⚠️ **THIS IS THE PROBLEM** - Bot might think user is asking about attractions' location

**Potential Issues**:
- Chat history contains "Azad Kashmir" from previous answer
- LLM might interpret "where is it located" as referring to attractions mentioned in previous message
- Context refinement might expand "it" to refer to attractions instead of cottages

---

### Test Case 4: Location Query After Multiple Queries Mentioning Azad Kashmir
**Purpose**: Verify location query after multiple queries mentioning Azad Kashmir doesn't get contaminated

**Conversation Flow**:
1. User: "What activities can we do?"
2. Bot: [Mentions "visiting viewpoints overlooking Azad Kashmir"]
3. User: "What nearby picnic spots are available?"
4. Bot: [Mentions "scenic viewpoints overlooking Azad Kashmir"]
5. User: "where is it located"
6. Expected: Correct location (Bhurban, Murree, Pakistan)
7. Should NOT contain: "Azad Kashmir" for cottage location

**Expected Behavior**: ⚠️ **HIGH RISK** - Multiple mentions of Azad Kashmir in chat history

---

### Test Case 5: Location Query with Pronoun Expansion
**Purpose**: Verify pronoun expansion doesn't expand to "Azad Kashmir" from chat history

**Conversation Flow**:
1. User: "nearby attractions"
2. Bot: [Mentions "viewpoints overlooking Azad Kashmir"]
3. User: "where is it located" (pronoun "it" needs expansion)
4. Expected: "it" should expand to "Swiss Cottages", NOT to "Azad Kashmir" or "nearby attractions"
5. Expected: Correct location answer

**Expected Behavior**: ⚠️ **CRITICAL** - Pronoun expansion might pick wrong entity from chat history

---

### Test Case 6: Location Query After Safety Query
**Purpose**: Verify location query after safety query works correctly

**Conversation Flow**:
1. User: "Is it safe?"
2. Bot: [Responds about safety]
3. User: "where is it located"
4. Expected: Correct location (Bhurban, Murree, Pakistan)

**Expected Behavior**: ✅ Should work (safety query doesn't mention Azad Kashmir)

---

### Test Case 7: Location Query After Pricing Query
**Purpose**: Verify location query after pricing query works correctly

**Conversation Flow**:
1. User: "What is the price?"
2. Bot: [Responds about pricing]
3. User: "where is it located"
4. Expected: Correct location (Bhurban, Murree, Pakistan)

**Expected Behavior**: ✅ Should work (pricing query doesn't mention Azad Kashmir)

---

### Test Case 8: Ambiguous Location Query After Attractions
**Purpose**: Verify ambiguous location query doesn't get misinterpreted

**Conversation Flow**:
1. User: "nearby attractions"
2. Bot: [Mentions "viewpoints overlooking Azad Kashmir", "Patriata Chairlift"]
3. User: "where is that located" (ambiguous - could mean attractions or cottages)
4. Expected: Should clarify or default to Swiss Cottages location
5. Should NOT say: "Azad Kashmir" or "Patriata" for cottage location

**Expected Behavior**: ⚠️ **RISK** - Ambiguous pronoun might refer to attractions

---

### Test Case 9: Explicit Location Query After Attractions
**Purpose**: Verify explicit location query works even after attractions query

**Conversation Flow**:
1. User: "nearby attractions"
2. Bot: [Mentions "viewpoints overlooking Azad Kashmir"]
3. User: "where is Swiss Cottages located" (explicit, no pronoun)
4. Expected: Correct location (Bhurban, Murree, Pakistan)
5. Should NOT contain: "Azad Kashmir"

**Expected Behavior**: ✅ Should work (explicit query, no ambiguity)

---

### Test Case 10: Location Query with Chat History Containing Wrong Location
**Purpose**: Verify system corrects wrong location even if chat history contains it

**Conversation Flow**:
1. User: "where is it located"
2. Bot: [WRONG ANSWER: "Bhurban, Azad Kashmir"] (if this happens)
3. User: "where is it located" (asks again)
4. Expected: Should correct to "Bhurban, Murree, Pakistan"
5. Should NOT repeat wrong location

**Expected Behavior**: ⚠️ **RISK** - Chat history might contain wrong answer from previous turn

---

## Test Execution Plan

### Phase 1: Manual Testing
1. Start fresh conversation (no chat history)
2. Execute each test case sequentially
3. Document actual responses
4. Identify which test cases fail

### Phase 2: Automated Testing (if possible)
1. Create test script that simulates conversations
2. Test all scenarios programmatically
3. Verify responses don't contain "Azad Kashmir" for cottage location

### Phase 3: Root Cause Analysis
For each failing test case:
1. Check what documents were retrieved
2. Check what chat history was sent to LLM
3. Check what context was provided to LLM
4. Check if preprocessing worked
5. Check if post-processing caught the issue

---

## Expected Issues to Find

1. **Chat History Contamination**: Previous messages mentioning "Azad Kashmir" influence location answer
2. **Pronoun Expansion**: "it" expands to wrong entity (attractions instead of cottages) ⚠️ **CRITICAL ISSUE FOUND**
   - Current prompt: `REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE` doesn't prevent expanding to "Azad Kashmir"
   - No rule to prioritize "Swiss Cottages" for location queries
   - No rule to exclude "Azad Kashmir" or "Patriata" from pronoun expansion
3. **Context Refinement**: Refined question includes "Azad Kashmir" from chat history
4. **Intent Misclassification**: "where is it located" after attractions query might be classified as asking about attractions
5. **Context Preprocessing**: Preprocessing might not catch all cases
6. **Post-Processing**: Post-processing might not catch all patterns

## Root Cause Analysis

### Issue Found in Code Review

**File**: `chatbot/bot/client/prompt.py:117-182` - `REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE`

**Problem**: The pronoun expansion rules don't prevent expanding to forbidden locations:
- No rule to exclude "Azad Kashmir" from pronoun expansion
- No rule to exclude "Patriata" from pronoun expansion  
- No rule to prioritize "Swiss Cottages Bhurban" for location queries
- If chat history mentions "viewpoints overlooking Azad Kashmir", pronoun "it" might expand to "Azad Kashmir"

**Example Failure Scenario**:
1. User: "nearby attractions"
2. Bot: "viewpoints overlooking Azad Kashmir"
3. User: "where is it located"
4. **Current behavior**: Pronoun expansion might expand "it" to "Azad Kashmir" or "nearby attractions"
5. **Expected behavior**: Pronoun expansion should expand "it" to "Swiss Cottages Bhurban"

---

## Success Criteria

✅ **Test passes if**:
- Answer contains correct location: "Bhurban, Murree, Pakistan" or "Murree Hills, Bhurban, Pakistan"
- Answer does NOT contain "Azad Kashmir" for cottage location
- Answer does NOT contain "Patriata" for cottage location
- Answer does NOT contain "Bhubaneswar" for cottage location

❌ **Test fails if**:
- Answer contains "Azad Kashmir" for cottage location
- Answer contains "Bhurban, Azad Kashmir"
- Answer contains "located in Azad Kashmir"
- Answer contains "gated community in Bhurban, Azad Kashmir"

---

## Next Steps After Testing

1. Document all failing test cases
2. Identify root causes for each failure
3. Propose fixes based on findings
4. Implement fixes
5. Re-test all scenarios
6. Verify fixes work
