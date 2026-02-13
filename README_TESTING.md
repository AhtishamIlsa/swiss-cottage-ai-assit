# Testing Guide: Location Contamination and Chat History Issues

## Overview

This test suite validates that the chatbot correctly handles:
1. Location queries without contamination from chat history
2. Pronoun expansion to correct entities
3. Sequential queries that don't contaminate each other
4. Forbidden locations (Azad Kashmir, Patriata, Bhubaneswar) don't appear in answers

## Test Script

### Running the Tests

```bash
# Make sure the API is running
# Then run the test script
python3 test_location_contamination.py
```

### Test Categories

#### 1. Location Contamination Tests (TC1-TC6)
- Direct location queries
- Location queries after facilities/attractions queries
- Pronoun expansion tests
- Multiple Azad Kashmir mentions

#### 2. Safety Queries (TC7-TC10)
- Direct safety queries
- Safety queries after other queries
- Safety for each cottage

#### 3. Reasoning Queries (TC11-TC15)
- Group size queries ("We are 7 people, which cottage is suitable?")
- Reasoning queries followed by pricing/availability/location

#### 4. Pricing Queries (TC16-TC19)
- Direct pricing queries
- Pricing queries after other queries

#### 5. Availability Queries (TC20-TC22)
- Direct availability queries
- Availability queries after other queries

#### 6. Booking Queries (TC23-TC25)
- Direct booking queries
- Booking queries after other queries

#### 7. Complex Sequential Queries (TC26-TC30)
- Full booking flow (Group Size → Pricing → Availability → Booking)
- Multiple sequential queries
- High contamination risk scenarios

## Critical Test Cases

These tests are marked as **critical** and must pass:

- **TC3**: Location After Nearby Attractions Query
- **TC4**: Location After Multiple Azad Kashmir Mentions
- **TC5**: Location Query with Pronoun After Attractions
- **TC12**: Reasoning Query - Group Size 7 Then Pricing
- **TC13**: Reasoning Query - Group Size 7 Then Availability
- **TC14**: Reasoning Query - Group Size 7 Then Location
- **TC26**: Full Booking Flow
- **TC27**: Attractions → Location → Safety → Pricing
- **TC28**: Facilities → Attractions → Location
- **TC29**: Group Size → Attractions → Location → Pricing
- **TC30**: Multiple Location Queries

## Expected Results

### ✅ Pass Criteria
- No forbidden locations in answers
- Correct location patterns found (for location queries)
- Expected keywords present
- No errors

### ❌ Fail Criteria
- Forbidden locations found (Azad Kashmir, Patriata, Bhubaneswar, etc.)
- Correct location pattern not found (for location queries)
- API errors
- Unexpected behavior

### ⚠️ Warning Criteria
- Expected keywords not found
- Correct location pattern not found (for non-location queries)

## Configuration

Edit the script to adjust:
- `API_BASE_URL`: API base URL (default: "http://localhost:8000")
- `FORBIDDEN_LOCATIONS`: List of forbidden locations
- `CORRECT_LOCATION_PATTERNS`: List of correct location patterns

## Interpreting Results

### Example Output

```
================================================================================
Test: TC3: Location After Nearby Attractions Query (CRITICAL)
Description: Location query after nearby attractions query - most likely to fail
================================================================================

[Turn 1] User: nearby attractions
[Turn 1] Bot: Guests can visit Chinar Golf Club, PC Bhurban, Governor House Bhurban...

[Turn 2] User: where is it located
[Turn 2] Bot: Swiss Cottages is located adjacent to Pearl Continental (PC) Bhurban...
✅ Correct location found
✅ Expected keywords found: ['bhurban', 'murree', 'pakistan']
✅ PASS
```

### Summary

```
================================================================================
TEST SUMMARY
================================================================================

Total Tests: 30
✅ Passed: 28
❌ Failed: 2
⚠️  Warnings: 0
⏭️  Skipped: 0

Critical Tests: 11
✅ Passed: 9
❌ Failed: 2
```

## Troubleshooting

### API Connection Issues
- Ensure the API is running: `curl http://localhost:8000/api/health`
- Check API_BASE_URL in the script

### Test Failures
1. Check the actual answer in the test output
2. Look for forbidden locations
3. Check if correct location pattern is present
4. Review chat history contamination

### Common Issues

1. **Forbidden Location Found**
   - Check context preprocessing
   - Check post-processing rules
   - Check pronoun expansion rules

2. **Correct Location Not Found**
   - Check if location query was classified correctly
   - Check if correct documents were retrieved
   - Check prompt templates

3. **Pronoun Expansion Issues**
   - Check `REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE`
   - Verify pronoun expansion rules are working

## Manual Testing

For manual testing, use this sequence:

1. Start a conversation
2. Ask: "nearby attractions"
3. Then ask: "where is it located"
4. Verify answer does NOT contain "Azad Kashmir" for cottage location
5. Verify answer contains "Bhurban, Murree, Pakistan" or similar

## Adding New Test Cases

To add new test cases, edit `create_test_cases()` function:

```python
test_cases.append(TestCase(
    name="TC31: Your Test Name",
    description="Description of what you're testing",
    conversation=[
        ("First query", ["expected", "keywords"]),
        ("Second query", ["expected", "keywords"])
    ],
    expected_behavior="What should happen",
    critical=True  # or False
))
```

## Notes

- Each test uses a unique session ID to avoid cross-contamination
- Tests include delays between requests to avoid rate limiting
- Critical tests must pass for the system to be considered working correctly
