#!/usr/bin/env python3
"""
Script to automatically fetch image URLs from Dropbox shared folders.

This script uses the Dropbox API to list files in shared folders and get
direct download links for each image.

Usage:
    python scripts/fetch_dropbox_images.py

Requirements:
    - DROPBOX_ACCESS_TOKEN in .env file (get from https://www.dropbox.com/developers/apps)
    - Or provide token via command line: --token YOUR_TOKEN
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import requests
except ImportError:
    print("❌ Error: 'requests' library is required.")
    print("   Install it with: pip install requests")
    sys.exit(1)


class DropboxImageFetcher:
    """Fetch image URLs from Dropbox shared folders."""
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize with Dropbox access token.
        
        Args:
            access_token: Dropbox API access token. If None, tries to load from .env
        """
        self.access_token = access_token or self._load_token_from_env()
        if not self.access_token:
            raise ValueError(
                "Dropbox access token is required. "
                "Set DROPBOX_ACCESS_TOKEN in .env file or pass --token argument."
            )
        self.api_base = "https://api.dropboxapi.com"
        self.content_base = "https://content.dropboxapi.com"
    
    def _load_token_from_env(self) -> Optional[str]:
        """Load Dropbox access token from .env file."""
        env_file = project_root / ".env"
        if env_file.exists():
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DROPBOX_ACCESS_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        return None
    
    def _make_api_request(self, endpoint: str, data: Dict, headers: Optional[Dict] = None) -> Dict:
        """Make a request to Dropbox API."""
        url = f"{self.api_base}{endpoint}"
        default_headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        if headers:
            default_headers.update(headers)
        
        try:
            response = requests.post(url, json=data, headers=default_headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API Error: {e}")
            if hasattr(e.response, 'text'):
                print(f"   Response: {e.response.text}")
            raise
    
    def extract_shared_link_from_url(self, url: str) -> str:
        """
        Extract the shared link from a Dropbox folder URL.
        
        Dropbox folder sharing URLs have format:
        https://www.dropbox.com/scl/fo/...?rlkey=...&st=...&dl=0
        
        We need to extract just the base URL part.
        """
        # Remove query parameters and get base URL
        parsed = urlparse(url)
        # Reconstruct base URL without query params
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return base_url
    
    def get_shared_link_metadata(self, shared_link: str) -> Dict:
        """Get metadata for a shared link."""
        endpoint = "/2/sharing/get_shared_link_metadata"
        data = {
            "url": shared_link
        }
        return self._make_api_request(endpoint, data)
    
    def list_shared_link_files(self, shared_link: str, path: str = "") -> List[Dict]:
        """
        List all files in a shared folder.
        
        Args:
            shared_link: The shared folder link
            path: Path within the folder (empty for root)
        
        Returns:
            List of file metadata dictionaries
        """
        endpoint = "/2/sharing/list_shared_link_files"
        data = {
            "url": shared_link,
            "path": path
        }
        
        all_files = []
        has_more = True
        
        while has_more:
            response = self._make_api_request(endpoint, data)
            
            # Add files from this page
            if "entries" in response:
                all_files.extend(response["entries"])
            
            # Check if there are more files
            has_more = response.get("has_more", False)
            if has_more and "cursor" in response:
                data["cursor"] = response["cursor"]
            else:
                has_more = False
        
        return all_files
    
    def get_direct_download_urls(self, shared_folder_url: str, max_images: int = 10) -> List[str]:
        """
        Get direct download URLs for all images in a shared folder.
        
        Args:
            shared_folder_url: The Dropbox shared folder URL
            max_images: Maximum number of images to return
        
        Returns:
            List of direct download URLs
        """
        print(f"📁 Processing folder: {shared_folder_url}")
        
        # Extract clean shared link (remove query params for API calls)
        shared_link = self.extract_shared_link_from_url(shared_folder_url)
        
        # List all files in the folder
        try:
            files = self.list_shared_link_files(shared_link)
        except Exception as e:
            print(f"❌ Error listing files: {e}")
            if "invalid_access_token" in str(e).lower():
                print("   💡 Check your DROPBOX_ACCESS_TOKEN in .env file")
            return []
        
        # Filter for image files
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP'}
        image_files = [
            f for f in files 
            if f.get(".tag") == "file" and 
            any(f.get("name", "").endswith(ext) for ext in image_extensions)
        ]
        
        print(f"   Found {len(image_files)} image files")
        
        # Get direct download URLs
        direct_urls = []
        for file_info in image_files[:max_images]:
            file_path = file_info.get("path_lower", file_info.get("name", ""))
            file_name = file_info.get("name", "")
            
            # Method 1: Try to get individual file shared link
            # For files in shared folders, we need to get their individual shared links
            try:
                # Use sharing API to get file metadata and construct URL
                endpoint = "/2/sharing/get_shared_link_file"
                url = f"{self.content_base}{endpoint}"
                
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Dropbox-API-Arg": json.dumps({
                        "url": shared_link,
                        "path": file_path
                    })
                }
                
                # Make a request with allow_redirects=False to capture redirect
                # The API returns the file, but we want the URL it redirects to
                session = requests.Session()
                response = session.post(url, headers=headers, allow_redirects=False, stream=True, timeout=10)
                
                # Check for redirect
                if response.status_code in [302, 307, 308]:
                    # Get redirect location
                    redirect_url = response.headers.get('Location', '')
                    if redirect_url:
                        final_url = redirect_url
                    else:
                        # Try to get from response URL
                        final_url = response.url
                elif response.status_code == 200:
                    # If no redirect, the URL might be in the response
                    final_url = response.url
                else:
                    # Try alternative: create individual shared link for the file
                    # This requires the file to be in the user's Dropbox
                    print(f"   ⚠️  {file_name} - status {response.status_code}, trying to create shared link")
                    
                    # Alternative method: Try to get file ID and create link
                    # For shared folder files, we need to use a different endpoint
                    # Skip for now and try manual URL construction
                    final_url = None
                
                if final_url:
                    # Ensure it's a direct download link
                    if "?dl=0" in final_url:
                        final_url = final_url.replace("?dl=0", "?dl=1")
                    elif "?" not in final_url:
                        final_url = f"{final_url}?dl=1"
                    elif "dl=" not in final_url:
                        final_url = f"{final_url}&dl=1"
                    
                    # Convert to dl.dropboxusercontent.com for better reliability
                    final_url = final_url.replace("www.dropbox.com", "dl.dropboxusercontent.com")
                    direct_urls.append(final_url)
                    print(f"   ✅ {file_name}")
                else:
                    # Last resort: Try to construct URL from shared link + file path
                    # This is a workaround and may not work for all cases
                    print(f"   ⚠️  {file_name} - could not get direct URL, skipping")
                    
            except requests.exceptions.RequestException as e:
                print(f"   ❌ {file_name} - error: {e}")
            except Exception as e:
                print(f"   ❌ {file_name} - unexpected error: {e}")
        
        return direct_urls


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Fetch image URLs from Dropbox shared folders"
    )
    parser.add_argument(
        "--token",
        help="Dropbox access token (or set DROPBOX_ACCESS_TOKEN in .env)"
    )
    parser.add_argument(
        "--output",
        choices=["json", "env", "both"],
        default="both",
        help="Output format (default: both)"
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=10,
        help="Maximum number of images per cottage (default: 10)"
    )
    
    args = parser.parse_args()
    
    # Load folder URLs from config
    config_file = project_root / "chatbot" / "api" / "dropbox_images.json"
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        print("   Please create it with folder URLs first.")
        sys.exit(1)
    
    with open(config_file, "r") as f:
        config = json.load(f)
    
    cottage_urls = config.get("cottage_image_urls", {})
    
    if not cottage_urls:
        print("❌ No cottage image URLs found in config file.")
        sys.exit(1)
    
    # Initialize fetcher
    try:
        fetcher = DropboxImageFetcher(access_token=args.token)
    except ValueError as e:
        print(f"❌ {e}")
        print("\n💡 To get a Dropbox access token:")
        print("   1. Go to https://www.dropbox.com/developers/apps")
        print("   2. Create a new app")
        print("   3. Generate an access token")
        print("   4. Add to .env: DROPBOX_ACCESS_TOKEN=your_token_here")
        sys.exit(1)
    
    # Fetch URLs for each cottage
    results = {}
    for cottage_num, folder_urls in cottage_urls.items():
        print(f"\n🏠 Cottage {cottage_num}")
        print("=" * 50)
        
        all_urls = []
        for folder_url in folder_urls:
            urls = fetcher.get_direct_download_urls(folder_url, max_images=args.max_images)
            all_urls.extend(urls)
        
        results[cottage_num] = all_urls[:args.max_images]
        print(f"\n✅ Found {len(results[cottage_num])} image URLs for cottage {cottage_num}")
    
    # Output results
    if args.output in ("json", "both"):
        output_file = project_root / "chatbot" / "api" / "dropbox_images.json"
        config["cottage_image_urls"] = results
        with open(output_file, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\n✅ Updated {output_file}")
    
    if args.output in ("env", "both"):
        env_output = []
        env_output.append("USE_DROPBOX=true")
        env_output.append("")
        
        for cottage_num, urls in results.items():
            if urls:
                urls_str = ",".join(urls)
                env_output.append(f"DROPBOX_COTTAGE_{cottage_num}_URLS=\"{urls_str}\"")
        
        env_file = project_root / "dropbox_images.env"
        with open(env_file, "w") as f:
            f.write("\n".join(env_output))
        print(f"✅ Created {env_file}")
        print("\n💡 You can copy these lines to your .env file:")
        print("\n".join(env_output))
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
