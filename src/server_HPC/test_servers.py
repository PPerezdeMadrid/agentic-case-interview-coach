#!/usr/bin/env python3
"""Smoke test for the HPC-hosted model servers.

Usage: python test_servers.py
"""

import time

import requests

SERVERS = {
    "mistral": "http://127.0.0.1:18401",
    "llama": "http://127.0.0.1:18402",
    # "mistral-small": "http://127.0.0.1:18403",  # uncomment if server.bash launches it
}


def test_server(name, url):
    """Runs the /v1/models, /v1/completions, and /v1/chat/completions checks for one server."""
    print(f"\n{'='*50}")
    print(f"Testing {name.upper()} at {url}")
    print("=" * 50)

    try:
        print("\n1) Testing /v1/models...")
        resp = requests.get(f"{url}/v1/models", timeout=5)
        if resp.status_code != 200:
            print(f"FAILED: {resp.status_code}")
            return False
        model_id = resp.json()["data"][0]["id"]
        print(f"OK: {model_id}")
    except Exception as e:
        print(f"FAILED: {e}")
        return False

    try:
        print("\n2) Testing /v1/completions...")
        payload = {"prompt": "Hello, world!", "max_tokens": 30, "temperature": 0.0}
        resp = requests.post(f"{url}/v1/completions", json=payload, timeout=120)
        if resp.status_code != 200:
            print(f"FAILED: {resp.status_code} {resp.text}")
            return False
        print(f"OK: {resp.json()['choices'][0]['text'][:100]!r}")
    except Exception as e:
        print(f"FAILED: {e}")
        return False

    try:
        print("\n3) Testing /v1/chat/completions...")
        payload = {
            "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
            "max_tokens": 30,
            "temperature": 0.0,
        }
        resp = requests.post(f"{url}/v1/chat/completions", json=payload, timeout=120)
        if resp.status_code != 200:
            print(f"FAILED: {resp.status_code} {resp.text}")
            return False
        print(f"OK: {resp.json()['choices'][0]['message']['content'][:100]!r}")
    except Exception as e:
        print(f"FAILED: {e}")
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

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"{name.upper()}: {status}")


if __name__ == "__main__":
    main()
