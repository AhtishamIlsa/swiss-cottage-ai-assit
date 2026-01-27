"""
Google Sheets FAQ Extractor

Extracts FAQ data from Google Sheets CSV export and generates properly formatted
Markdown files with correct Q&A pairs.

Usage:
1. Export Google Sheets to CSV: File > Download > CSV
2. Run: python chatbot/google_sheets_faq_extractor.py --csv path/to/exported.csv
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

try:
    from helpers.log import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)


def sanitize_filename(text: str) -> str:
    """Sanitize text for use in filenames."""
    # Replace spaces and special chars with underscores
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text.strip('_')


def format_qa_for_embedding(qa_pair: dict) -> str:
    """Format Q&A pair for embedding."""
    category = qa_pair.get('category', 'General')
    question = qa_pair.get('question', '')
    answer = qa_pair.get('answer', '')
    
    formatted = f"Category: {category}\n\n"
    formatted += f"Question: {question}\n\n"
    formatted += f"Answer: {answer}\n"
    
    return formatted


def extract_faq_from_csv(csv_path: Path) -> list[dict]:
    """
    Extract Q&A pairs from CSV file exported from Google Sheets.
    
    Expected CSV structure:
    - Row 1: Headers (Category, #, Question, Answer, Account/Resource, Link, ...)
    - Row 2+: Data rows
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        List of dictionaries containing Q&A pairs with metadata
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    logger.info(f"Extracting FAQ data from CSV: {csv_path}")
    
    qa_pairs = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        # Try to detect delimiter
        sample = f.read(1024)
        f.seek(0)
        sniffer = csv.Sniffer()
        delimiter = sniffer.sniff(sample).delimiter
        
        # Read first row (might be empty)
        first_row = f.readline()
        f.seek(0)
        
        # Read all rows to find header row
        all_rows = list(csv.reader(f, delimiter=delimiter))
        
        # Find header row (first row with non-empty values in expected columns)
        header_row_idx = 0
        for i, row in enumerate(all_rows):
            # Check if this row has Category, Question, Answer headers
            row_str = ' '.join(str(cell).lower() for cell in row)
            if 'category' in row_str and 'question' in row_str and 'answer' in row_str:
                header_row_idx = i
                break
        
        # Use header row as fieldnames
        headers = all_rows[header_row_idx] if header_row_idx < len(all_rows) else all_rows[0]
        
        # Skip to data rows (after header)
        data_rows = all_rows[header_row_idx + 1:]
        
        logger.info(f"Found headers at row {header_row_idx}: {headers}")
        logger.info(f"Found {len(data_rows)} data rows")
        
        # Map headers (case-insensitive)
        # Handle CSV with empty first column
        category_col = None
        number_col = None
        question_col = None
        answer_col = None
        link_col = None
        
        for i, header in enumerate(headers):
            header_lower = str(header).lower().strip()
            if 'category' in header_lower and header_lower != '':
                category_col = i
            elif header_lower in ['#', 'number', 'no', 'num'] and header_lower != '':
                number_col = i
            elif 'question' in header_lower and header_lower != '':
                question_col = i
            elif 'answer' in header_lower and header_lower != '':
                answer_col = i
            elif 'link' in header_lower and header_lower != '':
                link_col = i
        
        # Fallback: use position if headers not found (skip first empty column)
        # Based on actual CSV: empty, Category, #, Question, Answer, empty, Account/Resource, Link
        if category_col is None:
            # Find first non-empty column that might be category
            for i, header in enumerate(headers):
                if str(header).strip() and 'category' in str(header).lower():
                    category_col = i
                    break
            if category_col is None:
                category_col = 1  # Usually column 1 after empty first column
        
        if number_col is None:
            for i, header in enumerate(headers):
                if str(header).strip() in ['#', 'number', 'no', 'num']:
                    number_col = i
                    break
            if number_col is None:
                number_col = 2  # Usually column 2
        
        if question_col is None:
            for i, header in enumerate(headers):
                if str(header).strip() and 'question' in str(header).lower():
                    question_col = i
                    break
            if question_col is None:
                question_col = 3  # Usually column 3
        
        if answer_col is None:
            for i, header in enumerate(headers):
                if str(header).strip() and 'answer' in str(header).lower():
                    answer_col = i
                    break
            if answer_col is None:
                answer_col = 4  # Usually column 4
        
        logger.info(f"Column mapping: Category={category_col}, Number={number_col}, Question={question_col}, Answer={answer_col}")
        
        row_num = header_row_idx
        current_category = "General & About"
        
        # Convert rows to dict format for easier access
        for row_data in data_rows:
            row_num += 1
            
            # Skip empty rows
            if not any(str(cell).strip() for cell in row_data):
                continue
            
            # Get values directly by column index
            category = ""
            number_str = ""
            question = ""
            answer = ""
            link = ""
            
            if category_col < len(row_data):
                category = str(row_data[category_col]).strip()
            
            if number_col < len(row_data):
                number_str = str(row_data[number_col]).strip()
            
            if question_col < len(row_data):
                question = str(row_data[question_col]).strip()
            
            if answer_col < len(row_data):
                answer = str(row_data[answer_col]).strip()
            
            if link_col and link_col < len(row_data):
                link = str(row_data[link_col]).strip()
            
            # Update category if present
            if category and category not in ["", "Category"]:
                current_category = category
            
            # Skip if no question or answer
            if not question or not answer:
                logger.warning(f"Row {row_num}: Skipping - missing question or answer")
                continue
            
            # Skip header rows
            if question.lower() in ["question", "questions"] or answer.lower() in ["answer", "answers"]:
                continue
            
            # Extract question number
            question_num = None
            if number_str:
                # Try to extract number
                match = re.search(r'\d+', number_str)
                if match:
                    question_num = int(match.group())
                else:
                    question_num = row_num - 1  # Use row number as fallback
            
            if question_num is None:
                question_num = row_num - 1
            
            # Clean answer - remove extra whitespace
            answer = re.sub(r'\s+', ' ', answer).strip()
            
            # Skip if answer is too short or looks like a question
            if len(answer) < 10:
                logger.warning(f"Row {row_num}: Answer too short: {answer[:50]}")
                continue
            
            if answer.endswith('?') and len(answer) < 100:
                logger.warning(f"Row {row_num}: Answer looks like a question: {answer[:50]}")
                continue
            
            # Create Q&A pair
            qa_pair = {
                "faq_id": f"faq_{question_num:03d}",
                "category": current_category,
                "question": question,
                "answer": answer,
                "source": "Google Sheets",  # Don't include file path
                "question_number": question_num,
                "link": link if link else None,
            }
            
            qa_pairs.append(qa_pair)
            logger.debug(f"Extracted FAQ {question_num}: {question[:50]}...")
    
    logger.info(f"Extracted {len(qa_pairs)} Q&A pairs from CSV")
    return qa_pairs


def generate_markdown_files(qa_pairs: list[dict], output_dir: Path) -> None:
    """
    Generate Markdown files with YAML frontmatter for each Q&A pair.
    
    Args:
        qa_pairs: List of Q&A dictionaries
        output_dir: Directory to save Markdown files
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Generating {len(qa_pairs)} Markdown files in {output_dir}")
    
    for qa_pair in qa_pairs:
        # Format content for embedding
        formatted_content = format_qa_for_embedding(qa_pair)
        
        # Add link to answer if available
        if qa_pair.get('link'):
            formatted_content += f"\n\n{qa_pair['link']}\n"
        
        # Create frontmatter
        question_escaped = qa_pair.get('question', '').replace('"', '\\"')
        frontmatter = f"""---
category: "{qa_pair.get('category', 'General')}"
faq_id: "{qa_pair.get('faq_id', 'unknown')}"
source: "{qa_pair.get('source', 'Google Sheets')}"
question: "{question_escaped}"
type: "qa_pair"
---

"""
        
        # Combine frontmatter and content
        markdown_content = frontmatter + formatted_content
        
        # Generate filename
        category_safe = sanitize_filename(qa_pair.get("category", "general"))
        faq_id = qa_pair.get("faq_id", "unknown")
        filename = f"{category_safe}_{faq_id}.md"
        
        # Write file
        file_path = output_dir / filename
        file_path.write_text(markdown_content, encoding="utf-8")
        
        logger.debug(f"Created: {filename}")
    
    logger.info(f"Successfully generated {len(qa_pairs)} Markdown files")


def build_vector_index(
    docs_path: Path, vector_store_path: str, chunk_size: int = 512, chunk_overlap: int = 25
) -> None:
    """
    Build vector index from Markdown files.
    
    Args:
        docs_path: Path to directory containing Markdown files
        vector_store_path: Path to vector store directory
        chunk_size: Size of text chunks for embedding
        chunk_overlap: Overlap between chunks
    """
    from bot.memory.embedder import Embedder
    from bot.memory.vector_database.chroma import Chroma
    
    logger.info(f"Building vector index from {docs_path} to {vector_store_path}")
    
    # Use the same approach as pdf_faq_extractor
    from document_loader.format import Format
    from document_loader.loader import DirectoryLoader
    from document_loader.text_splitter import create_recursive_text_splitter
    from entities.document import Document
    
    logger.info(f"Loading documents from: {docs_path}")
    loader = DirectoryLoader(path=docs_path, glob="**/*.md", show_progress=True, recursive=True)
    sources = loader.load()
    logger.info(f"Number of loaded documents: {len(sources)}")
    
    logger.info("Chunking documents...")
    chunks = []
    splitter = create_recursive_text_splitter(
        format=Format.MARKDOWN.value, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    
    # Handle Q&A pairs specially - keep them together
    for doc in sources:
        # Check if this is a Q&A pair
        if doc.metadata.get("type") == "qa_pair":
            # Only split if content is very long (>1000 words)
            word_count = len(doc.page_content.split())
            if word_count > 1000:
                # Split long Q&A pairs
                doc_chunks = splitter.split_documents([doc])
                chunks.extend(doc_chunks)
            else:
                # Keep Q&A pair as single chunk
                chunks.append(doc)
        else:
            # Regular document - split normally
            doc_chunks = splitter.split_documents([doc])
            chunks.extend(doc_chunks)
    
    logger.info(f"Number of generated chunks: {len(chunks)}")
    
    logger.info("Creating memory index...")
    embedding = Embedder()
    vector_store = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
    vector_store.from_chunks(chunks)
    logger.info("Memory Index has been created successfully!")


def get_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract FAQ data from Google Sheets CSV export"
    )
    
    parser.add_argument(
        "--csv",
        type=str,
        required=True,
        help="Path to CSV file exported from Google Sheets"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="docs/faq",
        help="Output directory for Markdown files (default: docs/faq)"
    )
    
    parser.add_argument(
        "--vector-store",
        type=str,
        default="vector_store",
        help="Path to vector store directory (default: vector_store)"
    )
    
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip building vector index"
    )
    
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Chunk size for embedding (default: 512)"
    )
    
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=25,
        help="Chunk overlap for embedding (default: 25)"
    )
    
    return parser.parse_args()


def main(parameters) -> None:
    """Main execution function."""
    root_folder = Path(__file__).resolve().parent.parent
    csv_path = Path(parameters.csv)
    if not csv_path.is_absolute():
        csv_path = root_folder / csv_path
    
    output_dir = Path(parameters.output)
    if not output_dir.is_absolute():
        output_dir = root_folder / output_dir
    
    vector_store_path = parameters.vector_store
    if not Path(vector_store_path).is_absolute():
        vector_store_path = str(root_folder / vector_store_path)
    
    # Step 1: Extract Q&A pairs from CSV
    qa_pairs = extract_faq_from_csv(csv_path)
    
    if not qa_pairs:
        logger.error("No Q&A pairs extracted from CSV. Please check the CSV format.")
        sys.exit(1)
    
    # Step 2: Generate Markdown files
    generate_markdown_files(qa_pairs, output_dir)
    
    # Step 3: Build vector index (optional)
    if not parameters.skip_index:
        # Remove old vector store if exists
        vector_store_dir = Path(vector_store_path)
        if vector_store_dir.exists():
            logger.info(f"Removing old vector store at {vector_store_path}")
            import shutil
            shutil.rmtree(vector_store_dir)
        
        build_vector_index(output_dir, vector_store_path, parameters.chunk_size, parameters.chunk_overlap)
    else:
        logger.info("Skipping vector index build (--skip-index flag set)")


if __name__ == "__main__":
    try:
        args = get_args()
        main(args)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
