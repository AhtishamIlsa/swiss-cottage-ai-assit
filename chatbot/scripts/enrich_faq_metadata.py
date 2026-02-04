"""FAQ metadata enricher - adds intent and slot metadata to FAQ frontmatter."""

import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent.parent
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

# Add project root to path for Excel extractor functions
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from helpers.log import get_logger

logger = get_logger(__name__)

# Try to import pandas for Excel support
try:
    import pandas as pd
    EXCEL_SUPPORT = True
except ImportError:
    EXCEL_SUPPORT = False
    logger.warning("pandas not available - Excel support disabled. Install with: pip install pandas openpyxl")


# Category to intent mapping
CATEGORY_TO_INTENT = {
    "Booking": "booking",
    "Pricing & Payments": "pricing",
    "Pricing_Payments": "pricing",
    "Availability & Dates": "availability",
    "Availability_Dates": "availability",
    "Properties & Spaces": "rooms",
    "Properties_Spaces": "rooms",
    "Facilities & Amenities": "facilities",
    "Facilities_Amenities": "facilities",
    "Location & Surroundings": "location",
    "Location_Surroundings": "location",
    "Safety & Security": "safety",
    "Safety_Security": "safety",
    "Guest Support": "booking",
    "Guest_Support": "booking",
    "Check-in & Check-out": "booking",
    "Check_in_Check_out": "booking",
    "Cancellation & Refunds": "booking",
    "Cancellation_Refunds": "booking",
    "Images & Media": "rooms",
    "Images_Media": "rooms",
    "Weather": "faq_question",
    "Food": "facilities",
    "Fallback & General": "faq_question",
    "Fallback_General": "faq_question",
    "General & About": "faq_question",
    "General_About": "faq_question",
    "Reviews": "faq_question",
    "Services & Rules": "faq_question",
    "Services_Rules": "faq_question",
    "Weather": "faq_question",
}


# Intent to required slots mapping
INTENT_TO_SLOTS = {
    "pricing": {
        "required": ["guests", "dates", "room_type"],
        "optional": ["season"],
    },
    "booking": {
        "required": ["guests", "dates", "room_type", "family"],
        "optional": ["season"],
    },
    "availability": {
        "required": ["dates"],
        "optional": ["guests", "room_type"],
    },
    "rooms": {
        "required": [],
        "optional": ["guests", "room_type"],
    },
    "facilities": {
        "required": [],
        "optional": ["room_type"],
    },
    "location": {
        "required": [],
        "optional": [],
    },
    "safety": {
        "required": [],
        "optional": [],
    },
    "faq_question": {
        "required": [],
        "optional": [],
    },
}


# Slot extraction hints
SLOT_HINTS = {
    "guests": "number of guests or people",
    "room_type": "cottage 7, 9, or 11",
    "dates": "check-in and check-out dates",
    "family": "whether booking is for family or friends",
    "season": "weekday, weekend, peak, or off-peak",
}


def parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.
    
    Args:
        content: Markdown content with frontmatter
        
    Returns:
        Tuple of (frontmatter dict, content without frontmatter)
    """
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(frontmatter_pattern, content, re.DOTALL)
    
    if match:
        frontmatter_text = match.group(1)
        content_text = match.group(2)
        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
            return frontmatter, content_text
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse frontmatter: {e}")
            return {}, content
    else:
        return {}, content


def determine_intent_from_faq(frontmatter: Dict[str, Any], content: str) -> str:
    """
    Determine intent from FAQ category and content.
    
    Args:
        frontmatter: FAQ frontmatter
        content: FAQ content
        
    Returns:
        Intent string
    """
    category = frontmatter.get("category", "")
    question = frontmatter.get("question", "")
    
    # Try category mapping first
    if category in CATEGORY_TO_INTENT:
        return CATEGORY_TO_INTENT[category]
    
    # Try normalized category (with underscores)
    category_normalized = category.replace(" & ", "_").replace(" ", "_")
    if category_normalized in CATEGORY_TO_INTENT:
        return CATEGORY_TO_INTENT[category_normalized]
    
    # Analyze question text first (more reliable than answer text)
    question_lower = question.lower() if question else ""
    content_lower = content.lower()
    combined_text = (question_lower + " " + content_lower).lower()
    
    # Check for specific question patterns first (more specific to less specific)
    # IMPORTANT: Order matters - more specific patterns first
    
    # Images/Photos/Media questions - should be "rooms" intent (about viewing properties)
    # This MUST come BEFORE location check to avoid false positives
    photo_media_keywords = ["photo", "picture", "image", "video", "gallery", "visual", "pictures", "images", "videos"]
    if any(word in question_lower for word in photo_media_keywords):
        return "rooms"  # Images are about showing the cottages/properties
    
    # Also check for "where can i see" or "where to see" with photo/media context
    if ("where" in question_lower and ("see" in question_lower or "view" in question_lower)):
        if any(word in question_lower for word in photo_media_keywords):
            return "rooms"  # "Where can I see photos" is about viewing properties
    
    # Pricing questions
    if any(word in question_lower for word in ["price", "pricing", "cost", "rate", "rates", "how much", "payment"]):
        return "pricing"
    if any(word in combined_text for word in ["pkr", "per night", "weekday", "weekend", "peak season"]):
        return "pricing"
    
    # Booking questions
    if any(word in question_lower for word in ["book", "booking", "reserve", "reservation", "how to book"]):
        return "booking"
    
    # Availability questions - be more specific to avoid false positives
    # Only match if it's clearly about booking availability, not general "available" usage
    availability_patterns = [
        "is it available", "is available", "available for", "availability", 
        "when available", "available dates", "check availability", "available to book",
        "can i book", "can we book", "vacant", "vacancy"
    ]
    if any(phrase in question_lower for phrase in availability_patterns):
        # Exclude if it's about photos/media, facilities, or other things being available
        if not any(word in question_lower for word in ["photo", "picture", "image", "video", "gallery", "facility", "amenity", "feature", "service", "what is available"]):
            return "availability"
    
    # Location questions - check if "where" is about location, not photos
    if any(word in question_lower for word in ["where is", "location", "address", "nearby", "how to reach"]):
        # But exclude if it's about where to see photos
        if not any(word in question_lower for word in ["photo", "picture", "image", "video", "gallery", "see", "view"]):
            return "location"
    
    # Safety questions
    if any(word in question_lower for word in ["safety", "security", "safe", "emergency", "secure"]):
        return "safety"
    
    # Facilities questions
    if any(word in question_lower for word in ["facility", "amenity", "amenities", "facilities", "what is available", "what do you have"]):
        return "facilities"
    
    # Reviews questions
    if any(word in question_lower for word in ["review", "reviews", "rating", "feedback", "testimonial"]):
        return "faq_question"
    
    # Services/Support questions
    if any(word in question_lower for word in ["caretaker", "service", "support", "help", "assistance", "staff"]):
        return "faq_question"
    
    # Rooms/Properties questions
    if any(word in question_lower for word in ["cottage", "room", "bedroom", "property", "accommodation", "what is", "tell me about"]):
        return "rooms"
    
    # Fallback: analyze content keywords (less reliable, but as last resort)
    if any(word in content_lower for word in ["price", "pricing", "cost", "rate", "payment", "pkr"]):
        return "pricing"
    elif any(word in content_lower for word in ["book", "booking", "reserve", "reservation"]):
        return "booking"
    elif any(word in content_lower for word in ["cottage", "room", "bedroom", "property"]):
        return "rooms"
    elif any(word in content_lower for word in ["facility", "amenity", "feature"]):
        return "facilities"
    elif any(word in content_lower for word in ["location", "address", "nearby"]):
        return "location"
    elif any(word in content_lower for word in ["safety", "security", "safe", "emergency"]):
        return "safety"
    
    # Default
    return "faq_question"


def get_slots_for_intent(intent: str) -> Dict[str, List[str]]:
    """
    Get required and optional slots for an intent.
    
    Args:
        intent: Intent string
        
    Returns:
        Dictionary with 'required' and 'optional' slot lists
    """
    return INTENT_TO_SLOTS.get(intent, {"required": [], "optional": []})


def enrich_faq_file(faq_path: Path) -> bool:
    """
    Enrich a single FAQ file with intent and slot metadata.
    
    Args:
        faq_path: Path to FAQ file
        
    Returns:
        True if file was modified, False otherwise
    """
    try:
        content = faq_path.read_text(encoding="utf-8")
        frontmatter, content_text = parse_frontmatter(content)
        
        # Determine intent
        intent = determine_intent_from_faq(frontmatter, content_text)
        
        # Get slots for intent
        slots = get_slots_for_intent(intent)
        
        # Check if already enriched with correct intent
        existing_intent = frontmatter.get("intent")
        if existing_intent and existing_intent == intent and "required_slots" in frontmatter:
            # Already enriched with correct intent, skip
            logger.debug(f"Skipping {faq_path.name} - already enriched with correct intent {intent}")
            return False
        
        # If intent changed or is missing, re-enrich
        if existing_intent and existing_intent != intent:
            logger.info(f"Re-enriching {faq_path.name}: intent changed from {existing_intent} to {intent}")
        
        # Update frontmatter
        frontmatter["intent"] = intent
        frontmatter["required_slots"] = slots["required"]
        frontmatter["optional_slots"] = slots["optional"]
        
        # Add slot extraction hints
        hints_lines = []
        for slot in slots["required"] + slots["optional"]:
            if slot in SLOT_HINTS:
                hints_lines.append(f"  {slot}: {SLOT_HINTS[slot]}")
        
        if hints_lines:
            frontmatter["slot_extraction_hints"] = "\n".join(hints_lines)
        
        # Reconstruct file
        frontmatter_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        new_content = f"---\n{frontmatter_yaml}---\n\n{content_text}"
        
        # Write back
        faq_path.write_text(new_content, encoding="utf-8")
        logger.info(f"Enriched {faq_path.name} with intent={intent}, slots={slots}")
        return True
        
    except Exception as e:
        logger.error(f"Error enriching {faq_path}: {e}")
        return False


def sanitize_filename(text: str) -> str:
    """Sanitize text for use in filenames."""
    if not text:
        return "unknown"
    # Replace spaces and special chars with underscores
    text = re.sub(r'[^\w\s-]', '', str(text))
    text = re.sub(r'[-\s]+', '_', text)
    return text.strip('_').lower()


def format_qa_for_embedding(qa_pair: dict) -> str:
    """Format Q&A pair for embedding with comprehensive context."""
    category = qa_pair.get('category', 'General')
    question = qa_pair.get('question', '')
    answer = qa_pair.get('answer', '')
    account_resource = qa_pair.get('account_resource', '')
    link = qa_pair.get('link', '')
    
    # Build comprehensive formatted content
    formatted = f"Category: {category}\n\n"
    formatted += f"Question: {question}\n\n"
    formatted += f"Answer: {answer}\n"
    
    # Add account/resource information if available
    if account_resource and str(account_resource).strip() and str(account_resource).lower() != 'nan':
        formatted += f"\nAccount/Resource: {account_resource}\n"
    
    # Add link if available
    if link and str(link).strip() and str(link).lower() != 'nan':
        # Check if link is already a full URL
        link_str = str(link).strip()
        if not link_str.startswith('http'):
            # Assume it's a relative path or needs https://
            if link_str.startswith('www.'):
                link_str = f"https://{link_str}"
            elif not link_str.startswith('/'):
                link_str = f"https://{link_str}"
        
        formatted += f"\nRelated Link: {link_str}\n"
    
    return formatted


def extract_faq_from_excel(excel_path: Path) -> List[Dict[str, Any]]:
    """
    Extract Q&A pairs from Excel file.
    
    Expected Excel structure:
    - Columns: Category, Question, Answer, Account/Resource, Link
    - Row 1: Headers
    - Row 2+: Data rows
    
    Args:
        excel_path: Path to Excel file
        
    Returns:
        List of dictionaries containing Q&A pairs with metadata
    """
    if not EXCEL_SUPPORT:
        raise ImportError("pandas is required for Excel support. Install with: pip install pandas openpyxl")
    
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
    
    logger.info(f"Extracting FAQ data from Excel: {excel_path}")
    
    try:
        # Try reading with header=None first to see all rows
        df_raw = pd.read_excel(excel_path, engine='openpyxl', header=None)
        logger.info(f"Loaded Excel file with {len(df_raw)} rows and {len(df_raw.columns)} columns")
        
        # Find header row by looking for keywords
        header_row_idx = None
        for idx, row in df_raw.iterrows():
            row_str = ' '.join(str(cell).lower() for cell in row.values if pd.notna(cell))
            # Check if this row contains header keywords
            if any(keyword in row_str for keyword in ['category', 'question', 'answer']):
                header_row_idx = idx
                logger.info(f"Found potential header row at index {idx}: {list(row.values)}")
                break
        
        if header_row_idx is None:
            # Default to row 0
            header_row_idx = 0
            logger.warning("Could not find header row automatically. Using row 0 as header.")
        
        # Read with proper header row
        df = pd.read_excel(excel_path, engine='openpyxl', header=header_row_idx)
        logger.info(f"Reading with header row {header_row_idx}")
        logger.info(f"Columns after header detection: {list(df.columns)}")
        
    except Exception as e:
        logger.error(f"Failed to read Excel file: {e}")
        raise
    
    # Normalize column names (handle variations)
    column_mapping = {}
    for col in df.columns:
        col_lower = str(col).lower().strip()
        # Skip unnamed columns
        if 'unnamed' in col_lower:
            continue
        if 'category' in col_lower:
            column_mapping['category'] = col
        elif 'question' in col_lower:
            column_mapping['question'] = col
        elif 'answer' in col_lower:
            column_mapping['answer'] = col
        elif 'account' in col_lower or 'resource' in col_lower:
            column_mapping['account_resource'] = col
        elif 'link' in col_lower or 'url' in col_lower:
            column_mapping['link'] = col
    
    # Check required columns
    required = ['category', 'question', 'answer']
    missing = [col for col in required if col not in column_mapping]
    if missing:
        # Try common positions (Category=0, Question=2, Answer=3, etc.)
        if len(df.columns) >= 4:
            logger.info("Attempting to use column positions (assuming standard format)...")
            if 'category' not in column_mapping and len(df.columns) > 0:
                test_col = df.columns[0]
                if df[test_col].notna().any():
                    column_mapping['category'] = test_col
                    logger.info(f"Using column 0 ({test_col}) as Category")
            
            if 'question' not in column_mapping and len(df.columns) > 2:
                test_col = df.columns[2]
                if df[test_col].notna().any():
                    column_mapping['question'] = test_col
                    logger.info(f"Using column 2 ({test_col}) as Question")
            
            if 'answer' not in column_mapping and len(df.columns) > 3:
                test_col = df.columns[3]
                if df[test_col].notna().any():
                    column_mapping['answer'] = test_col
                    logger.info(f"Using column 3 ({test_col}) as Answer")
        
        # Re-check after position-based detection
        missing = [col for col in required if col not in column_mapping]
        if missing:
            raise ValueError(
                f"Missing required columns: {missing}.\n"
                f"Found columns: {list(df.columns)}\n"
                f"Please ensure your Excel file has columns named: Category, Question, Answer"
            )
    
    logger.info(f"Column mapping: {column_mapping}")
    
    qa_pairs = []
    
    # Process each row
    for idx, row in df.iterrows():
        # Skip empty rows
        question = str(row[column_mapping['question']]).strip() if column_mapping.get('question') else ''
        answer = str(row[column_mapping['answer']]).strip() if column_mapping.get('answer') else ''
        
        if not question or question.lower() in ['nan', 'none', '']:
            continue
        if not answer or answer.lower() in ['nan', 'none', '']:
            continue
        
        # Extract data
        category = str(row[column_mapping['category']]).strip() if column_mapping.get('category') else 'General'
        account_resource = str(row[column_mapping.get('account_resource', '')]).strip() if column_mapping.get('account_resource') else ''
        link = str(row[column_mapping.get('link', '')]).strip() if column_mapping.get('link') else ''
        
        # Clean up values
        if category.lower() in ['nan', 'none', '']:
            category = 'General'
        if account_resource.lower() in ['nan', 'none', '']:
            account_resource = ''
        if link.lower() in ['nan', 'none', '']:
            link = ''
        
        # Generate FAQ ID (use row number + 1 for 1-based indexing)
        faq_id = f"faq_{idx + 1:03d}"
        
        qa_pair = {
            'faq_id': faq_id,
            'category': category,
            'question': question,
            'answer': answer,
            'account_resource': account_resource,
            'link': link,
            'source': 'Excel FAQ Export',
            'row_number': idx + 1
        }
        
        qa_pairs.append(qa_pair)
    
    logger.info(f"Extracted {len(qa_pairs)} Q&A pairs from Excel")
    return qa_pairs


def generate_markdown_files(qa_pairs: List[Dict[str, Any]], output_dir: Path) -> None:
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
        
        # Create frontmatter
        question_escaped = qa_pair.get('question', '').replace('"', '\\"')
        category_escaped = qa_pair.get('category', 'General').replace('"', '\\"')
        
        frontmatter = f"""---
