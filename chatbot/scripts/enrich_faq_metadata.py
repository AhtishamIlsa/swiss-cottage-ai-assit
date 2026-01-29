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

from helpers.log import get_logger

logger = get_logger(__name__)


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
        default="docs/faq",
        help="Directory containing FAQ files (default: docs/faq)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - don't modify files, just show what would be done",
    )
    
    args = parser.parse_args()
    
    # Resolve FAQ directory
    if Path(args.faq_dir).is_absolute():
        faq_dir = Path(args.faq_dir)
    else:
        # Relative to project root
        project_root = Path(__file__).parent.parent.parent
        faq_dir = project_root / args.faq_dir
    
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
