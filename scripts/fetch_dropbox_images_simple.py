#!/usr/bin/env python3
"""
Simplified script to get image URLs from Dropbox shared folders.

This script provides a semi-automated approach:
1. Lists all image files in shared folders using Dropbox API
2. Provides instructions to get individual file links
3. Or attempts to construct URLs (may require manual verification)

Usage:
    python scripts/fetch_dropbox_images_simple.py
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import requests
except ImportError:
    print("❌ Error: 'requests' library is required.")
    print("   Install it with: pip install requests")
    sys.exit(1)


def load_token_from_env() -> Optional[str]:
    """Load Dropbox access token from .env file."""
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DROPBOX_ACCESS_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def list_files_in_shared_folder(access_token: str, shared_link: str) -> List[Dict]:
    """List all files in a shared folder."""
    url = "https://api.dropboxapi.com/2/sharing/list_shared_link_files"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Use the full URL with query params for folder links
    data = {"url": shared_link}
    all_files = []
    has_more = True
    
    while has_more:
        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if "entries" in result:
                all_files.extend(result["entries"])
            
            has_more = result.get("has_more", False)
            if has_more and "cursor" in result:
                data["cursor"] = result["cursor"]
            else:
                has_more = False
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Try with the full URL including query params
                if "?" not in shared_link:
                    # If the shared_link doesn't have query params, try adding them back
                    print(f"   ⚠️  API returned 404, the folder link might need to be in a different format")
                    print(f"   💡 Try opening the folder link in browser and getting individual file links manually")
                raise
            else:
                raise
    
    return all_files


def extract_shared_link(url: str) -> str:
    """Extract clean shared link from URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Get image URLs from Dropbox folders")
    parser.add_argument("--token", help="Dropbox access token")
    args = parser.parse_args()
    
    # Get access token
    access_token = args.token or load_token_from_env()
    if not access_token:
        print("❌ Dropbox access token is required.")
        print("\n💡 To get a token:")
        print("   1. Go to https://www.dropbox.com/developers/apps")
        print("   2. Create a new app")
        print("   3. Generate an access token")
        print("   4. Add to .env: DROPBOX_ACCESS_TOKEN=your_token")
        sys.exit(1)
    
    # Load config
    config_file = project_root / "chatbot" / "api" / "dropbox_images.json"
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        sys.exit(1)
    
    with open(config_file, "r") as f:
        config = json.load(f)
    
    cottage_urls = config.get("cottage_image_urls", {})
    
    print("🔍 Analyzing Dropbox folders...\n")
    
    results = {}
    for cottage_num, folder_urls in cottage_urls.items():
        print(f"🏠 Cottage {cottage_num}")
        print("=" * 50)
        
        all_image_files = []
        for folder_url in folder_urls:
            try:
                shared_link = extract_shared_link(folder_url)
                files = list_files_in_shared_folder(access_token, shared_link)
                
                # Filter images
                image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', 
                             '.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP'}
                images = [
                    f for f in files 
                    if f.get(".tag") == "file" and 
                    any(f.get("name", "").endswith(ext) for ext in image_exts)
                ]
                
                print(f"   Found {len(images)} images in folder")
                all_image_files.extend(images)
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        # For each image, we need to get its individual shared link
        # The Dropbox API doesn't provide direct URLs for files in shared folders
        # So we'll provide instructions
        print(f"\n   Total: {len(all_image_files)} images found")
        print(f"\n   💡 To get direct URLs:")
        print(f"      1. Open the folder link in your browser")
        print(f"      2. For each image, right-click → 'Copy link'")
        print(f"      3. Change '?dl=0' to '?dl=1'")
        print(f"      4. Add URLs to dropbox_images.json or .env file")
        
        # Store file names for reference
        file_names = [f.get("name", "") for f in all_image_files[:10]]
        results[cottage_num] = {
            "count": len(all_image_files),
            "files": file_names,
            "note": "Use the instructions above to get direct URLs"
        }
    
    # Save results
    output_file = project_root / "dropbox_files_list.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ File list saved to: {output_file}")
    print("\n💡 Next steps:")
    print("   1. Open each Dropbox folder link")
    print("   2. Get individual file links (right-click → Copy link)")
    print("   3. Update dropbox_images.json with direct URLs")
    print("   4. Or use the manual method described in DROPBOX_IMAGE_SETUP.md")


if __name__ == "__main__":
    main()
