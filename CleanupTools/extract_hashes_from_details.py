import json
import os

# --- Configuration ---
# The name of the input file containing the full fact details
INPUT_FILENAME = "all_facts_details.txt"

# The name of the output file where the clean hashes will be saved
# This name matches what your get_facts.py script is looking for
OUTPUT_FILENAME = "hash_facts.txt"
# ---------------------

def extract_hashes():
    """
    Reads a JSON file containing fact details, extracts all the 'hash' values,
    and writes them to a new file, one hash per line.
    """
    print(f"--> Reading data from '{INPUT_FILENAME}'...")
    
    # --- Step 1: Read and parse the JSON data from the input file ---
    try:
        with open(INPUT_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ ERROR: The input file '{INPUT_FILENAME}' was not found in this directory.")
        return
    except json.JSONDecodeError:
        print(f"❌ ERROR: The file '{INPUT_FILENAME}' does not contain valid JSON. Cannot parse.")
        return

    # --- Step 2: Extract all the hash values ---
    # The data is a dictionary like {"facts": [...]}, so we get the list first.
    list_of_facts = data.get("facts")

    if not isinstance(list_of_facts, list):
        print(f"❌ ERROR: Could not find a list under the 'facts' key in the JSON file.")
        return
        
    all_hashes = []
    for fact_object in list_of_facts:
        fact_hash = fact_object.get("hash")
        if fact_hash:
            all_hashes.append(fact_hash)
    
    if not all_hashes:
        print("✅ Found no hashes in the input file. Output file will be empty.")
    else:
        print(f"👍 Success! Extracted {len(all_hashes)} hashes.")

    # --- Step 3: Write the hashes to the output file ---
    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            for single_hash in all_hashes:
                f.write(single_hash + '\n') # Write each hash followed by a new line
        
        output_path = os.path.abspath(OUTPUT_FILENAME)
        print(f"\n--> Saving results...")
        print("-" * 40)
        print("✅ Success! All hashes have been saved to:")
        print(f"   {output_path}")
        print("   You can now use this file with your get_facts.py script.")
        print("-" * 40)

    except IOError as e:
        print(f"❌ ERROR: Could not write the output file '{OUTPUT_FILENAME}'.")
        print(f"   Details: {e}")


if __name__ == "__main__":
    extract_hashes()