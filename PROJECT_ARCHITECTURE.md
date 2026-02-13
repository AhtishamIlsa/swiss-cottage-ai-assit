# Complete Project Architecture Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Layers](#architecture-layers)
3. [Component Responsibilities](#component-responsibilities)
4. [Data Flow](#data-flow)
5. [Key Modules and Their Functions](#key-modules-and-their-functions)
6. [Integration Points](#integration-points)
7. [Deployment Architecture](#deployment-architecture)

---

## System Overview

This is a **Swiss Cottages AI Assistant** - a sophisticated RAG (Retrieval-Augmented Generation) chatbot system designed to help users with:
- FAQ questions about Swiss Cottages
- Booking inquiries and availability checks
- Pricing calculations
- Cottage information and recommendations
- Image requests

The system combines:
- **Vector Database** (ChromaDB) for semantic search
- **LLM Models** (Groq API or local llama.cpp) for natural language understanding
- **Intent Classification** for routing queries appropriately
- **Slot Extraction** for structured data (dates, guests, cottage numbers)
- **Context-Aware Conversations** with memory management

---

## Architecture Layers

### Layer 1: Presentation Layer (User Interface)

**Components:**
- **Streamlit Web App** (`streamlit_app.py`, `chatbot/rag_chatbot_app.py`)
- **FastAPI REST API** (`chatbot/api/main.py`)
- **WordPress Widget** (via API integration)

**Responsibilities:**
- User interaction and input handling
- Response display (streaming or complete)
- Session management
- UI state management
- Image display for cottage galleries

**Key Files:**
- `streamlit_app.py` - Streamlit Cloud entry point
- `chatbot/rag_chatbot_app.py` - Main RAG chatbot Streamlit interface
- `chatbot/chatbot_app.py` - Simple conversation chatbot
- `chatbot/api/main.py` - FastAPI REST endpoints (`/api/chat`, `/api/chat/stream`, `/api/health`, etc.)

---

### Layer 2: Application/Orchestration Layer

**Components:**
- **Conversation Handler** (`chatbot/bot/conversation/conversation_handler.py`)
- **Intent Router** (`chatbot/bot/conversation/intent_router.py`)
- **Slot Manager** (`chatbot/bot/conversation/slot_manager.py`)
- **Context Tracker** (`chatbot/bot/conversation/context_tracker.py`)
- **Query Optimizer** (`chatbot/bot/conversation/query_optimizer.py`)

**Responsibilities:**
- Query preprocessing and refinement
- Intent classification (greeting, FAQ, booking, pricing, etc.)
- Slot extraction (dates, guests, cottage numbers)
- Context synthesis strategy selection
- Conversation history management
- Query complexity analysis

**Key Functions:**
- `refine_question()` - Converts follow-up questions to standalone queries
- `answer_with_context()` - Orchestrates RAG pipeline
- `classify()` - Intent classification
- `extract_slots()` - Extracts structured data from queries

---

### Layer 3: Specialized Handlers

**Components:**
- **Pricing Handler** (`chatbot/bot/conversation/pricing_handler.py`)
- **Capacity Handler** (`chatbot/bot/conversation/capacity_handler.py`)
- **Refinement Handler** (`chatbot/bot/conversation/refinement_handler.py`)
- **Recommendation Engine** (`chatbot/bot/conversation/recommendation_engine.py`)
- **Fallback Handler** (`chatbot/bot/conversation/fallback_handler.py`)

**Responsibilities:**
- Domain-specific query handling
- Pricing calculations based on dates, guests, cottage
- Capacity validation and recommendations
- Query refinement detection and handling
- Contextual suggestions and follow-up actions
- Error handling and graceful degradation

---

### Layer 4: LLM Layer

**Components:**
- **Groq Client** (`chatbot/bot/client/groq_client.py`)
- **Local LLM Client** (`chatbot/bot/client/lama_cpp_client.py`)
- **Model Registry** (`chatbot/bot/model/model_registry.py`)
- **Prompt Templates** (`chatbot/bot/client/prompt.py`)

**Responsibilities:**
- LLM inference (cloud or local)
- Prompt generation and formatting
- Streaming response generation
- Model selection based on query complexity
- Token parsing and response extraction

**Supported Models:**
- Groq API: `llama-3.1-8b-instant` (fast, cloud-based)
- Local models: Llama 3.1/3.2, Qwen 2.5, DeepSeek R1, OpenChat, Starling, Phi-3.5, StableLM Zephyr

**Key Functions:**
- `generate_answer()` - Generate response from prompt
- `start_answer_iterator_streamer()` - Stream tokens
- `generate_qa_prompt()` - Create Q&A prompts
- `generate_refined_question_conversation_awareness_prompt()` - Refine questions with context

---

### Layer 5: Memory/Vector Database Layer

**Components:**
- **Embedder** (`chatbot/bot/memory/embedder.py`)
- **Chroma Vector Database** (`chatbot/bot/memory/vector_database/chroma.py`)
- **Distance Metrics** (`chatbot/bot/memory/vector_database/distance_metric.py`)

**Responsibilities:**
- Document embedding generation (384-dimensional vectors)
- Vector storage and indexing (HNSW algorithm)
- Semantic similarity search
- Relevance threshold filtering
- Metadata filtering (category, FAQ ID, etc.)

**Technology:**
- Embedding Model: `all-MiniLM-L6-v2` (sentence-transformers)
- Vector DB: ChromaDB with persistent storage
- Index: HNSW (Hierarchical Navigable Small World)

**Key Functions:**
- `embed_documents()` - Batch embedding generation
- `embed_query()` - Query embedding
- `similarity_search_with_threshold()` - Retrieve relevant documents
- `from_chunks()` - Add documents to vector store

---

### Layer 6: Document Processing Layer

**Components:**
- **PDF FAQ Extractor** (`chatbot/pdf_faq_extractor.py`)
- **Directory Loader** (`chatbot/document_loader/loader.py`)
- **Text Splitter** (`chatbot/document_loader/text_splitter.py`)
- **Memory Builder** (`chatbot/memory_builder.py`)

**Responsibilities:**
- PDF to Markdown conversion
- Q&A pair extraction from PDFs
- Document loading from directories
- Text chunking with overlap
- Vector index building

**Process Flow:**
1. Extract Q&A pairs from PDF → Parse table structure
2. Format Q&A pairs → Generate Markdown files with YAML frontmatter
3. Load Markdown files → Split into chunks (512 chars, 25 overlap)
4. Generate embeddings → Store in ChromaDB

**Key Functions:**
- `extract_faq_from_pdf()` - Extract FAQs from PDF
- `parse_table_structure()` - Parse Q&A pairs
- `load_documents()` - Load from directory
- `split_chunks()` - Split documents into chunks
- `build_memory_index()` - Build vector store

---

### Layer 7: Supporting Services

**Components:**
- **Cottage Registry** (`chatbot/bot/conversation/cottage_registry.py`)
- **Pricing Calculator** (`chatbot/bot/conversation/pricing_calculator.py`)
- **Date Extractor** (`chatbot/bot/conversation/date_extractor.py`)
- **Number Extractor** (`chatbot/bot/conversation/number_extractor.py`)
- **Sentiment Analyzer** (`chatbot/bot/conversation/sentiment_analyzer.py`)
- **Confidence Scorer** (`chatbot/bot/conversation/confidence_scorer.py`)
- **Query Complexity Classifier** (`chatbot/bot/conversation/query_complexity.py`)

**Responsibilities:**
- Cottage metadata management (capacity, features, pricing)
- Date parsing and validation
- Number extraction (guests, cottage numbers)
- Sentiment analysis for user queries
- Confidence scoring for responses
- Query complexity classification (simple vs complex)

---

## Component Responsibilities

### Intent Router (`intent_router.py`)
**What it does:**
- Classifies user queries into intent types (greeting, FAQ, booking, pricing, etc.)
- Uses pattern matching (fast) + LLM classification (fallback)
- Routes queries to appropriate handlers

**Intent Types:**
- `GREETING` - "hi", "hello"
- `FAQ_QUESTION` - General questions about cottages
- `PRICING` - Price inquiries
- `BOOKING` - Booking requests
- `AVAILABILITY` - Availability checks
- `ROOMS` - Cottage/room information
- `LOCATION` - Location queries
- `FACILITIES` - Amenities questions
- `SAFETY` - Safety/security questions
- `REFINEMENT` - Constraint/refinement requests

---

### Slot Manager (`slot_manager.py`)
**What it does:**
- Extracts structured data from user queries
- Manages conversation state (slots across turns)
- Validates slot values
- Determines which slots are required for each intent

**Slots:**
- `guests` - Number of guests (1-9)
- `cottage_id` - Cottage number (7, 9, 11, or "any")
- `dates` - Check-in/check-out dates
- `family` - Family-friendly requirement (boolean)
- `pets` - Pet-friendly requirement (boolean)

**Extraction Methods:**
- Pattern matching (regex, keywords)
- Number extractor (guests, cottage numbers)
- Date extractor (date ranges)
- LLM extraction (fallback for complex cases)

---

### Conversation Handler (`conversation_handler.py`)
**What it does:**
- Orchestrates the RAG pipeline
- Refines questions using conversation history
- Synthesizes answers from retrieved documents
- Manages streaming responses

**Key Functions:**
- `refine_question()` - Makes follow-up questions standalone
- `answer_with_context()` - Generates answer from retrieved docs
- `extract_content_after_reasoning()` - Extracts final answer from reasoning models

---

### Context Synthesis Strategies (`ctx_strategy.py`)
**What it does:**
- Combines multiple retrieved documents into coherent answers
- Implements different strategies for different use cases

**Strategies:**
1. **Create-and-Refine** (Fast: 30-60s)
   - Sequential refinement through documents
   - Best for real-time interactions

2. **Tree Summarization** (Medium: 2-5 min)
   - Hierarchical combination of answers
   - Best for comprehensive answers

3. **Async Tree Summarization** (Slow: 5-10+ min)
   - Parallel processing of chunks
   - Best for maximum quality

---

### Query Optimizer (`query_optimizer.py`)
**What it does:**
- Optimizes queries for better retrieval
- Extracts entities for metadata filtering
- Classifies query complexity
- Generates retrieval filters

**Functions:**
- `optimize_query_for_rag()` - Enhances query for RAG
- `optimize_query_for_retrieval()` - Optimizes for vector search
- `extract_entities_for_retrieval()` - Extracts entities (cottage numbers, dates)
- `get_retrieval_filter()` - Creates metadata filters
- `is_complex_query()` - Determines if query needs complex handling

---

### Pricing Handler (`pricing_handler.py`)
**What it does:**
- Handles pricing-related queries
- Calculates prices based on slots (dates, guests, cottage)
- Validates pricing requests
- Provides pricing information

**Dependencies:**
- Pricing Calculator
- Cottage Registry
- Slot Manager

---

### Capacity Handler (`capacity_handler.py`)
**What it does:**
- Handles capacity-related queries
- Validates guest counts against cottage capacities
- Recommends cottages based on group size
- Provides capacity information

**Dependencies:**
- Cottage Registry
- Slot Manager

---

### Recommendation Engine (`recommendation_engine.py`)
**What it does:**
- Generates contextual suggestions
- Provides follow-up actions (quick buttons)
- Uses 3-tier system: rule-based + LLM-generated
- Personalizes based on context tracker

**Output:**
- Quick actions (e.g., "Book Now", "Contact Manager")
- Suggestions (e.g., "Check availability for Cottage 7")

---

## Data Flow

### 1. Document Ingestion Flow

```
PDF Files (FAQs)
    ↓
[PDF FAQ Extractor]
    ├─ Extract text using unstructured
    ├─ Parse Q&A pairs from tables
    ├─ Assign categories
    └─ Generate Markdown files
    ↓
Markdown Files (docs/faq/)
    ↓
[Directory Loader]
    ├─ Load .md files
    ├─ Parse YAML frontmatter
    └─ Create Document objects
    ↓
[Text Splitter]
    ├─ Split into chunks (512 chars)
    ├─ Maintain overlap (25 chars)
    └─ Preserve Q&A pairs as single chunks
    ↓
[Embedder]
    ├─ Generate embeddings (384-dim)
    └─ Use all-MiniLM-L6-v2 model
    ↓
[ChromaDB]
    ├─ Store vectors with HNSW index
    ├─ Store metadata (category, FAQ ID, source)
    └─ Persist to disk
```

---

### 2. Query Processing Flow

```
User Query
    ↓
[FastAPI/Streamlit Interface]
    ├─ Receive query
    ├─ Get/create session
    └─ Initialize dependencies
    ↓
[Intent Router]
    ├─ Pattern matching (fast path)
    ├─ LLM classification (fallback)
    └─ Classify intent
    ↓
[Slot Manager]
    ├─ Extract slots (if needed)
    ├─ Validate slots
    └─ Update conversation state
    ↓
[Query Optimizer]
    ├─ Optimize query for RAG
    ├─ Extract entities
    └─ Generate retrieval filters
    ↓
[Question Refinement]
    ├─ Use conversation history
    └─ Convert to standalone question
    ↓
[Vector Search]
    ├─ Embed query
    ├─ Similarity search (top-k)
    ├─ Relevance threshold filtering
    └─ Metadata filtering
    ↓
[Document Relevance Check]
    ├─ Validate retrieved documents
    └─ Filter mismatched documents
    ↓
[Context Synthesis Strategy]
    ├─ Select strategy (create-and-refine, tree, async-tree)
    ├─ Combine retrieved documents
    └─ Generate context
    ↓
[LLM Generation]
    ├─ Select model (fast/reasoning based on complexity)
    ├─ Generate prompt with context
    ├─ Stream response tokens
    └─ Extract final answer
    ↓
[Post-Processing]
    ├─ Extract reasoning tags (if applicable)
    ├─ Format response
    ├─ Generate follow-up actions
    └─ Update chat history
    ↓
Response to User
```

---

### 3. Specialized Query Flow (Pricing/Booking)

```
User Query: "What's the price for Cottage 7 for 4 guests from Jan 15-20?"
    ↓
[Intent Router] → PRICING intent
    ↓
[Slot Manager]
    ├─ Extract: cottage_id="cottage_7", guests=4, dates="2025-01-15 to 2025-01-20"
    └─ Validate slots
    ↓
[Pricing Handler]
    ├─ Get cottage info from registry
    ├─ Calculate price using pricing calculator
    └─ Format response
    ↓
[Response] → "Cottage 7 costs $X for 4 guests from Jan 15-20..."
```

---

## Key Modules and Their Functions

### API Module (`chatbot/api/`)

**main.py:**
- `/api/chat` - Main chat endpoint (non-streaming)
- `/api/chat/stream` - Streaming chat endpoint
- `/api/health` - Health check
- `/api/sessions/{session_id}/clear` - Clear session
- `/api/images/{cottage_number}` - Get cottage images
- `/api/images` - List all images

**dependencies.py:**
- `get_llm_client()` - Get main LLM client
- `get_fast_llm_client()` - Get fast LLM (Groq)
- `get_reasoning_llm_client()` - Get reasoning LLM
- `get_vector_store()` - Get ChromaDB instance
- `get_intent_router()` - Get intent router
- `get_ctx_synthesis_strategy()` - Get synthesis strategy

**session_manager.py:**
- Manages chat history per session
- Stores conversation context
- Clears sessions on demand

**models.py:**
- `ChatRequest` - Request model
- `ChatResponse` - Response model
- `HealthResponse` - Health check model
- `SourceInfo` - Source document info

---

### Conversation Module (`chatbot/bot/conversation/`)

**conversation_handler.py:**
- `refine_question()` - Refine questions with context
- `answer()` - Simple Q&A without RAG
- `answer_with_context()` - RAG-based answer generation

**intent_router.py:**
- `classify()` - Classify user intent
- Pattern matching + LLM fallback

**slot_manager.py:**
- `extract_slots()` - Extract structured data
- `get_slots()` - Get current slots
- `update_slots()` - Update slot values
- `should_extract_slots()` - Determine if slots needed

**query_optimizer.py:**
- `optimize_query_for_rag()` - Optimize for RAG
- `extract_entities_for_retrieval()` - Extract entities
- `get_retrieval_filter()` - Create filters
- `is_complex_query()` - Classify complexity

**pricing_handler.py:**
- `handle_pricing_query()` - Handle pricing queries
- Uses Pricing Calculator + Cottage Registry

**capacity_handler.py:**
- `handle_capacity_query()` - Handle capacity queries
- Validates and recommends cottages

**recommendation_engine.py:**
- `generate_contextual_suggestions()` - Rule-based suggestions
- `generate_llm_recommendations()` - LLM-generated suggestions
- `generate_follow_up_actions()` - Quick actions

---

### Client Module (`chatbot/bot/client/`)

**groq_client.py:**
- `GroqClient` - Groq API client
- Fast cloud-based inference
- Streaming support

**lama_cpp_client.py:**
- `LamaCppClient` - Local llama.cpp client
- Offline inference
- GPU/CPU support
- Auto-download models

**prompt.py:**
- Prompt templates for different scenarios
- Q&A prompts
- Context-aware prompts
- Refinement prompts

---

### Memory Module (`chatbot/bot/memory/`)

**embedder.py:**
- `Embedder` - Embedding generator
- Uses sentence-transformers
- Model: all-MiniLM-L6-v2

**vector_database/chroma.py:**
- `Chroma` - ChromaDB wrapper
- `from_chunks()` - Add documents
- `similarity_search()` - Basic search
- `similarity_search_with_threshold()` - Filtered search

---

### Document Processing Module (`chatbot/document_loader/`)

**loader.py:**
- `DirectoryLoader` - Load documents from directory
- Supports Markdown, PDF, etc.
- Parses YAML frontmatter

**text_splitter.py:**
- `RecursiveCharacterTextSplitter` - Split documents
- Format-aware splitting (Markdown)
- Preserves Q&A pairs

**format.py:**
- Format definitions
- Separator hierarchies

---

## Integration Points

### 1. Streamlit ↔ FastAPI
- Streamlit apps can use FastAPI endpoints
- Shared dependencies (LLM clients, vector store)
- Session management coordination

### 2. WordPress ↔ FastAPI
- WordPress widget calls `/api/chat` or `/api/chat/stream`
- Returns JSON responses
- Supports streaming for real-time updates

### 3. Vector Store ↔ LLM
- Vector store provides context
- LLM generates answers from context
- Context synthesis strategies combine multiple documents

### 4. Intent Router ↔ Handlers
- Intent router classifies queries
- Routes to specialized handlers (pricing, capacity, etc.)
- Handlers use slot manager for structured data

### 5. Slot Manager ↔ Extractors
- Date Extractor - Parses dates
- Number Extractor - Extracts guests, cottage numbers
- LLM extraction - Fallback for complex cases

---

## Deployment Architecture

### Local Deployment

**Components:**
- Streamlit server (single process)
- FastAPI server (optional, for API access)
- Local model files (GGUF format)
- ChromaDB (file-based, persistent)
- Vector store (local filesystem)

**File Structure:**
```
project_root/
├── models/                    # GGUF model files
├── vector_store/              # ChromaDB persistent storage
├── docs/                      # Source documents
│   └── faq/                   # Extracted FAQs
├── chatbot/                   # Application code
│   ├── api/                   # FastAPI endpoints
│   ├── bot/                   # Core bot functionality
│   ├── document_loader/       # Document processing
│   └── ...
├── scripts/                   # Utility scripts
└── tests/                     # Test suite
```

### Production Deployment

**Components:**
- FastAPI server (main API)
- Nginx (reverse proxy, static files)
- Streamlit (optional, for admin interface)
- ChromaDB (persistent storage)
- Model files (local or remote storage)

**Environment Variables:**
- `GROQ_API_KEY` - Groq API key (optional)
- `FAST_MODEL_NAME` - Fast model name (default: llama-3.1-8b-instant)
- `VECTOR_STORE_PATH` - Path to vector store
- `MODEL_FOLDER` - Path to model files

---

## Summary

This architecture provides:

1. **Modular Design** - Each component has clear responsibilities
2. **Scalability** - Can handle multiple concurrent users
3. **Flexibility** - Supports multiple LLM backends (Groq, local)
4. **Extensibility** - Easy to add new intents, handlers, models
5. **Reliability** - Fallback mechanisms at multiple levels
6. **Context-Awareness** - Maintains conversation history and context
7. **Specialized Handling** - Domain-specific handlers for pricing, booking, etc.

The system is designed to be production-ready with proper error handling, logging, and monitoring capabilities.
