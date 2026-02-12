# Vector Store Rebuild Instructions

## Overview
After implementing the intent-based architecture, you need to rebuild the vector store with intent metadata.

## Environment Variable

Add this to your `.env` file to enable/disable the new intent-based architecture:

```bash
# Enable intent-based filtering (default: true)
# Set to "false" to disable and use old behavior
USE_INTENT_FILTERING=true
```

**Note**: The intent-based architecture is enabled by default. Set `USE_INTENT_FILTERING=false` to disable it and revert to the old behavior.

## Steps

### 1. Extract FAQs from Excel with Intent Classification
Run the refactored `enrich_faq_metadata.py` script to extract FAQs from Excel and classify intent during extraction:

```bash
python chatbot/scripts/enrich_faq_metadata.py --excel "Swiss Cottages FAQS.xlsx" --output-dir docs/faq
```

This will:
- Extract Q&A pairs from Excel
- Classify intent for each FAQ during extraction
- Extract cottage_id (7, 9, or 11) from question/answer
- Generate markdown files with intent, cottage_id, and slots in frontmatter

### 2. Rebuild Vector Store
Run the rebuild script which will:
- Remove old vector store files automatically
- Parse YAML frontmatter to extract intent and cottage_id metadata
- Build new vector store with intent metadata

```bash
python rebuild_vector_store.py
```

Or if you need to specify custom paths:

```bash
python rebuild_vector_store.py
# Default paths:
# - docs/faq (source)
# - vector_store/docs_index (destination)
```

## What Changed

### Phase 1: Intent Metadata
- ✅ `enrich_faq_metadata.py` now classifies intent DURING Excel extraction
- ✅ Extracts `cottage_id` (not `room_type`) during extraction
- ✅ Includes intent, cottage_id, required_slots, optional_slots in markdown frontmatter
- ✅ `DirectoryLoader` now parses YAML frontmatter to extract metadata
- ✅ `rebuild_vector_store.py` now parses YAML frontmatter

### Phase 2: Intent-First Retrieval
- ✅ Entity extraction before retrieval
- ✅ Intent-based query optimization (rule-based + optional LLM)
- ✅ Metadata filtering in ChromaDB retrieval
- ✅ `similarity_search_with_threshold` now supports filter parameter

### Phase 3: Split Prompts by Intent
- ✅ Created intent-specific prompt templates:
  - `PRICING_PROMPT_TEMPLATE`
  - `AVAILABILITY_PROMPT_TEMPLATE`
  - `SAFETY_PROMPT_TEMPLATE`
  - `ROOMS_PROMPT_TEMPLATE`
  - `FACILITIES_PROMPT_TEMPLATE`
  - `LOCATION_PROMPT_TEMPLATE`
  - `GENERAL_PROMPT_TEMPLATE`
- ✅ Each prompt has explicit allowlist/denylist and length constraints
- ✅ API now uses intent-specific prompts

### Phase 4: Gate Context
- ✅ Closed-world facts injected in intent-specific prompts
- ✅ SYSTEM FACTS section in each prompt template

### Phase 5: Hybrid Reasoning
- ✅ Already implemented via complexity classification
- ✅ Handlers do simple/deterministic reasoning
- ✅ Reasoning model used for complex tasks

### Phase 6: Length Control
- ✅ Response length constraints in each intent-specific prompt
- ✅ Pricing: 3-5 sentences
- ✅ Availability: 2-3 sentences
- ✅ Safety: 4-6 sentences
- ✅ Rooms: 4-6 sentences
- ✅ Facilities: 4-6 sentences
- ✅ Location: 4-6 sentencesHydraAttack!@#$%@4455
- ✅ General: 5-8 sentences

## Verification

After rebuilding, verify:
1. ✅ No pricing leakage in non-pricing queries
2. ✅ Responses are concise (2-8 sentences depending on intent)
3. ✅ Intent-specific prompts are used
4. ✅ Metadata filtering works (only relevant intents retrieved)
5. ✅ No hallucinations (only cottages 7, 9, 11 mentioned)

## Troubleshooting

If you encounter issues:

1. **Check frontmatter parsing**: Verify markdown files have intent in frontmatter
   ```bash
   head -20 docs/faq/*.md | grep -A 5 "intent:"
   ```

2. **Check vector store metadata**: Verify chunks have intent metadata
   ```python
   from chatbot.bot.memory.vector_database.chroma import Chroma
   from chatbot.bot.memory.embedder import Embedder
   
   vector_store = Chroma(persist_directory="vector_store/docs_index", embedding=Embedder())
   # Check a sample document's metadata
   sample = vector_store.collection.get(limit=1)
   print(sample.get('metadatas', [{}])[0])
   ```

3. **Verify intent classification**: Check that intents are correctly classified
   ```bash
   grep -r "intent:" docs/faq/*.md | sort | uniq -c
   ```
