---
name: Intent-Based Architecture Fix
overview: Refactor the chatbot from a "recall-first, control-last" architecture to an "intent-first, gate-then-retrieve" architecture. This will enforce strict boundaries between intents, prevent pricing leakage, reduce response length, and make the system deterministic and reliable.
todos:
  - id: phase1-intent-metadata
    content: "Phase 1: Refactor enrich_faq_metadata.py to classify intent DURING Excel extraction - Move intent classification into extract_faq_from_excel(), extract cottage_id, include intent in initial markdown frontmatter"
    status: completed
  - id: phase2-intent-filtering
    content: "Phase 2: Implement intent-first retrieval with query optimization and metadata filtering - Extract entities, optimize query based on intent (rule-based + optional LLM), build metadata filter, use filter in retrieval, remove post-retrieval filtering"
    status: completed
    dependencies:
      - phase1-intent-metadata
  - id: phase3-split-prompts
    content: "Phase 3: Split prompts by intent - Create separate prompt templates (PRICING, AVAILABILITY, SAFETY, etc.), each with explicit allowlist/denylist and length constraints"
    status: completed
    dependencies:
      - phase2-intent-filtering
  - id: phase4-gate-context
    content: "Phase 4: Gate context before prompt - Create fact injector function, inject closed-world facts before prompt generation"
    status: completed
    dependencies:
      - phase3-split-prompts
  - id: phase5-hybrid-reasoning
    content: "Phase 5: Hybrid reasoning approach - Handlers do simple/deterministic reasoning (extract entities, calculate), LLM reasoning model handles complex reasoning, LLM phrases final answers"
    status: completed
    dependencies:
      - phase4-gate-context
  - id: phase6-length-control
    content: "Phase 6: Response length control - Add explicit length constraints per intent in prompts (2-8 sentences depending on intent, with direct answer + brief explanation)"
    status: completed
    dependencies:
      - phase5-hybrid-reasoning
  - id: rebuild-vector-store
    content: Rebuild vector store with intent metadata - Remove old vector store files first, then extract FAQs from Excel using refactored enrich_faq_metadata.py, generate markdown files with intent, rebuild vector store from scratch
    status: completed
    dependencies:
      - phase1-intent-metadata
  - id: testing-validation
    content: Testing and validation - Verify no pricing leakage, concise responses, deterministic answers, no hallucinations
    status: completed
    dependencies:
      - phase6-length-control
      - rebuild-vector-store
---

# Intent-Based Architecture Refactoring Plan

## CRITICAL: Constraints and Requirements

**IMPORTANT - DO NOT CHANGE DEPENDENCY VERSIONS:**

- **DO NOT upgrade or downgrade any package versions** (ChromaDB, pandas, openpyxl, or any other dependencies)
- Use existing versions of all libraries and packages
- All implementations must work with current dependency versions
- If a feature requires a version change, find an alternative approach that works with current versions

## CRITICAL: Current System Analysis

**Key Findings from Code Review:**

1. **DirectoryLoader doesn't parse YAML frontmatter** (`chatbot/document_loader/loader.py:86-88`)

                                                                                                                                                                                                - Currently reads entire markdown file (including frontmatter) as `page_content`
                                                                                                                                                                                                - Metadata from YAML frontmatter is NOT extracted
                                                                                                                                                                                                - **Impact**: Even if markdown files have intent metadata, it won't be in chunks
                                                                                                                                                                                                - **Fix Required**: Add frontmatter parsing in `load_file()` method

2. **similarity_search_with_threshold doesn't support filter** (`chatbot/bot/memory/vector_database/chroma.py:475-523`)

                                                                                                                                                                                                - Current method signature: `similarity_search_with_threshold(query, k, threshold)` - no filter parameter
                                                                                                                                                                                                - But `similarity_search_with_score(query, k, filter=...)` DOES support filter (line 544)
                                                                                                                                                                                                - **Fix Required**: Either add filter parameter to `similarity_search_with_threshold()` OR use `similarity_search_with_score()` with threshold logic

