import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    from unstructured.partition.auto import partition
    # Test if PDF support is available by checking if partition_pdf exists
    try:
        import unstructured.partition.pdf
        PDF_SUPPORT = True
    except ImportError:
        PDF_SUPPORT = False
except ImportError:
    partition = None
    PDF_SUPPORT = False

try:
    from helpers.log import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)


def extract_faq_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Extract Q&A pairs from PDF file.

    Args:
        pdf_path: Path to PDF file

    Returns:
        List of dictionaries containing Q&A pairs with metadata
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if partition is None:
        raise ImportError(
            "unstructured module is required. Please install: pip install unstructured[pdf]"
        )

    if not PDF_SUPPORT:
        raise ImportError(
            "PDF support is not available. Please install PDF dependencies: pip install 'unstructured[pdf]'"
        )

    logger.info(f"Extracting FAQ data from PDF: {pdf_path}")

    # Extract text from PDF
    elements = partition(filename=str(pdf_path))
    text_content = "\n\n".join([str(el) for el in elements])

    # Parse the table structure
    qa_pairs = parse_table_structure(elements, text_content, pdf_path)

    logger.info(f"Extracted {len(qa_pairs)} Q&A pairs from PDF")
    return qa_pairs


def parse_table_structure(elements: list, text_content: str, pdf_path: Path) -> list[dict]:
    """
    Parse unstructured elements into structured Q&A pairs from table format.

    The PDF structure:
    - Lines 0-5: Category headers listed
    - Line 6-8: Column headers (#, Question, Answer)
    - Then rows: number, question, answer (but category info may be lost)

    Args:
        elements: List of unstructured elements
        text_content: Full text content
        pdf_path: Path to PDF file for source metadata

    Returns:
        List of Q&A dictionaries
    """
    qa_pairs = []

    # Split text into lines for processing
    lines = text_content.split("\n")
    lines = [line.strip() for line in lines if line.strip()]

    # Known categories from the PDF
    valid_categories = [
        "General & About",
        "Properties & Spaces",
        "Facilities & Amenities",
        "Services & Rules",
        "Location & Surroundings",
    ]

    # Find where questions start (after headers)
    question_start_idx = None
    for i, line in enumerate(lines):
        if line in ["Answer"] or (line == "Question" and i + 1 < len(lines) and lines[i + 1].startswith("1 ")):
            question_start_idx = i + 1
            break

    if question_start_idx is None:
        # Fallback: find first numbered question
        for i, line in enumerate(lines):
            if re.match(r"^1\s+", line):
                question_start_idx = i
                break

    if question_start_idx is None:
        question_start_idx = 0

    logger.info(f"Questions start at line {question_start_idx}")

    # Extract all Q&A pairs
    i = question_start_idx
    current_category = "General & About"  # Default category

    while i < len(lines):
        line = lines[i]

        # Skip header rows and category listings at top
        if line in ["Category", "#", "Question", "Answer"]:
            i += 1
            continue

        # Check if this is a category header (shouldn't appear after questions start, but check anyway)
        for cat in valid_categories:
            if cat == line:  # Exact match for category
                current_category = cat
                logger.debug(f"Found category: {cat} at line {i}")
                i += 1
                continue

        # Look for numbered questions
        question_num = None
        question_text = None
        question_line_idx = i

        # Pattern 1: Number and question on same line: "1 What is..."
        question_match = re.match(r"^(\d+)[\.\)]?\s+(.+)$", line)
        if question_match:
            question_num = int(question_match.group(1))
            question_text = question_match.group(2).strip()
        # Pattern 2: Just number on one line, question on next: "4" then "Is Swiss..."
        elif re.match(r"^(\d+)$", line) and i + 1 < len(lines):
            question_num = int(line)
            next_line = lines[i + 1].strip()
            # Check if next line is a question (not a number, not empty, reasonable length)
            if (
                next_line
                and not re.match(r"^\d+", next_line)
                and len(next_line) > 5
                and (next_line.endswith("?") or len(next_line) > 10)
            ):
                question_text = next_line
                question_line_idx = i + 1
                i += 1  # Skip the question text line since we're using it

        if question_num and question_text:
            # Clean question
            question_text = re.sub(r"^\d+[\.\)]?\s*", "", question_text).strip()

            # Extract answer - look in next lines (start from after question)
            answer_lines = []
            j = question_line_idx + 1
            max_search = min(question_line_idx + 50, len(lines))  # Search up to 50 lines ahead

            while j < max_search:
                next_line = lines[j]

                # Stop if we hit another numbered question (same line or split)
                if re.match(r"^(\d+)[\.\)]?\s+", next_line):
                    # Make sure we have some answer content before stopping
                    if answer_lines:
                        break
                if re.match(r"^(\d+)$", next_line) and j + 1 < len(lines):
                    # Check if next line after number is a question
                    following_line = lines[j + 1].strip()
                    if following_line and len(following_line) > 5 and not re.match(r"^\d+", following_line):
                        # Make sure we have some answer content before stopping
                        if answer_lines:
                            break

                # Stop if we hit a category
                is_category = False
                for cat in valid_categories:
                    if cat == next_line:
                        is_category = True
                        break
                if is_category:
                    break

                # Stop if we hit header words
                if next_line in ["Category", "#", "Question", "Answer"]:
                    j += 1
                    continue

                # Collect answer text - be more lenient
                if len(next_line) > 2:  # Reduced from 3 to 2
                    # Only skip if it's clearly a question (ends with ? and is very short)
                    is_question = next_line.endswith("?") and len(next_line) < 50
                    if not is_question:
                        answer_lines.append(next_line)

                j += 1

            if answer_lines:
                answer = " ".join(answer_lines).strip()
                # Clean answer - be gentler
                answer = re.sub(r"^[\d\s\.\)\-\*]+\s*", "", answer).strip()

                # Reduced minimum answer length
                if len(answer) > 5:
                    qa_pair = {
                        "faq_id": f"faq_{question_num:03d}",
                        "category": current_category,  # Will need to be improved with actual category detection
                        "question": question_text,
                        "answer": answer,
                        "source": str(pdf_path),
                        "question_number": question_num,
                    }
                    qa_pairs.append(qa_pair)

        i += 1

    # Now assign categories based on question number ranges (heuristic)
    # This is a rough estimate - you may need to adjust based on actual PDF
    qa_pairs = assign_categories_by_ranges(qa_pairs, valid_categories)

    # Sort by question number
    qa_pairs.sort(key=lambda x: x.get("question_number", 0))

    logger.info(f"Extracted {len(qa_pairs)} Q&A pairs from {len(lines)} lines")
    return qa_pairs


