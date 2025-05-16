"""Test Perplexity API directly."""
import httpx
from dora.models.config import DoraConfig

def test_perplexity():
    config = DoraConfig()
    url = "https://api.perplexity.ai/chat/completions"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.perplexity_api_key}",
    }
    
    data = {
        "model": "pplx-7b-online",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that helps find events."},
            {"role": "user", "content": "Find upcoming events in San Francisco for the next 2 weeks"},
        ],
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"Success! Content:\n{content}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_perplexity()