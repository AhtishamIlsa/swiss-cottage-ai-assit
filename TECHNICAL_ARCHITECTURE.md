# Technical Architecture Overview

## Executive Summary

This document provides a comprehensive technical architecture overview of the **RAG (Retrieval-Augmented Generation) Chatbot System** - an intelligent question-answering system that combines document retrieval, vector embeddings, and large language models to provide context-aware responses based on a knowledge base.

---

## 1. System Architecture Overview

### 1.1 High-Level Architecture

The system follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│              (Streamlit Web Interface)                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                  Application Layer                           │
│         (RAG Chatbot App / Conversation Handler)            │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐
│  LLM Layer   │ │  Memory     │ │ Document   │
│              │ │  Layer       │ │ Processing │
│  - Groq API  │ │  - Embedder  │ │  Layer     │
│  - llama.cpp │ │  - ChromaDB  │ │  - Loader  │
│              │ │              │ │  - Splitter │
└──────────────┘ └──────────────┘ └────────────┘
```

### 1.2 Core Principles

- **Modularity**: Each component is independently testable and replaceable
- **Extensibility**: Plugin-based model registry and synthesis strategies
- **Performance**: Caching, streaming responses, and parallel processing options
- **Reliability**: Fallback mechanisms (Groq → local model, refined → original query)
- **Context-Awareness**: Conversation history and document relevance validation

---

## 2. Component Architecture

### 2.1 Presentation Layer

**Technology**: Streamlit 1.37.0

**Components**:
- `chatbot/rag_chatbot_app.py` - Main Streamlit application
- `chatbot/chatbot_app.py` - Simple conversation-aware chatbot

**Features**:
- Real-time chat interface with message history
- Streaming token-by-token response display
- Source document preview and citation
- Sidebar configuration (model selection, synthesis strategy, parameters)
- Session state management for conversation persistence

**Key Functions**:
- `load_llm_client()` - Cached LLM client initialization
- `load_index()` - Cached vector database loading
- `init_chat_history()` - Conversation state management

### 2.2 Application Layer

#### 2.2.1 Conversation Handler
**File**: `chatbot/bot/conversation/conversation_handler.py`

**Responsibilities**:
- Question refinement using conversation history
- Context-aware answer generation
- Reasoning tag extraction (for models that support it)

**Key Functions**:
- `refine_question()` - Converts follow-up questions to standalone queries
- `answer_with_context()` - Orchestrates retrieval and generation

#### 2.2.2 Context Synthesis Strategies
**File**: `chatbot/bot/conversation/ctx_strategy.py`

**Strategy Pattern Implementation**:

1. **Create-and-Refine Strategy** (Fastest: 30-60s)
   - Sequential refinement through retrieved documents
   - Initial answer from first chunk, then refine with subsequent chunks
   - Best for: Real-time interactions

2. **Tree Summarization Strategy** (Medium: 2-5 min)
   - Hierarchical combination of answers
   - Generate answer per chunk, then combine pairwise
   - Best for: Comprehensive answers

3. **Async Tree Summarization Strategy** (Slowest: 5-10+ min)
   - Parallel processing of chunks
   - Async hierarchical combination
   - Best for: Maximum quality with parallel resources

#### 2.2.3 Chat History Management
**File**: `chatbot/bot/conversation/chat_history.py`

**Features**:
- Maintains conversation context (configurable length)
- Enables follow-up question understanding
- Session-based storage

### 2.3 LLM Layer

#### 2.3.1 Model Clients

**Groq Client** (`chatbot/bot/client/groq_client.py`)
- **Type**: Cloud API (Fast inference)
- **Default Model**: `llama-3.1-8b-instant`
- **Features**: 
  - Streaming support
  - Fast response times
  - Requires API key

**Local LLM Client** (`chatbot/bot/client/lama_cpp_client.py`)
- **Type**: Local inference via llama.cpp
- **Technology**: `llama-cpp-python`
- **Model Format**: GGUF (quantized)
- **Features**:
  - Offline operation
  - GPU/CPU support
  - Auto-download models
  - Streaming support

#### 2.3.2 Model Registry
**File**: `chatbot/bot/model/model_registry.py`

**Supported Models**:
- Llama 3.1/3.2 (1B, 3B, 8B)
- Qwen 2.5 (3B, with math reasoning variant)
- DeepSeek R1 (7B, experimental)
- OpenChat 3.5/3.6 (7B, 8B)
- Starling (7B)
- Phi-3.5 (3.8B)
- StableLM Zephyr (3B)

**Model Settings** (`chatbot/bot/model/settings/`):
- System templates
- Model file names and download URLs
- Configuration (temperature, top_p, etc.)
- Reasoning tags support

#### 2.3.3 Prompt Templates
**File**: `chatbot/bot/client/prompt.py`

**Templates**:
- `QA_PROMPT_TEMPLATE` - Simple Q&A
- `CTX_PROMPT_TEMPLATE` - Context-aware Q&A
- `REFINED_CTX_PROMPT_TEMPLATE` - Refine existing answer
- `REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE` - Question refinement
- `REFINED_ANSWER_CONVERSATION_AWARENESS_PROMPT_TEMPLATE` - Answer with history

### 2.4 Memory Layer (Vector Database)

#### 2.4.1 Embedding Generation
**File**: `chatbot/bot/memory/embedder.py`

**Technology**: 
- Library: `sentence-transformers`
- Model: `all-MiniLM-L6-v2`
- Dimensions: 384
- Max Tokens: 512

**Methods**:
- `embed_documents()` - Batch embedding for documents
- `embed_query()` - Single embedding for queries

#### 2.4.2 Vector Database
**File**: `chatbot/bot/memory/vector_database/chroma.py`

**Technology**: ChromaDB 0.4.18

**Storage Structure**:
```
vector_store/
├── chroma.sqlite3          # Metadata database
└── {uuid}/                  # Vector data directories
    ├── data_level0.bin      # Vector data
    ├── header.bin           # Header information
    ├── length.bin           # Length information
    └── link_lists.bin       # HNSW index links