def assign_categories_by_ranges(qa_pairs: list[dict], valid_categories: list[str]) -> list[dict]:
    """
    Assign categories to Q&A pairs based on question number ranges.

    Category ranges from the PDF:
    - General & About: 1-8
    - Properties & Spaces: 9-30
    - Facilities & Amenities: 31-49
    - Services & Rules: 50-59
    - Location & Surroundings: 60-77
    - Images & Media: 78-79
    - Availability & Dates: 80-81
    - Pricing & Payments: 82-95
    - Booking Cancellation & Refunds: 96-98
    - Check-in & Check-out: 99-102
    - Safety & Security: 103-106
    - Guest Support / Contacts / Ownership: 107-110
    - Food: 111-124
    - Fallback / General / Reviews: 125-132 (assuming 125-127 are also Reviews, and 128-132)
    - Questions 133-153: Assigned to last category (Fallback / General / Reviews)

    Args:
        qa_pairs: List of Q&A dictionaries
        valid_categories: List of valid category names

    Returns:
        Updated Q&A pairs with categories assigned
    """
    if not qa_pairs:
        return qa_pairs

    # Ensure valid_categories has all required categories
    required_categories = [
        "General & About",
        "Properties & Spaces",
        "Facilities & Amenities",
        "Services & Rules",
        "Location & Surroundings",
        "Images & Media",
        "Availability & Dates",
        "Pricing & Payments",
        "Booking Cancellation & Refunds",
        "Check-in & Check-out",
        "Safety & Security",
        "Guest Support / Contacts / Ownership",
        "Food",
        "Fallback / General / Reviews",
    ]

    for qa in qa_pairs:
        q_num = qa.get("question_number", 0)

        # Category ranges from actual PDF structure
        if 1 <= q_num <= 8:
            qa["category"] = required_categories[0]  # General & About
        elif 9 <= q_num <= 30:
            qa["category"] = required_categories[1]  # Properties & Spaces
        elif 31 <= q_num <= 49:
            qa["category"] = required_categories[2]  # Facilities & Amenities
        elif 50 <= q_num <= 59:
            qa["category"] = required_categories[3]  # Services & Rules
        elif 60 <= q_num <= 77:
            qa["category"] = required_categories[4]  # Location & Surroundings
        elif 78 <= q_num <= 79:
            qa["category"] = required_categories[5]  # Images & Media
        elif 80 <= q_num <= 81:
            qa["category"] = required_categories[6]  # Availability & Dates
        elif 82 <= q_num <= 95:
            qa["category"] = required_categories[7]  # Pricing & Payments
        elif 96 <= q_num <= 98:
            qa["category"] = required_categories[8]  # Booking Cancellation & Refunds
        elif 99 <= q_num <= 102:
            qa["category"] = required_categories[9]  # Check-in & Check-out
        elif 103 <= q_num <= 106:
            qa["category"] = required_categories[10]  # Safety & Security
        elif 107 <= q_num <= 110:
            qa["category"] = required_categories[11]  # Guest Support / Contacts / Ownership
        elif 111 <= q_num <= 124:
            qa["category"] = required_categories[12]  # Food
        elif 125 <= q_num <= 132:
            qa["category"] = required_categories[13]  # Fallback / General / Reviews
        else:
            # Questions 133-153+ assigned to last category
            qa["category"] = required_categories[13]  # Fallback / General / Reviews

    logger.info(f"Categories assigned using actual PDF ranges for {len(qa_pairs)} Q&A pairs")
    return qa_pairs