3. **INTENT_TO_SLOTS still uses "room_type"** (`chatbot/scripts/enrich_faq_metadata.py:69-102`)

                                                                                                                                                                                                - Lines 71, 75, 80, 84, 88 still use `"room_type"` instead of `"cottage_id"`
                                                                                                                                                                                                - **Fix Required**: Replace all `"room_type"` with `"cottage_id"` in INTENT_TO_SLOTS and SLOT_HINTS

4. **rebuild_vector_store.py doesn't parse frontmatter** (`rebuild_vector_store.py:20-48`)

                                                                                                                                                                                                - Only extracts metadata from filename, not from YAML frontmatter
                                                                                                                                                                                                - **Fix Required**: Add frontmatter parsing similar to DirectoryLoader

5. **Good news**: `rebuild_vector_store.py` already removes old vector store (lines 90-94) ✅

## CRITICAL: Slot Terminology Clarification

**IMPORTANT**: When implementing slot extraction in `enrich_faq_metadata.py`:

1. **`cottage_id`** - Use this slot for cottage types/numbers: 7, 9, or 11

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Cottage 7, Cottage 9, Cottage 11 → `cottage_id` slot
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - These are cottage identifiers, NOT room types

2. **`room_type`** - Does NOT mean cottage type

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Cottage types (7, 9, 11) should NEVER be mapped to `room_type` slot
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - If `room_type` is used, it refers to something else (e.g., room categories within a cottage), NOT cottage numbers

3. **When refactoring `enrich_faq_metadata.py`**:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - In `INTENT_TO_SLOTS` mapping, replace `room_type` with `cottage_id` for slots that refer to cottage types
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - When extracting cottage numbers (7, 9, 11), store them in `cottage_id` slot, NOT `room_type`
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Update slot extraction hints: `"cottage_id": "cottage 7, 9, or 11"` (NOT "room_type")

4. **Example correction**:
   ```python
   # WRONG:
   "pricing": {
       "required": ["guests", "dates", "room_type"],  # ❌ room_type is wrong
   }
   
   # CORRECT:
   "pricing": {
       "required": ["guests", "dates", "cottage_id"],  # ✅ cottage_id is correct
   }
   ```


## Problem Analysis

Your current system has these critical issues:

1. **Monolithic Prompt (999 lines)** - `chatbot/bot/client/prompt.py` tries to enforce 200+ rules via prompts
2. **Recall-First Retrieval** - Retrieves all documents, then tries to filter/prioritize AFTER retrieval
3. **No Intent-Based Filtering** - ChromaDB supports metadata filtering but it's never used
4. **Handlers Run After Retrieval** - Pricing/capacity/availability handlers enhance context but don't prevent irrelevant docs from being retrieved
5. **No Intent Metadata** - Chunks don't have intent tags, so filtering by intent is impossible
6. **Single Prompt for All Intents** - One huge prompt tries to handle everything

## Solution Architecture

### Phase 1: Add Intent Metadata to Chunks

**Files to modify:**

