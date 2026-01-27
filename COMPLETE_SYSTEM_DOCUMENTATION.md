# Complete RAG Chatbot System Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [PDF Extraction Process](#pdf-extraction-process)
3. [Document Chunking Process](#document-chunking-process)
4. [Vector Storage Process](#vector-storage-process)
5. [LLM Integration and Working](#llm-integration-and-working)
6. [Query Processing Flow](#query-processing-flow)
7. [File Structure and Responsibilities](#file-structure-and-responsibilities)

---

## System Overview

This is a **Retrieval-Augmented Generation (RAG)** chatbot system that:
1. Extracts Q&A pairs from PDF documents
2. Converts them to structured Markdown files
3. Splits documents into chunks for better semantic search
4. Creates vector embeddings and stores them in ChromaDB
5. Uses LLM (via Groq API or local llama.cpp) to answer questions based on retrieved context

---

## PDF Extraction Process

### Entry Point
**File:** `chatbot/pdf_faq_extractor.py`

### Process Flow

#### Step 1: Extract Q&A from PDF
**Function:** `extract_faq_from_pdf(pdf_path: Path)`
**Location:** `chatbot/pdf_faq_extractor.py:30-63`

**What happens:**
- Uses `unstructured.partition.auto.partition()` to extract text from PDF
- File: `chatbot/pdf_faq_extractor.py:56`
- Converts PDF elements to text content
- Calls `parse_table_structure()` to parse Q&A pairs

#### Step 2: Parse Table Structure
**Function:** `parse_table_structure(elements, text_content, pdf_path)`
**Location:** `chatbot/pdf_faq_extractor.py:66-237`

**What happens:**
- Splits text into lines
- Identifies question start index (after headers)
- Extracts numbered questions using regex patterns:
  - Pattern 1: `"1 What is..."` (number and question on same line)
  - Pattern 2: `"4"` then `"Is Swiss..."` (number and question on separate lines)
- Extracts answers by looking ahead until next question or category
- Assigns categories based on question number ranges (lines 240-326)
- Returns list of Q&A dictionaries with metadata:
  ```python
  {
    "faq_id": "faq_001",
    "category": "General & About",
    "question": "What is...",
    "answer": "...",
    "source": "path/to/pdf",
    "question_number": 1
  }
  ```

#### Step 3: Format Q&A for Embedding
**Function:** `format_qa_for_embedding(qa_pair: dict)`
**Location:** `chatbot/pdf_faq_extractor.py:408-429`

**What happens:**
- Formats Q&A pair as:
  ```
  Category: {category}
  
  Question: {question}
  
  Answer: {answer}
  ```
- This format optimizes semantic search

#### Step 4: Generate Markdown Files
**Function:** `generate_markdown_files(qa_pairs, output_dir)`
**Location:** `chatbot/pdf_faq_extractor.py:530-588`

**What happens:**
- Creates YAML frontmatter for each Q&A:
  ```yaml
  ---
  category: "General & About"
  faq_id: "faq_001"
  source: "path/to/pdf"
  question: "What is..."
  type: "qa_pair"
  ---
  ```
- Writes formatted content to Markdown files
- Filename format: `{category_safe}_{faq_id}.md`
- Adds resource links for specific FAQ numbers (lines 502-527)

**Output:** Markdown files in `docs/faq/` directory

---

## Document Chunking Process

### Entry Points
1. **For FAQ extraction:** `chatbot/pdf_faq_extractor.py:591-645` → `build_vector_index()`
2. **For general docs:** `chatbot/memory_builder.py:73-86` → `build_memory_index()`

### Process Flow

#### Step 1: Load Documents
**File:** `chatbot/document_loader/loader.py`

**Class:** `DirectoryLoader`
**Method:** `load()`
**Location:** `chatbot/document_loader/loader.py:46-70`

**What happens:**
- Scans directory for files matching glob pattern (e.g., `**/*.md`)
- For each file:
  - Uses `unstructured.partition.auto.partition()` to extract text
  - Creates `Document` objects with:
    - `page_content`: extracted text
    - `metadata`: `{"source": file_path}`
- Returns list of `Document` objects

**File:** `chatbot/entities/document.py:10-19`
```python
@dataclass
class Document:
    page_content: str
    metadata: dict
    type: Literal["Document"] = "Document"
```

#### Step 2: Split into Chunks
**File:** `chatbot/document_loader/text_splitter.py`

**Function:** `create_recursive_text_splitter(format, **kwargs)`
**Location:** `chatbot/document_loader/text_splitter.py:259-271`

**Class:** `RecursiveCharacterTextSplitter`
**Location:** `chatbot/document_loader/text_splitter.py:156-227`

**What happens:**
1. **Get Format Separators**
   - File: `chatbot/document_loader/format.py`
   - For Markdown: `["\n#{1,6} ", "```\n", "\n\n", "\n", " ", ""]`
   - Separators are tried in order (most semantic to least)

2. **Recursive Splitting**
   - Method: `_split_text(text, separators)`
   - Tries to split by first separator (e.g., headings)
   - If chunks still too large, recursively tries next separator
   - Continues until chunks fit within `chunk_size`

3. **Merge Splits**
   - Method: `_merge_splits(splits, separator)`
   - Combines small splits up to `chunk_size`
   - Maintains `chunk_overlap` between consecutive chunks
   - Overlap ensures context continuity

4. **Special Handling for Q&A Pairs**
   - Location: `chatbot/pdf_faq_extractor.py:621-637` and `chatbot/memory_builder.py:51-68`
   - If document metadata has `type: "qa_pair"`:
     - Only splits if content > 1000 words
     - Otherwise keeps Q&A pair as single chunk (better semantic matching)

**Parameters:**
- `chunk_size`: Maximum characters per chunk (default: 512)
- `chunk_overlap`: Overlapping characters between chunks (default: 25)

**Output:** List of `Document` chunks with preserved metadata

---

## Vector Storage Process

### Components

#### 1. Embedding Generation
**File:** `chatbot/bot/memory/embedder.py`

**Class:** `Embedder`
**Location:** `chatbot/bot/memory/embedder.py:6-49`

**What happens:**
- Uses `sentence-transformers` library
- Model: `all-MiniLM-L6-v2` (default)
- Converts text to 384-dimensional vectors

**Methods:**
- `embed_documents(texts)`: Batch embedding for documents
- `embed_query(text)`: Single embedding for queries

**Process:**
1. Replaces newlines with spaces
2. Calls `SentenceTransformer.encode()`
3. Returns list of float vectors

#### 2. Vector Database Storage
**File:** `chatbot/bot/memory/vector_database/chroma.py`

**Class:** `Chroma`
**Location:** `chatbot/bot/memory/vector_database/chroma.py:16-347`

**What happens:**

1. **Initialization**
   - Creates/connects to ChromaDB collection
   - Sets up persistent storage at `vector_store_path`
   - Configures embedding function

2. **Adding Chunks**
   - Method: `from_chunks(chunks)`
   - Location: `chatbot/bot/memory/vector_database/chroma.py:189-201`
   - Process:
     ```python
     texts = [clean(doc.page_content) for doc in chunks]  # Clean text
     metadatas = [doc.metadata for doc in chunks]         # Preserve metadata
     embeddings = embedder.embed_documents(texts)          # Generate embeddings
     collection.upsert(ids, embeddings, documents, metadatas)  # Store in ChromaDB
     ```

3. **Storage Structure**
   - **Location:** `vector_store/` directory
   - **Files:**
     - `chroma.sqlite3`: SQLite database with metadata
     - `{uuid}/`: Directories with vector data:
       - `data_level0.bin`: Vector data
       - `header.bin`: Header information
       - `length.bin`: Length information
       - `link_lists.bin`: HNSW index links

4. **Similarity Search**
   - Method: `similarity_search_with_threshold(query, k, threshold)`
   - Location: `chatbot/bot/memory/vector_database/chroma.py:203-251`
   - Process:
     ```python
     1. Embed query using embedder.embed_query(query)
     2. Query ChromaDB collection with query embedding
     3. Get top-k similar documents (cosine similarity)
     4. Filter by relevance threshold (default: 0.2)
     5. Return documents with scores
     ```

**Distance Metric:**
- File: `chatbot/bot/memory/vector_database/distance_metric.py`
- Uses L2 distance (Euclidean) by default
- Converts to relevance scores (0-1 range)

---

## LLM Integration and Working

### LLM Clients

#### 1. Groq Client (Fast - Cloud API)
**File:** `chatbot/bot/client/groq_client.py`

**Class:** `GroqClient`
**Location:** `chatbot/bot/client/groq_client.py:21-268`

**What happens:**
- Uses Groq API for fast inference
- Model: `llama-3.1-8b-instant` (default)
- **Initialization:**
  - Requires `GROQ_API_KEY` environment variable
  - Creates Groq client instance

- **Answer Generation:**
  - Method: `generate_answer(prompt, max_new_tokens)`
  - Sends request to Groq API
  - Returns generated text

- **Streaming:**
  - Method: `start_answer_iterator_streamer(prompt, max_new_tokens)`
  - Yields tokens as they're generated
  - Format compatible with `LamaCppClient`

#### 2. Local LLM Client (llama.cpp)
**File:** `chatbot/bot/client/lama_cpp_client.py`

**Class:** `LamaCppClient`
**Location:** `chatbot/bot/client/lama_cpp_client.py:25-343`

**What happens:**
- Uses `llama-cpp-python` library
- Loads GGUF model files (e.g., `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`)
- **Initialization:**
  - Auto-downloads model if not found
  - Loads model with `Llama()` from `llama_cpp`
  - Configures model settings (temperature, top_p, etc.)

- **Answer Generation:**
  - Method: `generate_answer(prompt, max_new_tokens)`
  - Uses `llm.create_chat_completion()`
  - Returns generated text

- **Streaming:**
  - Method: `start_answer_iterator_streamer(prompt, max_new_tokens)`
  - Streams tokens using `stream=True`
  - Yields token dictionaries

### Model Settings
**File:** `chatbot/bot/model/settings/`

**Structure:**
- Base class: `chatbot/bot/model/base_model.py`
- Model-specific settings:
  - `llama.py`: Llama 3.1 settings
  - `deep_seek.py`: DeepSeek settings
  - `qwen.py`: Qwen settings
  - etc.

**Settings include:**
- System template
- Model file name
- Download URL
- Configuration (temperature, top_p, etc.)
- Reasoning tags (if supported)

### Prompt Templates
**File:** `chatbot/bot/client/prompt.py`

**Templates:**
1. **QA_PROMPT_TEMPLATE**: Simple Q&A
2. **CTX_PROMPT_TEMPLATE**: Context-aware Q&A
3. **REFINED_CTX_PROMPT_TEMPLATE**: Refine existing answer with new context
4. **REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE**: Refine question based on chat history
5. **REFINED_ANSWER_CONVERSATION_AWARENESS_PROMPT_TEMPLATE**: Answer with chat history

**Key Instructions in CTX_PROMPT_TEMPLATE:**
- Answer using ONLY context information
- DO NOT use prior knowledge
- Include ALL relevant information
- If context doesn't match question location, state it clearly

---

## Query Processing Flow

### Entry Point
**File:** `chatbot/rag_chatbot_app.py`

### Main Flow (Function: `main()`)
**Location:** `chatbot/rag_chatbot_app.py:171-381`

#### Step 1: Initialize Components
**Location:** `chatbot/rag_chatbot_app.py:199-212`

1. **Load LLM Client**
   - Function: `load_llm_client()`
   - Location: `chatbot/rag_chatbot_app.py:28-56`
   - Tries Groq API first, falls back to local model
   - Returns `GroqClient` or `LamaCppClient`

2. **Load Vector Index**
   - Function: `load_index()`
   - Location: `chatbot/rag_chatbot_app.py:71-106`
   - Creates `Chroma` instance with `Embedder`
   - Loads from `vector_store/` directory

3. **Load Context Synthesis Strategy**
   - Function: `load_ctx_synthesis_strategy()`
   - Location: `chatbot/rag_chatbot_app.py:65-68`
   - Options:
     - `create-and-refine`: Sequential refinement (fastest)
     - `tree-summarization`: Hierarchical summarization
     - `async-tree-summarization`: Async hierarchical (slowest)

#### Step 2: Process User Query
**Location:** `chatbot/rag_chatbot_app.py:218-381`

1. **Refine Question**
   - Function: `refine_question()`
   - File: `chatbot/bot/conversation/conversation_handler.py:17-53`
   - **What happens:**
     - If chat history exists, uses LLM to convert follow-up question to standalone question
     - Uses `REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE`
     - Returns refined question

2. **Retrieve Documents**
   - Location: `chatbot/rag_chatbot_app.py:239-277`
   - **What happens:**
     ```python
     # Try with refined query first
     retrieved_contents, sources = index.similarity_search_with_threshold(
         query=refined_user_input, k=parameters.k, threshold=0.0
     )
     
     # If no results, try original query
     if not retrieved_contents:
         retrieved_contents, sources = index.similarity_search_with_threshold(
             query=user_input, k=parameters.k, threshold=0.0
         )
     ```
   - Uses cosine similarity to find top-k most relevant chunks
   - Returns documents with relevance scores

3. **Check Document Relevance**
   - Location: `chatbot/rag_chatbot_app.py:280-312`
   - **What happens:**
     - Checks for location mismatches (e.g., India vs Pakistan)
     - Validates that retrieved documents match query intent
     - Prevents hallucination from irrelevant documents

4. **Generate Answer**
   - Function: `answer_with_context()`
   - File: `chatbot/bot/conversation/conversation_handler.py:98-199`
   - **What happens:**
     - Uses context synthesis strategy to combine retrieved documents
     - Generates answer using LLM with context
     - Streams response token by token

#### Step 3: Context Synthesis Strategies

**File:** `chatbot/bot/conversation/ctx_strategy.py`

##### Strategy 1: Create-and-Refine (Fastest)
**Class:** `CreateAndRefineStrategy`
**Location:** `chatbot/bot/conversation/ctx_strategy.py:80-137`

**Process:**
1. Start with first chunk → generate initial answer
2. For each subsequent chunk:
   - Refine existing answer with new context
   - Uses `REFINED_CTX_PROMPT_TEMPLATE`
3. Last chunk streams response
4. **Time:** ~30-60 seconds

##### Strategy 2: Tree Summarization
**Class:** `TreeSummarizationStrategy`
**Location:** `chatbot/bot/conversation/ctx_strategy.py:140-231`

**Process:**
1. Generate answer for each chunk independently
2. Combine answers hierarchically (2 at a time)
3. Continue combining until single answer
4. Stream final answer
5. **Time:** ~2-5 minutes

##### Strategy 3: Async Tree Summarization
**Class:** `AsyncTreeSummarizationStrategy`
**Location:** `chatbot/bot/conversation/ctx_strategy.py:234-330`

**Process:**
1. Generate answers for all chunks in parallel (async)
2. Combine answers hierarchically (async)
3. Stream final answer
4. **Time:** ~5-10+ minutes (but parallel processing)

#### Step 4: Update Chat History
**Location:** `chatbot/rag_chatbot_app.py:363`

- Appends question and answer to chat history
- File: `chatbot/bot/conversation/chat_history.py`
- Maintains conversation context for future queries

---

## File Structure and Responsibilities

### Core Application Files

| File | Purpose | Key Functions |
|------|---------|---------------|
| `chatbot/rag_chatbot_app.py` | Main Streamlit app | `main()`, `load_llm_client()`, `load_index()` |
| `chatbot/pdf_faq_extractor.py` | PDF extraction & indexing | `extract_faq_from_pdf()`, `build_vector_index()`, `generate_markdown_files()` |
| `chatbot/memory_builder.py` | Build vector index from docs | `build_memory_index()`, `load_documents()`, `split_chunks()` |

### Document Processing

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `chatbot/document_loader/loader.py` | Load documents from directory | `DirectoryLoader.load()` |
| `chatbot/document_loader/text_splitter.py` | Split documents into chunks | `RecursiveCharacterTextSplitter`, `create_recursive_text_splitter()` |
| `chatbot/document_loader/format.py` | Define format separators | `Format`, `get_separators()` |
| `chatbot/entities/document.py` | Document data structure | `Document` dataclass |

### Vector Storage

| File | Purpose | Key Classes/Methods |
|------|---------|-------------------|
| `chatbot/bot/memory/embedder.py` | Generate embeddings | `Embedder.embed_documents()`, `Embedder.embed_query()` |
| `chatbot/bot/memory/vector_database/chroma.py` | ChromaDB integration | `Chroma.from_chunks()`, `Chroma.similarity_search_with_threshold()` |
| `chatbot/bot/memory/vector_database/distance_metric.py` | Distance calculations | `DistanceMetric`, `get_relevance_score_fn()` |

### LLM Integration

| File | Purpose | Key Classes/Methods |
|------|---------|-------------------|
| `chatbot/bot/client/groq_client.py` | Groq API client | `GroqClient.generate_answer()`, `GroqClient.start_answer_iterator_streamer()` |
| `chatbot/bot/client/lama_cpp_client.py` | Local LLM client | `LamaCppClient.generate_answer()`, `LamaCppClient.start_answer_iterator_streamer()` |
| `chatbot/bot/client/prompt.py` | Prompt templates | `CTX_PROMPT_TEMPLATE`, `generate_ctx_prompt()` |
| `chatbot/bot/model/base_model.py` | Base model settings | `ModelSettings` |
| `chatbot/bot/model/settings/*.py` | Model-specific settings | `Llama31Settings`, etc. |
| `chatbot/bot/model/model_registry.py` | Model registry | `get_model_settings()`, `get_models()` |

### Conversation Handling

| File | Purpose | Key Functions |
|------|---------|--------------|
| `chatbot/bot/conversation/conversation_handler.py` | Handle queries | `refine_question()`, `answer_with_context()` |
| `chatbot/bot/conversation/ctx_strategy.py` | Context synthesis | `CreateAndRefineStrategy`, `TreeSummarizationStrategy`, `AsyncTreeSummarizationStrategy` |
| `chatbot/bot/conversation/chat_history.py` | Chat history management | `ChatHistory.append()`, `ChatHistory.clear()` |

### Utilities

| File | Purpose |
|------|---------|
| `chatbot/helpers/log.py` | Logging utilities |
| `chatbot/helpers/prettier.py` | Format source information |
| `chatbot/helpers/reader.py` | File reading utilities |

---

## Data Flow Summary

```
PDF File
    ↓
[pdf_faq_extractor.py]
    ↓ extract_faq_from_pdf()
    ↓ parse_table_structure()
    ↓ generate_markdown_files()
    ↓
Markdown Files (docs/faq/*.md)
    ↓
[loader.py] DirectoryLoader.load()
    ↓
Document Objects
    ↓
[text_splitter.py] RecursiveCharacterTextSplitter
    ↓ split_documents()
    ↓
Document Chunks
    ↓
[embedder.py] Embedder.embed_documents()
    ↓
Vector Embeddings (384-dim)
    ↓
[chroma.py] Chroma.from_chunks()
    ↓
ChromaDB Storage (vector_store/)
    ↓
[rag_chatbot_app.py] User Query
    ↓ refine_question()
    ↓
Refined Query
    ↓
[chroma.py] Chroma.similarity_search_with_threshold()
    ↓
Retrieved Documents
    ↓
[ctx_strategy.py] Context Synthesis Strategy
    ↓ generate_response()
    ↓
[groq_client.py / lama_cpp_client.py] LLM Generation
    ↓
Streaming Answer
    ↓
Display to User
```

---

## Key Configuration

### Chunking Parameters
- **Default chunk_size:** 512 characters
- **Default chunk_overlap:** 25 characters
- **Q&A pairs:** Kept as single chunk if < 1000 words

### Embedding Model
- **Model:** `all-MiniLM-L6-v2`
- **Dimensions:** 384
- **Library:** `sentence-transformers`

### Vector Database
- **Database:** ChromaDB
- **Storage:** `vector_store/` directory
- **Similarity Metric:** Cosine similarity (L2 distance)
- **Default k:** 2-5 chunks retrieved

### LLM Settings
- **Groq API:** `llama-3.1-8b-instant` (default)
- **Local Model:** `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`
- **Max Tokens:** 512 (default)
- **Temperature:** 0.7

---

## Usage Examples

### Extract FAQ from PDF
```bash
python chatbot/pdf_faq_extractor.py \
    --pdf "Swiss Cottages FAQS - Google Sheets.pdf" \
    --output docs/faq \
    --vector-store vector_store \
    --chunk-size 512 \
    --chunk-overlap 25
```

### Build Vector Index from Documents
```bash
python chatbot/memory_builder.py \
    --chunk-size 512 \
    --chunk-overlap 25
```

### Run RAG Chatbot
```bash
streamlit run chatbot/rag_chatbot_app.py \
    --model llama-3.1 \
    --synthesis-strategy create-and-refine \
    --k 5 \
    --max-new-tokens 512
```

---

## Notes

1. **Q&A Pairs:** Special handling keeps Q&A pairs together as single chunks for better semantic matching
2. **Location Validation:** System checks for location mismatches to prevent hallucination
3. **Fallback Strategy:** If refined query fails, tries original query
4. **Streaming:** Answers are streamed token-by-token for better UX
5. **Caching:** Streamlit caches LLM client and vector index for performance

---

*Documentation generated for RAG-based Chatbot System*