def identify_categories(text: str) -> str | None:
    """
    Identify category from text line.

    Args:
        text: Text line to analyze

    Returns:
        Category name if found, None otherwise
    """
    # Known categories from the PDF (in order they appear)
    valid_categories = [
        "General & About",
        "Properties & Spaces",
        "Facilities & Amenities",
        "Services & Rules",
        "Location & Surroundings",
        "Images & Media",
        "Availability & Dates",
        "Pricing & Payments",
        "Booking Cancellation & Refunds",
        "Check-in & Check-out",
        "Safety & Security",
        "Guest Support / Contacts / Ownership",
        "Food",
        "Fallback / General / Reviews",
    ]

    for category in valid_categories:
        if category in text:
            return category

    return None


def parse_alternative_format(text_content: str, pdf_path: Path) -> list[dict]:
    """
    Alternative parsing method for less structured PDFs.

    Args:
        text_content: Full text content
        pdf_path: Path to PDF file

    Returns:
        List of Q&A dictionaries
    """
    qa_pairs = []
    faq_id = 0
    current_category = "General"

    # Split by common separators
    sections = re.split(r"\n\n+", text_content)

    for section in sections:
        lines = [line.strip() for line in section.split("\n") if line.strip()]

        if len(lines) < 2:
            continue

        # Look for question-answer pattern
        for i, line in enumerate(lines):
            if line.endswith("?") and i + 1 < len(lines):
                question = line
                answer = " ".join(lines[i + 1 : i + 3]).strip()  # Take next 1-2 lines as answer

                if len(answer) > 10:
                    faq_id += 1
                    qa_pair = {
                        "faq_id": f"faq_{faq_id:03d}",
                        "category": current_category,
                        "question": question,
                        "answer": answer,
                        "source": str(pdf_path),
                    }
                    qa_pairs.append(qa_pair)

    return qa_pairs


def format_qa_for_embedding(qa_pair: dict) -> str:
    """
    Format Q&A pair for optimal embeddings.

    Args:
        qa_pair: Dictionary containing category, question, and answer

    Returns:
        Formatted text string for embedding
    """
    category = qa_pair.get("category", "General")
    question = qa_pair.get("question", "").strip()
    answer = qa_pair.get("answer", "").strip()

    # Clean text
    question = re.sub(r"\s+", " ", question)
    answer = re.sub(r"\s+", " ", answer)

    # Format for optimal embeddings: Category + Question + Answer
    formatted_text = f"Category: {category}\n\nQuestion: {question}\n\nAnswer: {answer}"

    return formatted_text