- `chatbot/scripts/enrich_faq_metadata.py` - **REFACTOR**: Classify intent DURING Excel extraction (not after)
- `chatbot/document_loader/loader.py` - **CRITICAL**: Parse YAML frontmatter to extract metadata (currently doesn't parse it)
- `chatbot/memory_builder.py` - Ensure frontmatter metadata is preserved when chunking
- `rebuild_vector_store.py` - Update to parse frontmatter metadata

**CRITICAL FINDINGS:**

1. **DirectoryLoader doesn't parse YAML frontmatter** - Currently reads entire markdown file as content, including frontmatter. Metadata from frontmatter is NOT extracted.
2. **Must add frontmatter parsing** - Need to extract intent, cottage_id, category from YAML frontmatter during loading
3. **INTENT_TO_SLOTS uses "room_type"** - Must change to "cottage_id" in enrich_faq_metadata.py

**Changes:**

1. **Refactor `enrich_faq_metadata.py`** to classify intent during Excel extraction:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Move `determine_intent_from_faq()` call INSIDE `extract_faq_from_excel()` function
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Classify intent for each FAQ row as it's extracted from Excel
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Extract `cottage_id` (7, 9, 11, or None) from question/answer text during extraction
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Include intent and cottage_id in the qa_pair dictionary immediately
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **FIX SLOT TERMINOLOGY**: Replace `room_type` with `cottage_id` in `INTENT_TO_SLOTS` mapping

2. **Update `generate_markdown_files()`** to include intent in initial frontmatter:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Add `intent` field to frontmatter from qa_pair
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Add `cottage_id` field to frontmatter if present
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Include `required_slots` and `optional_slots` based on intent (using `cottage_id`, NOT `room_type`)

3. **Intent classification logic** (already exists in `determine_intent_from_faq()`):

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `pricing` - Pricing & Payments category, questions with pricing keywords
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `availability` - Availability & Dates category, questions about booking/availability
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `safety` - Safety & Security category, questions about safety/security
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `rooms` - **Cottage types/properties** (Properties & Spaces category, "tell me about cottage X")
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **IMPORTANT**: "rooms" intent refers to **cottage types** (Cottage 7, 9, 11), NOT individual rooms within cottages
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - This intent is about cottage descriptions, properties, and cottage types
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **CRITICAL**: Cottage types (7, 9, 11) are NOT room types - use `cottage_id` slot, NOT `room_type` slot
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `facilities` - Facilities & Amenities category
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `location` - Location & Surroundings category
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `faq_question` - Everything else (general)

4. **Cottage ID extraction** - Add function to extract cottage numbers (7, 9, 11) from question/answer:
   ```python
   def extract_cottage_id(question: str, answer: str) -> Optional[int]:
       """Extract cottage number (7, 9, or 11) from question/answer text.
       Returns cottage_id, NOT room_type. Cottage types are NOT room types."""
       text = (question + " " + answer).lower()
       for num in [7, 9, 11]:
           if f"cottage {num}" in text or f"cottage{num}" in text:
               return num
       return None
   ```

5. **Updated markdown frontmatter structure**:
   ```yaml
   ---
   intent: pricing
   cottage_id: 9
   category: Pricing & Payments
   faq_id: faq_084
   required_slots: [guests, dates, cottage_id]
   optional_slots: [season]
   ---
   ```


**Note**: Uses `cottage_id` slot, NOT `room_type` slot

6. **Workflow**:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Read Excel file (`Swiss Cottages FAQS.xlsx`)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - For each row: Extract Q&A → Classify intent → Extract cottage_id → Create qa_pair with intent
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Generate markdown files with intent already in frontmatter
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - When vector store is built, chunks will automatically have intent metadata

**Detailed Refactoring Steps for `enrich_faq_metadata.py`:**

1. **Fix `INTENT_TO_SLOTS` mapping** - Replace `room_type` with `cottage_id` (CURRENTLY STILL USES room_type):
   ```python
   # CURRENT STATE (lines 69-102 in enrich_faq_metadata.py):
   # ❌ STILL WRONG - uses "room_type"
   INTENT_TO_SLOTS = {
       "pricing": {
           "required": ["guests", "dates", "room_type"],  # ❌ WRONG
       },
       # ...
   }
   
   # FIXED VERSION:
   INTENT_TO_SLOTS = {
       "pricing": {
           "required": ["guests", "dates", "cottage_id"],  # ✅ Changed from room_type
           "optional": ["season"],
       },
       "booking": {
           "required": ["guests", "dates", "cottage_id", "family"],  # ✅ Changed from room_type
           "optional": ["season"],
       },
       "availability": {
           "required": ["dates"],
           "optional": ["guests", "cottage_id"],  # ✅ Changed from room_type
       },
       "rooms": {
           "required": [],
           "optional": ["guests", "cottage_id"],  # ✅ Changed from room_type
       },
       "facilities": {
           "required": [],
           "optional": ["cottage_id"],  # ✅ Changed from room_type
       },
       # ... etc
   }
   ```

2. **Fix `SLOT_HINTS` mapping** (CURRENTLY STILL USES room_type):
   ```python
   # CURRENT STATE (lines 106-112 in enrich_faq_metadata.py):
   # ❌ STILL WRONG - uses "room_type"
   SLOT_HINTS = {
       "room_type": "cottage 7, 9, or 11",  # ❌ WRONG - should be cottage_id
   }
   
   # FIXED VERSION:
   SLOT_HINTS = {
       "guests": "number of guests or people",
       "cottage_id": "cottage 7, 9, or 11",  # ✅ Changed from room_type
       "dates": "check-in and check-out dates",
       "family": "whether booking is for family or friends",
       "season": "weekday, weekend, peak, or off-peak",
   }
   ```

3. **Add cottage_id extraction function** (before `extract_faq_from_excel`):
   ```python
   def extract_cottage_id(question: str, answer: str) -> Optional[int]:
       """Extract cottage number (7, 9, or 11) from question/answer text.
       Returns cottage_id, NOT room_type. Cottage types are NOT room types."""
       text = (question + " " + answer).lower()
       for num in [7, 9, 11]:
           if f"cottage {num}" in text or f"cottage{num}" in text:
               return num
       return None
   ```

4. **Modify `extract_faq_from_excel()` function**:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Inside the loop where qa_pair is created (around line 500):
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Call `determine_intent_from_faq()` with category, question, and answer
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Call `extract_cottage_id()` with question and answer (returns cottage_id, NOT room_type)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Add `intent` and `cottage_id` to qa_pair dictionary
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Get slots using `get_slots_for_intent(intent)` (which now uses `cottage_id`, NOT `room_type`)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Add `required_slots` and `optional_slots` to qa_pair

5. **Modify `generate_markdown_files()` function**:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - In frontmatter generation (around line 536):
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Add `intent: "{qa_pair.get('intent', 'faq_question')}"`
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Add `cottage_id: {qa_pair.get('cottage_id')}` if present (or omit if None)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Add `required_slots: {qa_pair.get('required_slots', [])}` (will contain `cottage_id`, NOT `room_type`)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Add `optional_slots: {qa_pair.get('optional_slots', [])}`

6. **Remove separate enrichment step** - Since intent is classified during extraction, the `enrich_faq_file()` function is no longer needed for new extractions (but keep it for backward compatibility with existing files)

7. **CRITICAL: Update DirectoryLoader to parse YAML frontmatter**:

                                                                                                                                                                                                - Current issue: `DirectoryLoader.load_file()` (line 86-88) reads entire markdown file as content
                                                                                                                                                                                                - Frontmatter metadata (intent, cottage_id, category) is NOT extracted
                                                                                                                                                                                                - Solution: Add frontmatter parsing in `load_file()` method:
   ```python
   def load_file(self, doc_path: Path, docs: list[Document], pbar: Any | None) -> None:
       if doc_path.suffix.lower() == '.md':
           text = doc_path.read_text(encoding='utf-8')
           
           # Parse YAML frontmatter if present
           metadata = {"source": str(doc_path)}
           frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
           match = re.match(frontmatter_pattern, text, re.DOTALL)
           
           if match:
               frontmatter_text = match.group(1)
               content_text = match.group(2)
               try:
                   import yaml
                   frontmatter = yaml.safe_load(frontmatter_text) or {}
                   # Extract metadata from frontmatter
                   metadata.update({
                       "intent": frontmatter.get("intent"),
                       "cottage_id": frontmatter.get("cottage_id"),
                       "category": frontmatter.get("category"),
                       "faq_id": frontmatter.get("faq_id"),
                       "type": frontmatter.get("type", "document"),
                   })
                   # Use content without frontmatter
                   text = content_text
               except Exception as e:
                   logger.warning(f"Failed to parse frontmatter for {doc_path}: {e}")
           
           docs.extend([Document(page_content=text, metadata=metadata)])
   ```


8. **Update rebuild_vector_store.py** - Add frontmatter parsing:

                                                                                                                                                                                                - Currently only extracts metadata from filename (line 28-39)
                                                                                                                                                                                                - Must also parse YAML frontmatter to get intent, cottage_id
                                                                                                                                                                                                - Use same parsing logic as DirectoryLoader

### Phase 2: Intent-First Retrieval with Query Optimization and Metadata Filtering

**Files to modify:**

- `chatbot/api/main.py` - Add query optimization, use metadata filters in retrieval
- `chatbot/bot/memory/vector_database/chroma.py` - **ADD filter parameter** to `similarity_search_with_threshold()` OR use `similarity_search_with_score()` which already supports filter
- `chatbot/bot/conversation/query_optimizer.py` - Create/update query optimization module

**IMPORTANT**:

- Use existing ChromaDB API for metadata filtering. Do NOT upgrade/downgrade ChromaDB version.
- `similarity_search_with_score()` already supports `filter` parameter (line 544 in chroma.py)
- `similarity_search_with_threshold()` does NOT support filter - need to add it or use alternative method

**Changes:**

1. **Detect intent BEFORE retrieval** (already done via `intent_router.classify()`)

2. **Extract entities BEFORE retrieval** (rule-based, fast):
   ```python
   def extract_entities_for_retrieval(query: str) -> dict:
       """Extract entities from query for better retrieval filtering."""
       entities = {
           "cottage_id": None,
           "dates": None,
           "group_size": None
       }
       
       # Extract cottage_id
       query_lower = query.lower()
       for num in [7, 9, 11]:
           if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
               entities["cottage_id"] = num
               break
       
       # Extract group size (numbers with "people", "guests", "members")
       # Extract dates (date patterns)
       # ... (implement date and group_size extraction)
       
       return entities
   ```

3. **Optimize query based on intent** (hybrid approach - rule-based first, LLM optional):
   ```python
   def optimize_query_for_retrieval(
       query: str, 
       intent: IntentType, 
       entities: dict,
       use_llm: bool = False
   ) -> str:
       """Optimize query for better vector retrieval."""
       
       # Stage 1: Rule-based intent-specific enhancement (always)
       enhanced_query = query
       
       # Add domain terms based on intent
       intent_terms = {
           IntentType.PRICING: ["PKR", "weekday", "weekend", "per night", "rate", "cost"],
           IntentType.AVAILABILITY: ["available", "booking", "vacancy", "dates"],
           IntentType.SAFETY: ["security", "guards", "gated community", "safe"],
           IntentType.ROOMS: ["cottage", "bedroom", "property", "accommodation"],
           IntentType.FACILITIES: ["facility", "amenity", "kitchen", "terrace"],
           IntentType.LOCATION: ["location", "nearby", "attractions", "Bhurban"],
       }
       
       if intent in intent_terms:
           # Add relevant domain terms to query
           terms = intent_terms[intent]
           enhanced_query = f"{query} {' '.join(terms)}"
       
       # Add extracted entities to query
       if entities.get("cottage_id"):
           enhanced_query = f"{enhanced_query} cottage {entities['cottage_id']}"
       
       # Stage 2: Optional LLM optimization (only for complex/ambiguous queries)
       if use_llm:
           # Use existing QUERY_OPTIMIZATION_PROMPT_TEMPLATE
           # Only call LLM if query is ambiguous or entity extraction failed
           enhanced_query = llm_optimize_query(enhanced_query, intent)
       
       return enhanced_query
   ```

4. **Build metadata filter based on intent and entities:**
   ```python
   def get_retrieval_filter(intent: IntentType, entities: dict) -> dict:
       """Build metadata filter for vector retrieval."""
       base_filter = {"intent": intent.value}
       
       # Add cottage_id filter if extracted
       if entities.get("cottage_id"):
           base_filter["cottage_id"] = str(entities["cottage_id"])
       
       return base_filter
   ```

5. **Updated retrieval flow:**
   ```python
   # NEW FLOW:
   # 1. Detect intent
   intent = intent_router.classify(user_query)
   
   # 2. Extract entities (rule-based, fast)
   entities = extract_entities_for_retrieval(user_query)
   
   # 3. Optimize query (rule-based enhancement + optional LLM)
   optimized_query = optimize_query_for_retrieval(
       user_query, 
       intent, 
       entities,
       use_llm=is_complex_query(user_query)  # Only use LLM for complex queries
   )
   
   # 4. Build metadata filter
   retrieval_filter = get_retrieval_filter(intent, entities)
   
   # 5. Retrieve with intent filter - **CRITICAL**: similarity_search_with_threshold doesn't support filter
   # Use similarity_search_with_score which supports filter, then apply threshold
   docs_and_scores = vector_store.similarity_search_with_score(
       query=optimized_query,
       k=effective_k * 3,
       filter=retrieval_filter  # NEW - only retrieves relevant intents
   )
   
   # Apply threshold (0.0 means no threshold, but keep for compatibility)
   threshold = 0.0
   if threshold is not None:
       # Note: ChromaDB returns distance scores (lower = more similar)
       # Convert to similarity scores if needed, or filter by distance
       docs_and_scores = [(doc, score) for doc, score in docs_and_scores if score <= threshold]
   
   # Format as tuple to match existing code
   retrieved_contents = [doc for doc, _ in docs_and_scores]
   sources = [{
       "score": round(score, 3),
       "document": doc.metadata.get("source"),
       "content_preview": f"{doc.page_content[0:256]}..."
   } for doc, score in docs_and_scores]
   result = (retrieved_contents, sources)
   
   # ALTERNATIVE: Add filter parameter to similarity_search_with_threshold() in chroma.py
   # Then can use: result = vector_store.similarity_search_with_threshold(
   #     query=optimized_query, k=effective_k * 3, threshold=0.0, filter=retrieval_filter
   # )
   ```

6. **Remove post-retrieval filtering** - Delete `filter_pricing_from_context()` since pricing docs won't be retrieved for non-pricing queries

**Benefits:**

- **Faster**: Rule-based entity extraction and query enhancement are fast
- **Better retrieval**: Intent-aware query enhancement improves semantic matching
- **Lower cost**: LLM optimization only for complex/ambiguous queries
- **More reliable**: Entity extraction before retrieval enables better filtering
- **Intent boundaries**: Query optimization respects intent boundaries

### Phase 3: Split Prompts by Intent

**Files to modify:**

- `chatbot/bot/client/prompt.py` - Split into intent-specific prompts

**Changes:**

1. Create separate prompt templates:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `PRICING_PROMPT_TEMPLATE` - Only allows pricing fields, explicitly forbids other topics
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `AVAILABILITY_PROMPT_TEMPLATE` - Only allows availability info, no pricing
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `SAFETY_PROMPT_TEMPLATE` - Only safety/security info, no pricing
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `ROOMS_PROMPT_TEMPLATE` - Only cottage types/properties info (Cottage 7, 9, 11 descriptions), no pricing
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **Note**: "rooms" intent = cottage types/properties, NOT individual rooms within cottages
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `FACILITIES_PROMPT_TEMPLATE` - Only facilities/amenities, no pricing
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `LOCATION_PROMPT_TEMPLATE` - Only location/attractions, no pricing
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `GENERAL_PROMPT_TEMPLATE` - General info, no pricing unless asked

2. Each prompt should be SHORT (50-100 lines max) with:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Closed-world facts injection (cottage IDs, base facts)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Explicit field allowlist
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Explicit field denylist
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Response length constraints

3. Example structure:
   ```python
   PRICING_PROMPT_TEMPLATE = """Context information is below.
   ---------------------
   {context}
   ---------------------
   
   SYSTEM FACTS (AUTHORITATIVE):
   - Only cottages: 7, 9, 11
   - No other cottages exist
   - Do not invent entities
   
   ALLOWED FIELDS:
   - Pricing (PKR only)
   - Weekday/weekend rates
   - Total cost calculations
   - Number of nights
   
   FORBIDDEN FIELDS:
   - Capacity information (unless asked)
   - Availability details (unless asked)
   - Safety information
   - Location details
   
   RESPONSE LENGTH: Maximum 3-5 sentences. Provide direct answer first (manager-style), then brief explanation. Be concise but informative.
   
   Question: {question}
   Answer:"""
   ```


### Phase 4: Gate Context Before Prompt

**Files to modify:**

- `chatbot/api/main.py` - Inject closed-world facts before prompt generation

**Changes:**

1. Create fact injector function:
   ```python
   def inject_closed_world_facts(context: str, intent: IntentType, cottage_id: Optional[int]) -> str:
       facts = [
           "SYSTEM FACTS (AUTHORITATIVE):",
           "- Only cottages: 7, 9, 11",
           "- No other cottages exist",
           "- Do not invent entities"
       ]
       if cottage_id:
           facts.append(f"- Current query is about Cottage {cottage_id}")
       return "\n".join(facts) + "\n\n" + context
   ```

2. Inject facts BEFORE passing to prompt template

### Phase 5: Hybrid Reasoning Approach

**Files to modify:**

- `chatbot/bot/conversation/pricing_handler.py` - Keep simple calculations, delegate complex reasoning to LLM
- `chatbot/bot/conversation/capacity_handler.py` - Keep simple checks, delegate complex reasoning to LLM
- `chatbot/api/main.py` - Use hybrid approach: handlers for simple reasoning, LLM reasoning model for complex tasks

**IMPORTANT**: You have `REASONING_MODEL_NAME=openai/gpt-oss-20b` configured. Use this reasoning model for complex reasoning tasks.

**Changes:**

1. **Handlers do simple/deterministic reasoning** - Pricing/capacity/availability handlers should:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Extract entities (cottage_id, dates, group_size) - **Rule-based, fast**
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Perform simple calculations (pricing math, basic capacity checks) - **Deterministic**
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Return structured data for LLM to reason about

2. **LLM reasoning model handles complex reasoning** - Use `REASONING_MODEL_NAME` for:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Complex capacity analysis (e.g., "which cottage is best for 8 people with 2 kids")
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Multi-factor recommendations (e.g., "best cottage considering price, capacity, and location")
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Contextual reasoning (e.g., "is this suitable for a family vs friends group")
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Date-based availability reasoning (e.g., "what's available during peak season")
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Any reasoning that requires understanding context, trade-offs, or multiple factors

3. **LLM phrases the final answer** - After reasoning, LLM formats the answer:
   ```python
   # Simple case: Handler did calculation, LLM just phrases
   if pricing_result.get("simple_calculation"):
       prompt = PRICING_PROMPT_TEMPLATE.format(
           context=injected_context,
           question=request.question,
           calculation_result=pricing_result["calculation"]  # Simple math result
       )
   
   # Complex case: Use reasoning model for complex reasoning
   elif pricing_result.get("needs_complex_reasoning"):
       # Use REASONING_MODEL_NAME for complex reasoning
       reasoning_result = reasoning_model.reason(
           context=injected_context,
           question=request.question,
           structured_data=pricing_result["data"]
       )
       # Then phrase the answer
       prompt = PRICING_PROMPT_TEMPLATE.format(
           context=injected_context,
           question=request.question,
           reasoning_result=reasoning_result
       )
   ```

4. **When to use reasoning model**:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **Use reasoning model when**: Query requires understanding context, making recommendations, analyzing trade-offs, or complex multi-factor decisions
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **Use handlers when**: Simple calculations, entity extraction, or deterministic logic
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **Always use LLM for phrasing**: Final answer formatting should use LLM for natural language

5. **Benefits of hybrid approach**:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **Faster**: Simple tasks handled by handlers (no LLM call needed)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **Better reasoning**: Complex tasks use specialized reasoning model
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **Lower cost**: Only use reasoning model when needed
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **More reliable**: Deterministic handlers for simple cases, LLM for complex cases

### Phase 6: Response Length Control

**Files to modify:**

- All intent-specific prompts in `chatbot/bot/client/prompt.py`

**Changes:**

1. Add explicit length constraints per intent:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Pricing: 3-5 sentences (direct price breakdown + brief explanation)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Availability: 2-3 sentences (yes/no + contact info + brief note)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Safety: 4-6 sentences (key safety points with brief context)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Cottage description: 4-6 sentences (features + capacity + brief context)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - General: 5-8 sentences (comprehensive but concise)

2. Add to each prompt:
   ```
   RESPONSE LENGTH: Maximum X sentences. Provide direct answer first (manager-style), then brief explanation. Be concise but informative.
   ```


## Implementation Order

1. **Phase 1** - Add intent metadata (enables everything else)
2. **Phase 2** - Intent-based retrieval with query optimization (prevents irrelevant docs, improves retrieval quality)

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Extract entities before retrieval
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Optimize query based on intent (rule-based enhancement + optional LLM)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Use metadata filters in retrieval

3. **Phase 3** - Split prompts (enforces boundaries)
4. **Phase 4** - Gate context (prevents hallucinations)
5. **Phase 5** - Hybrid reasoning (handlers for simple tasks, LLM reasoning model for complex tasks)
6. **Phase 6** - Length control (makes responses concise)

## Expected Outcomes

- **No pricing leakage** - Pricing docs won't be retrieved for non-pricing queries
- **Better retrieval quality** - Intent-aware query optimization improves semantic matching
- **Faster retrieval** - Rule-based entity extraction and query enhancement are fast
- **Lower cost** - LLM optimization only for complex queries, not every query
- **Shorter responses** - Explicit length constraints per intent
- **Hybrid reasoning** - Handlers do simple/deterministic reasoning, LLM reasoning model handles complex reasoning, LLM phrases answers
- **Faster responses** - Less context = faster generation
- **More reliable** - Intent boundaries enforced at retrieval time, not prompt time

## Migration Strategy

1. **Backward compatibility** - Keep old prompts during transition
2. **Feature flag** - Add `USE_INTENT_FILTERING` env var to toggle new system
3. **Gradual rollout** - Test with one intent first (e.g., PRICING), then expand
4. **Rebuild vector store** - Required to add intent metadata to existing chunks

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **IMPORTANT**: Remove old vector store files FIRST before rebuilding
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Steps:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                1. Delete/backup existing vector store directory (e.g., `rm -rf vector_store/` or move to backup)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                2. Clear any cached embeddings or old chunks
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                3. Use refactored `enrich_faq_metadata.py` to extract from Excel (`Swiss Cottages FAQS.xlsx`)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                4. Command: `python chatbot/scripts/enrich_faq_metadata.py --excel "Swiss Cottages FAQS.xlsx" --output-dir docs/faq`
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                5. This will generate markdown files with intent metadata already included
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                6. Then rebuild vector store from scratch: `python rebuild_vector_store.py` or use existing build script

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - **Why remove first**: Ensures clean rebuild with new intent metadata, prevents mixing old chunks without intent with new chunks with intent

5. **Version constraints** - All implementations must work with existing dependency versions

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Do NOT modify `requirements.txt`, `pyproject.toml`, or any dependency files
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Do NOT upgrade/downgrade ChromaDB, pandas, openpyxl, or any other packages
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - If a feature seems to require a version change, find an alternative implementation approach

## Testing Checklist

- [ ] Pricing queries only retrieve pricing docs
- [ ] Non-pricing queries don't mention pricing
- [ ] Responses are concise but informative (2-8 sentences depending on intent, with direct answer + brief explanation)
- [ ] Cottage-specific queries only retrieve relevant cottage docs
- [ ] Handlers perform calculations correctly
- [ ] Hybrid reasoning works correctly (handlers for simple tasks, reasoning model for complex tasks)
- [ ] Reasoning model (REASONING_MODEL_NAME) is used for complex reasoning when needed
- [ ] LLM phrases final answers naturally
- [ ] No hallucinations (cottages 7, 9, 11 only)
- [ ] Slot terminology is correct (`cottage_id` used for cottage types, NOT `room_type`)
- [ ] Query optimization enhances queries with intent-specific domain terms
- [ ] Entity extraction (cottage_id, dates, group_size) works before retrieval
- [ ] Metadata filters correctly filter by intent and cottage_id
- [ ] LLM query optimization only used for complex/ambiguous queries (not every query)