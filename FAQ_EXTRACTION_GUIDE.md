# FAQ Extraction from PDF Guide

## Overview

This guide explains how to extract Q&A pairs from PDF files and build a vector database for RAG-based FAQ chatbot.

## Prerequisites

1. Install dependencies:
   ```bash
   poetry install
   # or
   pip install "unstructured[pdf]" sentence-transformers chromadb
   ```

   **Important**: For PDF extraction, you need `unstructured[pdf]` (not just `unstructured[md]`)

2. Ensure the PDF file is accessible

## Usage

### Basic Usage

Extract FAQ from PDF and build vector index:

```bash
python chatbot/pdf_faq_extractor.py \
    --pdf "Swiss Cottages FAQS - Google Sheets.pdf" \
    --output docs/faq \
    --vector-store vector_store/faq_index
```

### Extract Only (No Vector Index)

Generate Markdown files without building vector index:

```bash
python chatbot/pdf_faq_extractor.py \
    --pdf "Swiss Cottages FAQS - Google Sheets.pdf" \
    --output docs/faq \
    --skip-index
```

### Custom Chunking

Specify custom chunk size and overlap:

```bash
python chatbot/pdf_faq_extractor.py \
    --pdf "Swiss Cottages FAQS - Google Sheets.pdf" \
    --output docs/faq \
    --vector-store vector_store/faq_index \
    --chunk-size 512 \
    --chunk-overlap 25
```

## Output Structure

After extraction, you'll have:

```
docs/
  faq/
    general_abuse_faq_001.md
    general_abuse_faq_002.md
    fragile_media_faq_001.md
    ...

vector_store/
  faq_index/
    (Chroma database files)
```

## Markdown File Format

Each FAQ is saved as a Markdown file with:

- **Frontmatter**: Metadata (category, faq_id, source, question, type)
- **Content**: Formatted Q&A text optimized for embeddings

Example:

```markdown
---
category: "General & Abuse"
faq_id: "faq_001"
source: "Swiss Cottages FAQS - Google Sheets.pdf"
question: "What is Home Collagen Blocker?"
type: "qa_pair"
---

Category: General & Abuse

Question: What is Home Collagen Blocker?

Answer: [The answer text...]
```

## Features

1. **Optimal Embedding Format**: Each Q&A includes category, question, and answer for better semantic matching
2. **Q&A Preservation**: Q&A pairs are kept together (not split) for better retrieval
3. **Metadata Filtering**: Category and question stored in metadata for filtering in Chroma
4. **Flexible Workflow**: Generate Markdown first for review, then build index

## Integration with RAG Chatbot

After building the vector index, update your RAG chatbot to use the FAQ index:

```python
# In rag_chatbot_app.py or similar
vector_store_path = root_folder / "vector_store" / "faq_index"
index = load_index(vector_store_path)
```

## Troubleshooting

### "unstructured module not found" or "partition_pdf is not available"
- Install PDF dependencies: `pip install "unstructured[pdf]"`
- Or update pyproject.toml to include PDF extras: `unstructured = { version = "~=0.14.3", extras = ["md", "pdf"] }`
- Then run: `poetry install`

### "No Q&A pairs extracted"
- Check PDF format - script looks for numbered questions (1., 2., etc.) or questions ending with "?"
- PDF may need manual review or different parsing approach

### Import errors
- Ensure you're running from project root
- Check PYTHONPATH includes project directory
- Use: `PYTHONPATH=/var/www/html/rag-baesd-model python3 chatbot/pdf_faq_extractor.py ...`

## Notes

- Q&A pairs with >1000 words will be split (rare for FAQs)
- Categories are auto-detected from known patterns
- Questions and answers are cleaned (whitespace normalized)
- Each Q&A gets a unique ID (faq_001, faq_002, etc.)