def sanitize_filename(text: str) -> str:
    """
    Sanitize text for use in filename.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized filename-safe string
    """
    # Remove special characters, keep alphanumeric, spaces, hyphens, underscores
    sanitized = re.sub(r"[^\w\s-]", "", text)
    # Replace spaces with underscores
    sanitized = re.sub(r"\s+", "_", sanitized)
    # Remove multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    # Limit length
    sanitized = sanitized[:50]
    return sanitized.strip("_")


def get_resource_links() -> dict:
    """
    Get resource links mapping for FAQ files.
    
    Returns:
        Dictionary mapping FAQ question numbers or keywords to lists of links
    """
    return {
        # General & About - Website, Social Media, Contact
        "website": {"faq_nums": [1], "links": [
            ("Website", "https://swisscottagesbhurban.com/"),
            ("Instagram", "https://www.instagram.com/swiss_cottages_bhurban/"),
            ("Facebook", "https://www.facebook.com/profile.php?id=100095024470541"),
            ("Contact Us", "https://swisscottagesbhurban.com/contact-us/"),
        ]},
        # Booking & Availability
        "booking": {"faq_nums": [80, 81, 96, 97, 98], "links": [
            ("Airbnb Cottage 9", "https://www.airbnb.com/rooms/651168099240245080?source_impression_id=p3_1768373938_P3UsgNEH2WEbHfrW"),
            ("Airbnb Cottage 11", "https://www.airbnb.com/rooms/886682083069412842?source_impression_id=p3_1768373959_P3-TaoEexUttIGk0"),
            ("Request Custom Quote", "https://swisscottagesbhurban.com/contact-us/"),
        ]},
        # Reviews
        "reviews": {"faq_nums": [147, 148, 149, 150, 151, 152, 153], "links": [
            ("Read Airbnb Reviews - Cottage 9", "https://www.airbnb.com/rooms/651168099240245080?source_impression_id=p3_1768373938_P3UsgNEH2WEbHfrW"),
            ("Read Airbnb Reviews - Cottage 11", "https://www.airbnb.com/rooms/886682083069412842?source_impression_id=p3_1768373959_P3-TaoEexUttIGk0"),
        ]},
        # Images & Media
        "images": {"faq_nums": [78, 79], "links": [
            ("View Photo Gallery", "https://swisscottagesbhurban.com/"),
            ("Instagram", "https://www.instagram.com/swiss_cottages_bhurban/"),
            ("Facebook", "https://www.facebook.com/profile.php?id=100095024470541"),
        ]},
        # Location & Maps
        "location": {"faq_nums": [60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77], "links": [
            ("View on Google Maps", "https://goo.gl/maps/PQbSR9DsuxwjxUoU6?g_st=aw"),
            ("Azad Kashmir view point near PC Bhurban", "https://maps.app.goo.gl/vcvDmZ2KTg2An3WK6?g_st=aw"),
            ("Hiking trail near Hotel One Bhurban", "https://maps.app.goo.gl/ELzmaMnqv8NjSTTg9?g_st=aw"),
            ("Walking trail near Governor House Bhurban", "https://maps.app.goo.gl/9zLdWCcYYEEb77Fh7?g_st=aw"),
            ("Chinar golf club", "https://maps.app.goo.gl/DEoq4X5HTXsQ5ZDTA?g_st=aw"),
            ("PC Bhurban", "https://maps.app.goo.gl/R3qsW38PYZPY5YMH8?g_st=aw"),
        ]},
        # Guest Support / Contacts
        "support": {"faq_nums": [107, 108, 109, 110], "links": [
            ("Contact Us", "https://swisscottagesbhurban.com/contact-us/"),
            ("Website", "https://swisscottagesbhurban.com/"),
        ]},
    }


def add_links_to_faq_file(file_path: Path, links: list[tuple[str, str]]) -> None:
    """
    Add resource links to an FAQ file.
    
    Args:
        file_path: Path to the FAQ markdown file
        links: List of (name, url) tuples
    """
    if not file_path.exists():
        return
    
    content = file_path.read_text(encoding="utf-8")
    
    # Find the Answer section and add links
    if "Answer:" in content:
        # Add links section before the end of the file
        links_section = "\n\n## Useful Links\n\n"
        for name, url in links:
            if url and url != "-":
                links_section += f"- [{name}]({url})\n"
        
        # Insert before the end of the content
        content = content.rstrip() + links_section
        
        file_path.write_text(content, encoding="utf-8")
        logger.debug(f"Added {len(links)} links to {file_path.name}")


