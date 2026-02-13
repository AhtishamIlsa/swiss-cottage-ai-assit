"""Build vector store from JSON FAQ file."""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent.parent
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from helpers.log import get_logger
from entities.document import Document
from bot.memory.embedder import Embedder
from bot.memory.vector_database.chroma import Chroma
from document_loader.text_splitter import create_recursive_text_splitter
from document_loader.format import Format

logger = get_logger(__name__)


def format_faq_for_embedding(faq: Dict[str, Any]) -> str:
    """
    Format FAQ for embedding with links included.
    
    Args:
        faq: FAQ dictionary with id, category, question, answer, links
        
    Returns:
        Formatted text string for embedding
    """
    faq_id = faq.get("id", "unknown")
    category = faq.get("category", "General")
    question = faq.get("question", "")
    answer = faq.get("answer", "")
    links = faq.get("links", [])
    
    # Build formatted text
    formatted = f"FAQ #{faq_id} - {category}\n\n"
    formatted += f"Question: {question}\n\n"
    formatted += f"Answer: {answer}\n"
    
    # Add links section if available
    if links:
        formatted += "\nUseful Links:\n"
        for link in links:
            name = link.get("name", "")
            url = link.get("url", "")
            if name and url:
                formatted += f"- [{name}]({url})\n"
    
    return formatted


def build_vector_store_from_json(
    json_path: Path,
    vector_store_path: str,
    chunk_size: int = 512,
    chunk_overlap: int = 25
) -> None:
    """
    Build vector store from JSON FAQ file.
    
    Args:
        json_path: Path to JSON file containing FAQs
        vector_store_path: Path to vector store directory
        chunk_size: Chunk size for splitting long FAQs (default: 512)
        chunk_overlap: Chunk overlap for splitting (default: 25)
    """
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    
    logger.info(f"Loading FAQs from JSON: {json_path}")
    
    # Load JSON file
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    faqs = data.get("faqs", [])
    logger.info(f"Loaded {len(faqs)} FAQs from JSON")
    
    # Create text splitter for long FAQs
    splitter = create_recursive_text_splitter(
        format=Format.MARKDOWN.value,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    
    # Process FAQs into documents
    documents = []
    split_count = 0
    
    for faq in faqs:
        faq_id = faq.get("id", "unknown")
        word_count = faq.get("word_count", 0)
        should_split = faq.get("should_split", False)
        
        # Format FAQ text for embedding
        formatted_text = format_faq_for_embedding(faq)
        
        # Create metadata
        # ChromaDB only accepts str, int, float, or bool in metadata
        # Convert lists to JSON strings
        metadata = {
            "id": faq_id,
            "category": faq.get("category", "General"),
            "question": faq.get("question", ""),
            "tags": json.dumps(faq.get("tags", [])),  # Store tags as JSON string
            "priority": faq.get("priority", 1),
            "type": "qa_pair",
            "links": json.dumps(faq.get("links", []))  # Store links as JSON string
        }
        
        # Split if needed
        if should_split and word_count > 1000:
            # Create temporary document for splitting
            temp_doc = Document(page_content=formatted_text, metadata=metadata)
            chunks = splitter.split_documents([temp_doc])
            
            # Add chunk index to metadata
            for idx, chunk in enumerate(chunks):
                chunk.metadata["chunk_index"] = idx
                chunk.metadata["total_chunks"] = len(chunks)
            
            documents.extend(chunks)
            split_count += 1
            logger.debug(f"Split FAQ {faq_id} into {len(chunks)} chunks ({word_count} words)")
        else:
            # Keep as single document
            doc = Document(page_content=formatted_text, metadata=metadata)
            documents.append(doc)
    
    logger.info(f"Created {len(documents)} documents ({split_count} FAQs were split)")
    
    # Build vector store
    logger.info("Creating vector store...")
    embedding = Embedder()
    vector_store = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
    
    # Remove old collection if it exists (to rebuild from scratch)
    try:
        vector_store.client.delete_collection(name=vector_store.collection_name)
        logger.info(f"Removed old collection '{vector_store.collection_name}'")
    except Exception as e:
        logger.debug(f"Could not delete old collection (may not exist): {e}")
    
    # Create new collection and add documents
    vector_store.from_chunks(documents)
    
    logger.info(f"✅ Vector store created successfully at {vector_store_path}")
    logger.info(f"   Total embeddings: {len(documents)}")
    logger.info(f"   FAQs split: {split_count}")


def main():
    """Main function to build vector store from JSON."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Build vector store from JSON FAQ file")
    parser.add_argument(
        "--json",
        type=str,
        default="docs/faqs.json",
        help="Path to JSON file (default: docs/faqs.json)"
    )
    parser.add_argument(
        "--vector-store",
        type=str,
        default="vector_store/faqs_index",
        help="Path to vector store directory (default: vector_store/faqs_index)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Chunk size for splitting long FAQs (default: 512)"
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=25,
        help="Chunk overlap for splitting (default: 25)"
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    project_root = Path(__file__).parent.parent.parent
    
    json_path = Path(args.json)
    if not json_path.is_absolute():
        json_path = project_root / json_path
    
    vector_store_path = Path(args.vector_store)
    if not vector_store_path.is_absolute():
        vector_store_path = project_root / vector_store_path
    
    if not json_path.exists():
        logger.error(f"JSON file not found: {json_path}")
        sys.exit(1)
    
    # Build vector store
    build_vector_store_from_json(
        json_path,
        str(vector_store_path),
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap
    )
    
    logger.info("✅ Vector store build complete!")


if __name__ == "__main__":
    main()
