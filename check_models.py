import requests
import json

# Your API key is included here
API_KEY = "AIzaSyCXibdnlNGtYfvJ2oE4bRMz11mzzrwY2-I"

# The special URL to "List Models"
LIST_MODELS_URL = f"https://generativelanguage.googleapis.com/v1/models?key={API_KEY}"

print("--- Checking available Gemini models for your API key ---")

try:
    response = requests.get(LIST_MODELS_URL)
    
    if response.status_code == 200:
        data = response.json()
        print("\nSUCCESS! Here are the models available to you:\n")
        
        # Pretty-print the JSON response
        print(json.dumps(data, indent=2))
        
        print("\n--- INSTRUCTIONS ---")
        print("Look for a model that supports 'generateContent'. The 'name' will be something like 'models/gemini-pro'.")
        print("Copy that exact name (e.g., 'gemini-pro') and we will use it in app.py.")

    else:
        print(f"\nERROR! Failed to get a list of models.")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

except requests.exceptions.RequestException as e:
    print(f"\nA network error occurred: {e}")


