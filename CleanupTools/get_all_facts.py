import requests
import json
import os

# --- Configuration ---
# The URLs for your local Axiom node's API
GET_HASHES_URL = "http://localhost:8002/get_fact_hashes"
GET_FACTS_URL = "http://localhost:8002/get_facts_by_hash"

# The name of the output file
OUTPUT_FILENAME = "all_facts_details.txt"
# ---------------------

def fetch_and_save_all_facts():
    """
    Fetches all fact hashes, then uses them to get all fact details
    and saves the result to a text file.
    """
    print(f"--> Step 1: Fetching all fact hashes from {GET_HASHES_URL}...")
    
    # --- Step 1: Get the list of all fact hashes ---
    try:
        response_hashes = requests.get(GET_HASHES_URL, timeout=10)
        response_hashes.raise_for_status()  # This will raise an error for bad responses (4xx or 5xx)
        
        data = response_hashes.json()
        fact_hashes = data.get("fact_hashes")
        
        if not fact_hashes:
            print("✅ Found no fact hashes in the database. Nothing to do.")
            return

        print(f"👍 Success! Found {len(fact_hashes)} fact hashes.")

    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Could not connect to the Axiom node to get hashes.")
        print(f"   Please ensure your node is running and accessible at {GET_HASHES_URL}")
        print(f"   Details: {e}")
        return
    except json.JSONDecodeError:
        print("❌ ERROR: The server's response for hashes was not valid JSON. Cannot proceed.")
        return

    # --- Step 2: Use the hashes to get the full fact details ---
    print(f"\n--> Step 2: Fetching full details for {len(fact_hashes)} facts from {GET_FACTS_URL}...")
    
    payload = {"fact_hashes": fact_hashes}
    headers = {"Content-Type": "application/json"}
    
    try:
        response_facts = requests.post(GET_FACTS_URL, headers=headers, json=payload, timeout=30)
        response_facts.raise_for_status()
        
        # We get the JSON data to format it nicely
        facts_data = response_facts.json()
        
        # Format the JSON with indentation for readability
        formatted_output = json.dumps(facts_data, indent=4)
        
        print("👍 Success! Received full details for all facts.")

    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Could not connect to the Axiom node to get fact details.")
        print(f"   Details: {e}")
        return
    except json.JSONDecodeError:
        print("❌ ERROR: The server's response for fact details was not valid JSON.")
        return

    # --- Step 3: Save the final output to a file ---
    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            f.write(formatted_output)
        
        output_path = os.path.abspath(OUTPUT_FILENAME)
        print(f"\n--> Step 3: Saving results...")
        print("-" * 40)
        print("✅ Success! All fact details have been saved to:")
        print(f"   {output_path}")
        print("-" * 40)

    except IOError as e:
        print(f"❌ ERROR: Could not write the output file.")
        print(f"   Details: {e}")


if __name__ == "__main__":
    fetch_and_save_all_facts()