def generate_markdown_files(qa_pairs: list[dict], output_dir: Path) -> None:
    """
    Generate Markdown files with YAML frontmatter for each Q&A pair.

    Args:
        qa_pairs: List of Q&A dictionaries
        output_dir: Directory to save Markdown files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating {len(qa_pairs)} Markdown files in {output_dir}")

    # Get resource links mapping
    resource_links = get_resource_links()
    
    # Create a mapping of FAQ numbers to links
    faq_links_map = {}
    for resource_type, resource_data in resource_links.items():
        for faq_num in resource_data["faq_nums"]:
            if faq_num not in faq_links_map:
                faq_links_map[faq_num] = []
            faq_links_map[faq_num].extend(resource_data["links"])

    for qa_pair in qa_pairs:
        # Format content for embedding
        formatted_content = format_qa_for_embedding(qa_pair)

        # Create frontmatter
        question_escaped = qa_pair.get('question', '').replace('"', '\\"')
        frontmatter = f"""---
category: "{qa_pair.get('category', 'General')}"
faq_id: "{qa_pair.get('faq_id', 'unknown')}"
source: "{qa_pair.get('source', 'unknown')}"
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

        # Add links if this FAQ has associated links
        question_num = qa_pair.get("question_number")
        if question_num and question_num in faq_links_map:
            add_links_to_faq_file(file_path, faq_links_map[question_num])

        logger.debug(f"Created: {filename}")

    logger.info(f"Successfully generated {len(qa_pairs)} Markdown files")


def build_vector_index(
    docs_path: Path, vector_store_path: str, chunk_size: int = 512, chunk_overlap: int = 25
) -> None:
    """
    Build vector index from Markdown files.

    Args:
        docs_path: Path to directory containing Markdown files
        vector_store_path: Path to vector store
        chunk_size: Chunk size (default: 512)
        chunk_overlap: Chunk overlap (default: 25)
    """
    from bot.memory.embedder import Embedder
    from bot.memory.vector_database.chroma import Chroma
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
    vector_database = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
    vector_database.from_chunks(chunks)
    logger.info("Memory Index has been created successfully!")


def get_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Extract FAQ from PDF and build vector index")

    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="Path to PDF file",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="docs/faq",
        help="Output directory for Markdown files (default: docs/faq)",
    )

    parser.add_argument(
        "--vector-store",
        type=str,
        default="vector_store/faq_index",
        help="Path to vector store (default: vector_store/faq_index)",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Chunk size (default: 512, but Q&A pairs won't be split)",
    )

    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=25,
        help="Chunk overlap (default: 25)",
    )

    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip building vector index (only generate Markdown files)",
    )

    return parser.parse_args()


def main(parameters) -> None:
    """Main execution function."""
    root_folder = Path(__file__).resolve().parent.parent
    pdf_path = Path(parameters.pdf)
    if not pdf_path.is_absolute():
        pdf_path = root_folder / pdf_path

    output_dir = Path(parameters.output)
    if not output_dir.is_absolute():
        output_dir = root_folder / output_dir

    vector_store_path = parameters.vector_store
    if not Path(vector_store_path).is_absolute():
        vector_store_path = str(root_folder / vector_store_path)

    # Step 1: Extract Q&A pairs from PDF
    qa_pairs = extract_faq_from_pdf(pdf_path)

    if not qa_pairs:
        logger.error("No Q&A pairs extracted from PDF. Please check the PDF format.")
        sys.exit(1)

    # Step 2: Generate Markdown files
    generate_markdown_files(qa_pairs, output_dir)

    # Step 3: Build vector index (optional)
    if not parameters.skip_index:
        build_vector_index(output_dir, vector_store_path, parameters.chunk_size, parameters.chunk_overlap)
    else:
        logger.info("Skipping vector index build (--skip-index flag set)")


if __name__ == "__main__":
    try:
        args = get_args()
        main(args)
    except Exception as error:
        logger.error(f"An error occurred: {str(error)}", exc_info=True, stack_info=True)
        sys.exit(1)
