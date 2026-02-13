"""Export FAQs from Excel to JSON format for simplified vector store."""

import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent.parent
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from helpers.log import get_logger

logger = get_logger(__name__)

# Import Excel extraction function
try:
    from chatbot.scripts.enrich_faq_metadata import extract_faq_from_excel
    EXCEL_EXTRACTION_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import extract_faq_from_excel: {e}")
    EXCEL_EXTRACTION_AVAILABLE = False

# Import resource links function
try:
    from chatbot.pdf_faq_extractor import get_resource_links
    RESOURCE_LINKS_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import get_resource_links: {e}")
    RESOURCE_LINKS_AVAILABLE = False


def extract_links_from_markdown(markdown_path: Path) -> List[Dict[str, str]]:
    """
    Extract links from markdown file's "## Useful Links" section.
    
    Args:
        markdown_path: Path to markdown file
        
    Returns:
        List of link dictionaries with 'name' and 'url' keys
    """
    if not markdown_path.exists():
        return []
    
    try:
        content = markdown_path.read_text(encoding="utf-8")
        
        # Find "## Useful Links" section
        links_section_match = re.search(r'##\s+Useful\s+Links\s*\n(.*?)(?=\n##|\Z)', content, re.IGNORECASE | re.DOTALL)
        if not links_section_match:
            return []
        
        links_text = links_section_match.group(1)
        
        # Extract markdown links: [name](url)
        link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
        matches = re.findall(link_pattern, links_text)
        
        links = []
        seen_urls = set()
        for name, url in matches:
            url = url.strip()
            if url and url not in seen_urls:
                links.append({"name": name.strip(), "url": url})
                seen_urls.add(url)
        
        return links
    except Exception as e:
        logger.warning(f"Failed to extract links from {markdown_path}: {e}")
        return []


def get_faq_number_from_id(faq_id: str) -> Optional[int]:
    """
    Extract FAQ number from FAQ ID (e.g., "faq_001" -> 1).
    
    Args:
        faq_id: FAQ ID string
        
    Returns:
        FAQ number as integer, or None if not found
    """
    match = re.search(r'faq_(\d+)', faq_id, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def merge_links(
    resource_links: List[Dict[str, str]],
    markdown_links: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """
    Merge links from multiple sources, deduplicating by URL.
    
    Args:
        resource_links: Links from resource_links mapping
        markdown_links: Links from markdown files
        
    Returns:
        Merged list of unique links (by URL)
    """
    seen_urls = {}
    all_links = resource_links + markdown_links
    
    for link in all_links:
        url = link.get("url", "").strip()
        name = link.get("name", "").strip()
        
        if url and url not in seen_urls:
            seen_urls[url] = {"name": name, "url": url}
    
    return list(seen_urls.values())


def calculate_word_count(text: str) -> int:
    """Calculate word count for a text string."""
    if not text:
        return 0
    return len(text.split())


def export_faqs_to_json(
    excel_path: Path,
    output_path: Path,
    markdown_dir: Optional[Path] = None
) -> None:
    """
    Export FAQs from Excel to JSON format.
    
    Args:
        excel_path: Path to Excel file
        output_path: Path to output JSON file
        markdown_dir: Optional directory containing markdown files for link extraction
    """
    if not EXCEL_EXTRACTION_AVAILABLE:
        raise ImportError("Excel extraction not available. Check imports.")
    
    logger.info(f"Exporting FAQs from Excel: {excel_path}")
    
    # Extract FAQs from Excel (skip intent/slots extraction)
    qa_pairs = extract_faq_from_excel(excel_path)
    logger.info(f"Extracted {len(qa_pairs)} FAQs from Excel")
    
    # Get resource links mapping
    resource_links_map = {}
    if RESOURCE_LINKS_AVAILABLE:
        resource_links_data = get_resource_links()
        # Create mapping from FAQ numbers to links
        for resource_type, resource_data in resource_links_data.items():
            for faq_num in resource_data.get("faq_nums", []):
                if faq_num not in resource_links_map:
                    resource_links_map[faq_num] = []
                # Convert tuple links to dict format
                for name, url in resource_data.get("links", []):
                    resource_links_map[faq_num].append({"name": name, "url": url})
        logger.info(f"Loaded resource links mapping for {len(resource_links_map)} FAQ numbers")
    
    # Process each FAQ
    faqs = []
    for qa_pair in qa_pairs:
        faq_id = qa_pair.get("faq_id", "")
        question = qa_pair.get("question", "")
        answer = qa_pair.get("answer", "")
        category = qa_pair.get("category", "General")
        
        # Get FAQ number for link lookup
        faq_num = get_faq_number_from_id(faq_id)
        
        # Collect links from multiple sources
        resource_links = []
        if faq_num and faq_num in resource_links_map:
            resource_links = resource_links_map[faq_num]
        
        markdown_links = []
        if markdown_dir and markdown_dir.exists():
            # Try to find corresponding markdown file
            category_safe = re.sub(r'[^\w\s-]', '', category).strip().replace(' ', '_').lower()
            markdown_file = markdown_dir / f"{category_safe}_{faq_id}.md"
            if markdown_file.exists():
                markdown_links = extract_links_from_markdown(markdown_file)
        
        # Merge all links
        all_links = merge_links(resource_links, markdown_links)
        
        # Calculate word count
        full_text = f"{question} {answer}"
        word_count = calculate_word_count(full_text)
        should_split = word_count > 1000
        
        # Build FAQ entry (exclude intent, slots, link, account_resource)
        faq_entry = {
            "id": faq_id,
            "category": category,
            "question": question,
            "answer": answer,
            "links": all_links,
            "word_count": word_count,
            "should_split": should_split,
            "tags": [],
            "priority": 1
        }
        
        faqs.append(faq_entry)
    
    # Create output structure
    output_data = {
        "faqs": faqs
    }
    
    # Write to JSON file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"✅ Exported {len(faqs)} FAQs to {output_path}")
    logger.info(f"   Total links: {sum(len(faq['links']) for faq in faqs)}")
    logger.info(f"   FAQs to split (>1000 words): {sum(1 for faq in faqs if faq['should_split'])}")


def main():
    """Main function to export FAQs to JSON."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Export FAQs from Excel to JSON")
    parser.add_argument(
        "--excel",
        type=str,
        default="Swiss Cottages FAQS.xlsx",
        help="Path to Excel file (default: Swiss Cottages FAQS.xlsx)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docs/faqs.json",
        help="Output JSON file path (default: docs/faqs.json)"
    )
    parser.add_argument(
        "--markdown-dir",
        type=str,
        default="docs/faq",
        help="Directory containing markdown files for link extraction (default: docs/faq)"
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    project_root = Path(__file__).parent.parent.parent
    
    excel_path = Path(args.excel)
    if not excel_path.is_absolute():
        excel_path = project_root / excel_path
    
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = project_root / output_path
    
    markdown_dir = Path(args.markdown_dir)
    if not markdown_dir.is_absolute():
        markdown_dir = project_root / markdown_dir
    
    if not excel_path.exists():
        logger.error(f"Excel file not found: {excel_path}")
        sys.exit(1)
    
    # Export to JSON
    export_faqs_to_json(excel_path, output_path, markdown_dir)
    
    logger.info("✅ Export complete!")


if __name__ == "__main__":
    main()
