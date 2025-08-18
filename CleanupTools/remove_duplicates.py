# remove_duplicates.py
"""
A simple and safe utility script to remove duplicate URL links from a Python file.

This script reads a target .py file, finds all lines containing URLs, and
removes any line where the URL has already appeared earlier in the file.
It preserves all other code, comments, and formatting.

An automatic backup of the original file is created with a '.bak' extension.

Usage:
    python remove_duplicates.py /Users/vic/AxiomEngine/src/axiom_server/discovery_rss.py
"""

import re
import shutil
import sys
from typing import Set

def clean_duplicate_links(filepath: str):
    """
    Reads a Python file, removes lines with duplicate URLs, and overwrites the file.
    """
    # --- 1. Safety Check: Make sure the file exists ---
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ Error: The file '{filepath}' was not found.")
        return

    # --- 2. The Core Logic: Find and filter duplicates ---
    print(f"🔍 Scanning '{filepath}' for duplicate links...")
    
    seen_urls: Set[str] = set()
    new_lines = []
    duplicates_found = 0
    
    # This simple regex finds any http or https link inside quotes.
    url_pattern = re.compile(r'["\'](https?://.*?)["\']')

    for line in original_lines:
        match = url_pattern.search(line)
        
        # If the line contains a URL...
        if match:
            url = match.group(1)
            # Check if we've already seen this URL
            if url in seen_urls:
                duplicates_found += 1
                # If we have, DO NOTHING (this removes the line)
            else:
                # If it's a new URL, add it to our set and keep the line
                seen_urls.add(url)
                new_lines.append(line)
        # If the line does not contain a URL, keep it
        else:
            new_lines.append(line)

    # --- 3. Final Action: Backup and rewrite the file ---
    if duplicates_found == 0:
        print("✅ No duplicate links found. The file is already clean!")
        return

    print(f"Found and removed {duplicates_found} duplicate link(s).")
    
    # Create a backup before overwriting
    backup_path = f"{filepath}.bak"
    try:
        shutil.copy(filepath, backup_path)
        print(f"👍 A backup of the original file has been saved to: {backup_path}")
        
        # Write the clean content back to the original file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        print(f"✅ Successfully cleaned '{filepath}'!")
        
    except Exception as e:
        print(f"❌ FATAL ERROR: Could not write to the file. Error: {e}")
        print("Your original file has NOT been modified.")


if __name__ == "__main__":
    # Get the filename from the command line arguments
    if len(sys.argv) < 2:
        print("❗️ Usage: python remove_duplicates.py <filename.py>")
        print("   Example: python remove_duplicates.py src/axiom_server/discovery_rss.py")
    else:
        target_file = sys.argv[1]
        clean_duplicate_links(target_file)