# Code Review Findings & Recommendations

## Executive Summary

After reviewing your codebase, I've identified **5 critical issues** that need to be addressed before implementing the intent-based architecture plan. The plan has been updated with these findings.

---

## 🔴 Critical Issues Found

### 1. DirectoryLoader Doesn't Parse YAML Frontmatter

**Location**: `chatbot/document_loader/loader.py:86-88`

**Current Behavior**:
```python
if doc_path.suffix.lower() == '.md':
    text = doc_path.read_text(encoding='utf-8')
    docs.extend([Document(page_content=text, metadata={"source": str(doc_path)})])
```

**Problem**: 
- Reads entire markdown file (including YAML frontmatter) as `page_content`
- Metadata from frontmatter (intent, cottage_id, category) is **NOT extracted**
- Even if markdown files have intent metadata, it won't be in chunks

**Impact**: 
- Intent metadata from frontmatter will be lost during chunking
- Vector store won't have intent metadata for filtering

**Fix Required**: 
- Add frontmatter parsing in `load_file()` method
- Extract intent, cottage_id, category from YAML frontmatter
- Use content without frontmatter as `page_content`
- Add frontmatter fields to metadata dict

**Recommended Solution**:
```python
import re
import yaml

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

---

### 2. similarity_search_with_threshold Doesn't Support Filter

**Location**: `chatbot/bot/memory/vector_database/chroma.py:475-523`

**Current Method Signature**:
```python
def similarity_search_with_threshold(
    self,
    query: str,
    k: int = 4,
    threshold: float | None = 0.2,
) -> tuple[list[Document], list[dict[str, Any]]]:
```

**Problem**: 
- No `filter` parameter in `similarity_search_with_threshold()`
- Cannot filter by intent metadata using this method

**Available Alternative**:
- `similarity_search_with_score(query, k, filter=...)` DOES support filter (line 544)

**Impact**: 
- Cannot use intent-based filtering with current method
- Need to use alternative method or add filter support

**Fix Options**:

**Option A**: Use `similarity_search_with_score()` and apply threshold manually:
```python
docs_and_scores = vector_store.similarity_search_with_score(
    query=optimized_query,
    k=effective_k * 3,
    filter=retrieval_filter  # Supports filter!
)

# Apply threshold
if threshold is not None:
    docs_and_scores = [(doc, score) for doc, score in docs_and_scores if score <= threshold]

# Format as tuple
retrieved_contents = [doc for doc, _ in docs_and_scores]
sources = [{"score": round(score, 3), "document": doc.metadata.get("source"), ...} 
           for doc, score in docs_and_scores]
result = (retrieved_contents, sources)
```

**Option B**: Add filter parameter to `similarity_search_with_threshold()`:
```python
def similarity_search_with_threshold(
    self,
    query: str,
    k: int = 4,
    threshold: float | None = 0.2,
    filter: dict[str, str] | None = None,  # NEW parameter
) -> tuple[list[Document], list[dict[str, Any]]]:
    # Use similarity_search_with_score with filter
    docs_and_scores = self.similarity_search_with_score(query, k, filter=filter)
    # ... rest of existing logic