```

**Features**:
- Persistent storage
- HNSW (Hierarchical Navigable Small World) indexing
- Cosine similarity search
- Relevance threshold filtering
- Metadata filtering

**Key Methods**:
- `from_chunks()` - Add documents to vector store
- `similarity_search_with_threshold()` - Retrieve relevant documents
- `similarity_search()` - Basic similarity search

#### 2.4.3 Distance Metrics
**File**: `chatbot/bot/memory/vector_database/distance_metric.py`

**Metrics**:
- L2 (Euclidean) distance
- Relevance score conversion (0-1 range)

### 2.5 Document Processing Layer

#### 2.5.1 Document Loader
**File**: `chatbot/document_loader/loader.py`

**Class**: `DirectoryLoader`

**Features**:
- Recursive directory scanning
- Multiple file format support (Markdown, PDF, etc.)
- Uses `unstructured` library for text extraction
- Creates `Document` objects with metadata

#### 2.5.2 Text Splitter
**File**: `chatbot/document_loader/text_splitter.py`

**Class**: `RecursiveCharacterTextSplitter`

**Algorithm**:
1. **Format Detection**: Identifies document format (Markdown, etc.)
2. **Separator Hierarchy**: Tries separators in order of semantic importance
   - Markdown: `["\n#{1,6} ", "```\n", "\n\n", "\n", " ", ""]`
3. **Recursive Splitting**: 
   - Tries first separator (e.g., headings)
   - If chunks too large, recursively tries next separator
4. **Merge Strategy**: 
   - Combines small splits up to `chunk_size`
   - Maintains `chunk_overlap` for context continuity

**Parameters**:
- `chunk_size`: 512 characters (default)
- `chunk_overlap`: 25 characters (default)
- Special handling: Q&A pairs kept as single chunk if < 1000 words

#### 2.5.3 Format Handlers
**File**: `chatbot/document_loader/format.py`

**Supported Formats**:
- Markdown
- Extensible to other formats

#### 2.5.4 PDF FAQ Extractor
**File**: `chatbot/pdf_faq_extractor.py`

**Process**:
1. Extract text from PDF using `unstructured`
2. Parse table structure to identify Q&A pairs
3. Extract categories and metadata
4. Generate Markdown files with YAML frontmatter
5. Build vector index from extracted FAQs

**Output**: Structured Markdown files in `docs/faq/` directory

### 2.6 Data Models

#### 2.6.1 Document Entity
**File**: `chatbot/entities/document.py`

```python
@dataclass
class Document:
    page_content: str      # Text content
    metadata: dict         # Source, category, FAQ ID, etc.
    type: Literal["Document"] = "Document"
```

---

## 3. Data Flow Architecture

### 3.1 Document Ingestion Flow

```
PDF/Markdown Files
    ↓
[PDF Extractor / Directory Loader]
    ↓
Text Extraction (unstructured library)
    ↓
[Text Splitter]
    ↓
Document Chunks
    ↓
[Embedder]
    ↓
Vector Embeddings (384-dim)
    ↓
