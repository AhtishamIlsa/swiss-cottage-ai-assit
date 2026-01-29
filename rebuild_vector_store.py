#!/usr/bin/env python3
"""Simple script to rebuild vector store from markdown files without PDF dependencies."""

import sys
from pathlib import Path

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent / "chatbot"
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

from bot.memory.embedder import Embedder
from bot.memory.vector_database.chroma import Chroma
from entities.document import Document
from helpers.log import get_logger

logger = get_logger(__name__)


def load_markdown_files(docs_path: Path) -> list[Document]:
    """Load markdown files directly without using DirectoryLoader."""
    documents = []
    
    for md_file in docs_path.rglob("*.md"):
        try:
            content = md_file.read_text(encoding='utf-8')
            
            # Extract metadata from filename if possible
            metadata = {
                "source": str(md_file.relative_to(docs_path.parent)),
                "file_name": md_file.name,
                "type": "qa_pair" if "faq" in md_file.name.lower() else "document"
            }
            
            # Try to extract FAQ ID from filename (e.g., "Booking_faq_098.md" -> "098")
            if "_faq_" in md_file.name:
                parts = md_file.stem.split("_faq_")
                if len(parts) > 1:
                    metadata["faq_id"] = parts[-1]
            
            doc = Document(page_content=content, metadata=metadata)
            documents.append(doc)
            
        except Exception as e:
            logger.warning(f"Failed to load {md_file}: {e}")
            continue
    
    return documents


def split_chunks(sources: list[Document], chunk_size: int = 512, chunk_overlap: int = 25) -> list[Document]:
    """Simple chunking - keep Q&A pairs together, split long documents."""
    chunks = []
    
    for doc in sources:
        word_count = len(doc.page_content.split())
        
        # Keep Q&A pairs together if not too long
        if doc.metadata.get("type") == "qa_pair" and word_count <= 1000:
            chunks.append(doc)
        else:
            # Simple splitting for long documents
            words = doc.page_content.split()
            for i in range(0, len(words), chunk_size - chunk_overlap):
                chunk_words = words[i:i + chunk_size]
                chunk_content = " ".join(chunk_words)
                
                chunk_metadata = doc.metadata.copy()
                chunk_metadata["chunk_index"] = i // (chunk_size - chunk_overlap)
                
                chunk_doc = Document(page_content=chunk_content, metadata=chunk_metadata)
                chunks.append(chunk_doc)
    
    return chunks


def rebuild_vector_store(docs_path: Path, vector_store_path: Path, chunk_size: int = 512, chunk_overlap: int = 25):
    """Rebuild vector store from markdown files."""
    logger.info(f"Loading markdown files from: {docs_path}")
    sources = load_markdown_files(docs_path)
    logger.info(f"Loaded {len(sources)} documents")
    
    logger.info("Chunking documents...")
    chunks = split_chunks(sources, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    logger.info(f"Generated {len(chunks)} chunks")
    
    logger.info("Creating vector index...")
    embedding = Embedder()
    
    # Remove old vector store if it exists
    if vector_store_path.exists():
        import shutil
        logger.info(f"Removing old vector store at {vector_store_path}")
        shutil.rmtree(vector_store_path)
    
    vector_database = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
    vector_database.from_chunks(chunks)
    logger.info("✅ Vector store rebuilt successfully!")


if __name__ == "__main__":
    root_folder = Path(__file__).resolve().parent
    doc_path = root_folder / "docs" / "faq"
    vector_store_path = root_folder / "vector_store" / "docs_index"
    
    if not doc_path.exists():
        logger.error(f"Document path not found: {doc_path}")
        sys.exit(1)
    
    try:
        rebuild_vector_store(doc_path, vector_store_path, chunk_size=512, chunk_overlap=25)
        logger.info(f"✅ Vector store available at: {vector_store_path}")
    except Exception as e:
        logger.error(f"Failed to rebuild vector store: {e}", exc_info=True)
        sys.exit(1)
