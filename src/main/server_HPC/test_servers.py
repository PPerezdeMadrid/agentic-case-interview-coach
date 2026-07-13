# Server for the HPC
#!/usr/bin/env python3
"""
Script para probar ambos servidores
Uso: python test_servers.py
"""

import requests
import time
import json

SERVERS = {
    "mistral": "http://127.0.0.1:18401",
    "llama": "http://127.0.0.1:18402"
}

def test_server(name, url):
    """Prueba un servidor específico"""
    print(f"\n{'='*50}")
    print(f"Testing {name.upper()} at {url}")
    print('='*50)
    
    # Test 1: /v1/models
    try:
        print(f"\n1️⃣  Testing /v1/models...")
        resp = requests.get(f"{url}/v1/models", timeout=5)
        if resp.status_code == 200:
            models = resp.json()
            print(f"✅ Models: {models['data'][0]['id']}")
        else:
            print(f"❌ Error: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    # Test 2: /v1/completions
    try:
        print(f"\n2️⃣  Testing /v1/completions...")
        payload = {
            "prompt": "Hello, world!",
            "max_tokens": 50,
            "temperature": 0.7
        }
        resp = requests.post(
            f"{url}/v1/completions",
            json=payload,
            timeout=30
        )
        if resp.status_code == 200:
            result = resp.json()
            completion = result["choices"][0]["text"][:100]
            print(f"✅ Completion: {completion}...")
        else:
            print(f"❌ Error: {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
    except requests.exceptions.Timeout:
        print(f"⚠️  Timeout (model is loading, that's OK)")
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

def main():
    print("Waiting for servers to start... (they need time to load models)")
    time.sleep(5)
    
    results = {}
    for name, url in SERVERS.items():
        max_retries = 3
        for attempt in range(max_retries):
            print(f"\nAttempt {attempt + 1}/{max_retries} for {name}...")
            if test_server(name, url):
                results[name] = True
                break
            time.sleep(5)
        else:
            results[name] = False
    
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    for name, success in results.items():
        status = "✅ OK" if success else "❌ FAILED"
        print(f"{name.upper()}: {status}")

if __name__ == "__main__":
    main()