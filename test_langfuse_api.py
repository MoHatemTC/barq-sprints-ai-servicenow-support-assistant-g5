import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
secret_key = os.getenv("LANGFUSE_SECRET_KEY")
base_url = os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")

url = f"{base_url}/api/public/traces?sessionId=INC0010250"

response = httpx.get(
    url,
    auth=(public_key, secret_key),
    headers={"Accept": "application/json"}
)

if response.status_code == 200:
    data = response.json()
    traces = data.get("data", [])
    if not traces:
        print("No traces found for INC0010250.")
    else:
        trace_id = traces[0]["id"]
        print(f"Found trace ID: {trace_id}")
        
        # Fetch observations for this trace
        obs_url = f"{base_url}/api/public/observations?traceId={trace_id}"
        obs_resp = httpx.get(obs_url, auth=(public_key, secret_key))
        if obs_resp.status_code == 200:
            obs_data = obs_resp.json()
            observations = obs_data.get("data", [])
            print(f"Total observations: {len(observations)}")
            for obs in observations:
                print(f"- Type: {obs.get('type')}, Name: {obs.get('name')}, Prompt Tokens: {obs.get('promptTokens')}, Comp Tokens: {obs.get('completionTokens')}, Total Tokens: {obs.get('totalTokens')}, Calc Cost: {obs.get('calculatedTotalCost')}")
        else:
            print(f"Failed to fetch observations: {obs_resp.status_code}")
else:
    print(f"Failed to fetch traces: {response.status_code} {response.text}")