```

---

### 3. INTENT_TO_SLOTS Still Uses "room_type"

**Location**: `chatbot/scripts/enrich_faq_metadata.py:69-102`

**Current State**:
```python
INTENT_TO_SLOTS = {
    "pricing": {
        "required": ["guests", "dates", "room_type"],  # ❌ WRONG
    },
    "booking": {
        "required": ["guests", "dates", "room_type", "family"],  # ❌ WRONG
    },
    "availability": {
        "optional": ["guests", "room_type"],  # ❌ WRONG
    },
    # ... etc
}
```

**Problem**: 
- Still uses `"room_type"` instead of `"cottage_id"`
- Lines 71, 75, 80, 84, 88 need to be changed

**Fix Required**: Replace all `"room_type"` with `"cottage_id"`:
```python
INTENT_TO_SLOTS = {
    "pricing": {
        "required": ["guests", "dates", "cottage_id"],  # ✅ FIXED
    },
    "booking": {
        "required": ["guests", "dates", "cottage_id", "family"],  # ✅ FIXED
    },
    "availability": {
        "optional": ["guests", "cottage_id"],  # ✅ FIXED
    },
    "rooms": {
        "optional": ["guests", "cottage_id"],  # ✅ FIXED
    },
    "facilities": {
        "optional": ["cottage_id"],  # ✅ FIXED
    },
}
```

**Also Fix SLOT_HINTS** (line 108):
```python
SLOT_HINTS = {
    "guests": "number of guests or people",
    "cottage_id": "cottage 7, 9, or 11",  # ✅ Changed from room_type
    "dates": "check-in and check-out dates",
    "family": "whether booking is for family or friends",
    "season": "weekday, weekend, peak, or off-peak",
}
```

---

### 4. rebuild_vector_store.py Doesn't Parse Frontmatter

**Location**: `rebuild_vector_store.py:20-48`

**Current Behavior**:
```python
def load_markdown_files(docs_path: Path) -> list[Document]:
    for md_file in docs_path.rglob("*.md"):
        content = md_file.read_text(encoding='utf-8')
        
        # Extract metadata from filename if possible
        metadata = {
            "source": str(md_file.relative_to(docs_path.parent)),
            "file_name": md_file.name,
            "type": "qa_pair" if "faq" in md_file.name.lower() else "document"
        }
        
        doc = Document(page_content=content, metadata=metadata)
```

**Problem**: 
- Only extracts metadata from filename
- Does NOT parse YAML frontmatter
- Intent, cottage_id from frontmatter are lost

**Fix Required**: Add frontmatter parsing (same logic as DirectoryLoader fix)

---

### 5. ✅ Good News: Rebuild Process Already Removes Old Files

**Location**: `rebuild_vector_store.py:90-94`

**Current Behavior**:
```python
# Remove old vector store if it exists
if vector_store_path.exists():
    import shutil
    logger.info(f"Removing old vector store at {vector_store_path}")
    shutil.rmtree(vector_store_path)
```

**Status**: ✅ Already correct - removes old vector store before rebuilding

---

## 📋 Summary of Required Fixes

| Issue | File | Priority | Status |
|-------|------|----------|--------|
| DirectoryLoader doesn't parse frontmatter | `chatbot/document_loader/loader.py` | 🔴 Critical | Needs Fix |
| similarity_search_with_threshold no filter | `chatbot/bot/memory/vector_database/chroma.py` | 🔴 Critical | Needs Fix |
| INTENT_TO_SLOTS uses room_type | `chatbot/scripts/enrich_faq_metadata.py` | 🔴 Critical | Needs Fix |
| rebuild_vector_store doesn't parse frontmatter | `rebuild_vector_store.py` | 🔴 Critical | Needs Fix |
| Rebuild removes old files | `rebuild_vector_store.py` | ✅ Good | Already Correct |

---

## 🎯 Recommended Implementation Order

1. **Fix INTENT_TO_SLOTS** (easiest, no dependencies)
2. **Fix DirectoryLoader** (needed for metadata extraction)
3. **Fix rebuild_vector_store.py** (needed for rebuild process)
4. **Fix similarity_search_with_threshold** (needed for filtering)

---

## 📝 Plan Status

The plan at `.cursor/plans/intent-based_architecture_fix_70ac24f6.plan.md` has been updated with:
- All findings documented in "CRITICAL: Current System Analysis" section
- Detailed fix instructions for each issue
- Code examples for each fix
- Updated Phase 1 and Phase 2 with frontmatter parsing requirements

---

## ✅ Next Steps

1. Review this document
2. Review updated plan
3. Implement fixes in order (INTENT_TO_SLOTS → DirectoryLoader → rebuild_vector_store → similarity_search)
4. Test each fix before moving to next
5. Proceed with full implementation