category: "{category_escaped}"
faq_id: "{qa_pair.get('faq_id', 'unknown')}"
source: "{qa_pair.get('source', 'Excel FAQ Export')}"
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


def enrich_all_faqs(faq_dir: Path) -> Dict[str, int]:
    """
    Enrich all FAQ files in a directory.
    
    Args:
        faq_dir: Directory containing FAQ files
        
    Returns:
        Dictionary with enrichment statistics
    """
    stats = {"total": 0, "enriched": 0, "skipped": 0, "errors": 0}
    
    if not faq_dir.exists():
        logger.error(f"FAQ directory does not exist: {faq_dir}")
        return stats
    
    faq_files = list(faq_dir.glob("*.md"))
    stats["total"] = len(faq_files)
    
    logger.info(f"Found {stats['total']} FAQ files to process")
    
    for faq_file in faq_files:
        try:
            if enrich_faq_file(faq_file):
                stats["enriched"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            logger.error(f"Error processing {faq_file}: {e}")
            stats["errors"] += 1
    
    return stats


def main():
    """Main function to enrich FAQ files."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enrich FAQ files with intent and slot metadata")
    parser.add_argument(
        "--faq-dir",
        type=str,
        default=None,
        help="Directory containing FAQ files (default: docs/faq)",
    )
    parser.add_argument(
        "--excel",
        type=str,
        default=None,
        help="Path to Excel file to extract and enrich FAQs from",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="docs/faq",
        help="Output directory for generated FAQ files (default: docs/faq)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - don't modify files, just show what would be done",
    )
    
    args = parser.parse_args()
    
    # Resolve paths relative to project root
    project_root = Path(__file__).parent.parent.parent
    
    # If Excel file is provided, extract and generate markdown files first
    if args.excel:
        if not EXCEL_SUPPORT:
            logger.error("Excel support requires pandas. Install with: pip install pandas openpyxl")
            sys.exit(1)
        
        excel_path = Path(args.excel)
        if not excel_path.is_absolute():
            excel_path = project_root / excel_path
        
        if not excel_path.exists():
            logger.error(f"Excel file not found: {excel_path}")
            sys.exit(1)
        
        # Resolve output directory
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = project_root / output_dir
        
        if args.dry_run:
            logger.info("DRY RUN MODE - No files will be modified")
            qa_pairs = extract_faq_from_excel(excel_path)
            logger.info(f"Would extract {len(qa_pairs)} FAQs from Excel and generate markdown files")
            logger.info(f"Would enrich them with intent and slot metadata")
            return
        
        # Extract from Excel
        logger.info(f"Extracting FAQs from Excel: {excel_path}")
        qa_pairs = extract_faq_from_excel(excel_path)
        
        # Generate markdown files
        logger.info(f"Generating markdown files in: {output_dir}")
        generate_markdown_files(qa_pairs, output_dir)
        
        # Now enrich the generated files
        faq_dir = output_dir
    else:
        # Use provided FAQ directory or default
        faq_dir_str = args.faq_dir or args.output_dir
        if Path(faq_dir_str).is_absolute():
            faq_dir = Path(faq_dir_str)
        else:
            faq_dir = project_root / faq_dir_str
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No files will be modified")
        # Just analyze, don't modify
        faq_files = list(faq_dir.glob("*.md"))
        logger.info(f"Would process {len(faq_files)} FAQ files")
        return
    
    # Enrich all FAQs
    stats = enrich_all_faqs(faq_dir)
    
    logger.info(f"\nEnrichment complete:")
    logger.info(f"  Total files: {stats['total']}")
    logger.info(f"  Enriched: {stats['enriched']}")
    logger.info(f"  Skipped (already enriched): {stats['skipped']}")
    logger.info(f"  Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
