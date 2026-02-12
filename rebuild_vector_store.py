#!/usr/bin/env python3
"""Simple script to rebuild vector store from markdown files without PDF dependencies."""

import sys
import re
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

# Try to import yaml for frontmatter parsing
try:
    import yaml
    YAML_SUPPORT = True
except ImportError:
    YAML_SUPPORT = False
    logger.warning("yaml not available - frontmatter parsing disabled. Install with: pip install pyyaml")


def clean_metadata(metadata: dict) -> dict:
    """
    Remove None values from metadata dict.
    ChromaDB doesn't accept None values - only str, int, float, or bool.
    """
    return {k: v for k, v in metadata.items() if v is not None}


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
            
            # Parse YAML frontmatter if present
            frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
            match = re.match(frontmatter_pattern, content, re.DOTALL)
            
            if match and YAML_SUPPORT:
                frontmatter_text = match.group(1)
                content_text = match.group(2)
                try:
                    frontmatter = yaml.safe_load(frontmatter_text) or {}
                    # Extract metadata from frontmatter (overrides filename-based metadata)
                    # Only include non-None values
                    if frontmatter.get("intent"):
                        metadata["intent"] = frontmatter.get("intent")
                    if frontmatter.get("cottage_id") is not None:
                        metadata["cottage_id"] = str(frontmatter.get("cottage_id"))  # Convert to string for ChromaDB
                    if frontmatter.get("category"):
                        metadata["category"] = frontmatter.get("category")
                    if frontmatter.get("faq_id"):
                        metadata["faq_id"] = frontmatter.get("faq_id")
                    if frontmatter.get("type"):
                        metadata["type"] = frontmatter.get("type")
                    # Use content without frontmatter
                    content = content_text
                except Exception as e:
                    logger.warning(f"Failed to parse frontmatter for {md_file}: {e}")
            
            # Clean metadata - remove None values before creating Document
            metadata = clean_metadata(metadata)
            
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
