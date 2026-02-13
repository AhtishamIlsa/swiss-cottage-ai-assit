# Diagnostic Report: "Azad Kashmir" Location Issue

## Root Cause Found

### The Problem
The FAQ documents contain "Azad Kashmir" in the **CORRECT** context:
- ✅ "viewpoints **overlooking** Azad Kashmir" (correct - viewpoints can see Azad Kashmir)
- ✅ "Azad Kashmir View Point (near PC Bhurban)" (correct - this is a viewpoint name)
- ✅ "scenic viewpoints **overlooking** Azad Kashmir" (correct - you can see Azad Kashmir from viewpoints)

### The Issue
The LLM is **misinterpreting** the context and generating:
- ❌ "Our cozy cottage is located within a gated community in Bhurban, **Azad Kashmir**" (WRONG)
- ❌ "Swiss Cottages is located in **Bhurban, Azad Kashmir**" (WRONG)

### Why This Happens
1. **Context contains "Azad Kashmir"** - LLM sees this phrase in retrieved documents
2. **LLM infers wrong meaning** - It thinks "Azad Kashmir" means the cottages are IN Azad Kashmir
3. **Context says "overlooking"** - But LLM ignores the word "overlooking" and focuses on "Azad Kashmir"
4. **Post-processing may not catch it** - The `fix_incorrect_location_mentions()` function might not catch all patterns

## Files Containing "Azad Kashmir" (Correct Context)

1. `docs/faq/location_surroundings_faq_065.md`:
   - "Azad Kashmir View Point (near PC Bhurban)" ✅

2. `docs/faq/location_surroundings_faq_066.md`:
   - "scenic viewpoints **overlooking** Azad Kashmir" ✅

3. `docs/faq/location_surroundings_faq_071.md`:
   - "visiting viewpoints **overlooking** Azad Kashmir" ✅

4. `docs/faq/location_surroundings_faq_073.md`:
   - "scenic viewpoints **overlooking** Azad Kashmir" ✅

## Current Fixes in Place

1. **Prompt Rules** (`chatbot/bot/client/prompt.py`):
   - Multiple prohibitions against saying "Azad Kashmir" for location
   - Rule: "PC Bhurban overlooks Azad Kashmir, but cottages are in Murree Hills"

2. **Post-Processing** (`chatbot/api/main.py:1133-1196`):
   - `fix_incorrect_location_mentions()` function
   - Pattern matching to replace "Azad Kashmir" with correct location
   - But may not catch all variations

## Why Fixes Aren't Working

1. **LLM sees "Azad Kashmir" in context** → Generates it in answer
2. **Post-processing may miss patterns** like "Bhurban, Azad Kashmir" if formatted differently
3. **Context preprocessing missing** → No clarification added to context before sending to LLM

## Solution Needed

1. **Add context preprocessing** to clarify "overlooking Azad Kashmir" means you can SEE it, not that you're IN it
2. **Strengthen post-processing** to catch more patterns
3. **Add explicit clarification in prompts** about "overlooking" vs "located in"