[ChromaDB]
    ↓
Persistent Vector Store
```

### 3.2 Query Processing Flow

```
User Query
    ↓
[Question Refinement]
    ├─ Uses conversation history
    └─ Converts to standalone question
    ↓
[Vector Search]
    ├─ Embed query
    ├─ Similarity search (top-k)
    └─ Relevance threshold filtering
    ↓
[Document Relevance Validation]
    ├─ Location mismatch detection
    └─ Intent validation
    ↓
[Context Synthesis Strategy]
    ├─ Create-and-Refine
    ├─ Tree Summarization
    └─ Async Tree Summarization
    ↓
[LLM Generation]
    ├─ Groq API (fast)
    └─ Local llama.cpp (offline)
    ↓
[Streaming Response]
    └─ Token-by-token display
    ↓
[Chat History Update]
    └─ Store Q&A for context
```

### 3.3 Error Handling & Fallbacks

1. **LLM Client Fallback**: Groq API → Local llama.cpp
2. **Query Fallback**: Refined query → Original query
3. **Search Fallback**: Threshold search → Basic similarity search
4. **Relevance Validation**: Prevents hallucination from mismatched documents

---

## 4. Technology Stack

### 4.1 Core Dependencies

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **LLM Framework** | llama-cpp-python | Latest | Local model inference |
| **Cloud LLM** | groq | 0.11.0 | Fast cloud inference |
| **Vector DB** | chromadb | 0.4.18 | Vector storage & search |
| **Embeddings** | sentence-transformers | 5.0.0 | Text embeddings |
| **UI Framework** | streamlit | 1.37.0 | Web interface |
| **Document Processing** | unstructured | 0.14.3 | PDF/text extraction |
| **ML Framework** | torch | 2.1.2 | Deep learning backend |
| **Text Processing** | clean-text | 0.6.0 | Text cleaning |
| **Async Support** | nest_asyncio | 1.5.8 | Async operations |

### 4.2 Development Tools

- **Package Manager**: Poetry 1.7.0+
- **Testing**: pytest, pytest-cov, pytest-asyncio
- **Code Quality**: ruff 0.6.4, pre-commit
- **Python Version**: 3.10 (strict)

### 4.3 Hardware Requirements

- **CPU**: Modern multi-core processor
- **GPU**: Optional (CUDA 12.1+ or Metal for macOS)
- **RAM**: 8GB+ (16GB+ recommended for local models)
- **Storage**: 5-10GB for models and vector store

---

## 5. Deployment Architecture

### 5.1 Local Deployment

**Components**:
- Streamlit server (single process)
- Local model files (GGUF format)
- ChromaDB (file-based, persistent)
- Vector store (local filesystem)

**File Structure**:
```
project_root/
├── models/                    # GGUF model files
├── vector_store/              # ChromaDB persistent storage
├── docs/                      # Source documents
│   └── faq/                   # Extracted FAQs
├── chatbot/                   # Application code
└── tests/                     # Test suite
```

### 5.2 Configuration

**Environment Variables**:
- `GROQ_API_KEY` - Optional, for Groq API access

**Command-Line Arguments**:
- `--model` - Model selection
- `--synthesis-strategy` - Context synthesis method
- `--k` - Number of retrieved chunks
- `--max-new-tokens` - Response length limit
- `--groq-api-key` - Groq API key override

### 5.3 Caching Strategy

**Streamlit Caching**:
- `@st.cache_resource()` for:
  - LLM client initialization
  - Vector index loading
  - Chat history
  - Context synthesis strategy

**Cache Invalidation**:
- Vector store modification time used as cache version
- Manual cache clearing via Streamlit UI

---

## 6. Design Patterns

### 6.1 Strategy Pattern
- **Context Synthesis Strategies**: Pluggable algorithms for combining retrieved documents
- **Model Registry**: Extensible model configuration system

### 6.2 Factory Pattern
- **Model Settings Factory**: `get_model_settings()` creates appropriate settings
- **Synthesis Strategy Factory**: `get_ctx_synthesis_strategy()` creates strategy instances

### 6.3 Template Method Pattern
- **BaseSynthesisStrategy**: Defines interface, subclasses implement `generate_response()`

### 6.4 Repository Pattern
- **Chroma Vector Database**: Abstracts vector storage operations

---l

## 7. Performance Characteristics

### 7.1 Response Times

| Strategy | Typical Time | Use Case |
|----------|-------------|----------|
| Create-and-Refine | 30-60 seconds | Real-time interactions |
| Tree Summarization | 2-5 minutes | Comprehensive answers |
| Async Tree Summarization | 5-10+ minutes | Maximum quality |

### 7.2 Scalability Considerations

**Vector Database**:
- HNSW indexing for fast approximate nearest neighbor search
- Persistent storage for large document collections
- Batch operations for bulk ingestion

**LLM Inference**:
- Groq API: Handles scaling automatically
- Local llama.cpp: Limited by hardware (GPU recommended)

**Memory Usage**:
- Embeddings: ~384 floats per chunk
- Model: 3-8GB depending on model size and quantization
- Vector store: Grows with document count

---

## 8. Security & Privacy

### 8.1 Data Privacy
- **Local Processing**: All data processing can run entirely offline
- **No External Calls**: When using local models, no data leaves the system
- **Optional Cloud**: Groq API usage is opt-in

### 8.2 API Key Management
- Environment variable storage
- Command-line argument override
- No hardcoded credentials

---

## 9. Extensibility Points

### 9.1 Adding New Models
1. Create settings file in `chatbot/bot/model/settings/`
2. Extend `ModelSettings` base class
3. Register in `model_registry.py`

### 9.2 Adding New Synthesis Strategies
1. Extend `BaseSynthesisStrategy`
2. Implement `generate_response()` method
3. Register in `ctx_strategy.py`

### 9.3 Adding New Document Formats
1. Add format separators in `format.py`
2. Extend `DirectoryLoader` if needed
3. Update text splitter configuration

### 9.4 Adding New Vector Databases
1. Implement interface matching `Chroma` class
2. Update `load_index()` function
3. Maintain embedding compatibility

---

## 10. Testing Architecture

### 10.1 Test Structure
```
tests/
├── bot/
│   ├── client/
│   │   └── test_lamacpp_client.py
│   ├── conversation/
│   │   └── test_conversation_handler.py
│   └── memory/
│       └── vector_database/
│           └── test_chroma.py
├── document_loader/
│   └── test_text_splitter.py
└── conftest.py
```

### 10.2 Testing Tools
- **pytest**: Test framework
- **pytest-cov**: Coverage reporting
- **pytest-mock**: Mocking utilities
- **pytest-asyncio**: Async test support

---

## 11. Monitoring & Logging

### 11.1 Logging
**File**: `chatbot/helpers/log.py`

**Features**:
- Structured logging
- Configurable log levels
- File and console output

**Key Log Points**:
- LLM client initialization
- Query refinement
- Document retrieval
- Answer generation
- Error conditions

---

## 12. Future Architecture Considerations

### 12.1 Potential Enhancements
- **Multi-modal Support**: Image/document understanding
- **Reranking**: Improve retrieval quality with cross-encoders
- **Hybrid Search**: Combine semantic and keyword search
- **Distributed Deployment**: Scale across multiple servers
- **Model Fine-tuning**: Domain-specific model adaptation
- **API Layer**: REST/GraphQL API for programmatic access
- **User Management**: Multi-user support with authentication
- **Analytics**: Usage tracking and performance metrics

### 12.2 Scalability Improvements
- **Vector Database Clustering**: Distributed ChromaDB
- **Model Serving**: Dedicated model server (e.g., vLLM, TensorRT-LLM)
- **Caching Layer**: Redis for frequently accessed data
- **Load Balancing**: Multiple Streamlit instances

---

## Appendix A: Key Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 512 | Maximum characters per chunk |
| `chunk_overlap` | 25 | Overlapping characters between chunks |
| `k` | 2 | Number of chunks to retrieve |
| `max_new_tokens` | 512 | Maximum tokens in response |
| `threshold` | 0.2 | Relevance threshold for retrieval |
| `embedding_dim` | 384 | Embedding vector dimensions |
| `chat_history_length` | 2 | Number of previous Q&A pairs to remember |

---

## Appendix B: File Organization

```
chatbot/
├── bot/                          # Core bot functionality
│   ├── client/                   # LLM clients
│   ├── conversation/             # Conversation handling
│   ├── memory/                   # Vector database & embeddings
│   └── model/                    # Model registry & settings
├── document_loader/               # Document processing
├── entities/                     # Data models
├── helpers/                      # Utilities
├── cli/                          # Command-line interfaces
├── experiments/                  # Experimental code
├── rag_chatbot_app.py            # Main RAG application
├── chatbot_app.py                # Simple chatbot
├── pdf_faq_extractor.py          # PDF extraction
└── memory_builder.py             # Vector index builder
```

---

*Document Version: 1.0*  
*Last Updated: 2025-01-22*
