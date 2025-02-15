#!/usr/bin/env python3
import json
import urllib.request
import urllib.parse
import sys
import os


TARGET_REPO = "ngxson/llama.cpp-test-mirror"
SOURCE_REPO = "ggerganov/llama.cpp"
SYNC_TAGS = [
    'server', 'light', 'full',
    'server-intel', 'light-intel', 'full-intel',
    'server-cuda', 'light-cuda', 'full-cuda',
    'server-musa', 'light-musa', 'full-musa',
    'server-vulkan', 'light-vulkan', 'full-vulkan'
]

OUTPUT_SCRIPT = "tmp.sh"

####################################################################

def get_auth_token(repository, host='ghcr.io', service='ghcr.io'):
    """
    Retrieves an authentication token for the specified repository.

    For Docker Hub, the token endpoint is used with parameters:
      - host: auth.docker.io
      - service: registry.docker.io

    For ghcr.io the token endpoint is: https://ghcr.io/token?service=ghcr.io&scope=repository:<repository>:pull
      - host: ghcr.io
      - service: ghcr.io
    """
    token_url = f'https://{host}/token'
    query_params = {
        'service': service,
        'scope': f'repository:{repository}:pull'
    }
    url = token_url + '?' + urllib.parse.urlencode(query_params)

    with urllib.request.urlopen(url) as response:
        data = response.read()

    token_data = json.loads(data.decode('utf-8'))
    return token_data['token']

def fetch_manifest(repository, tag, token, host='ghcr.io'):
    """
    Fetches the manifest for the given repository and tag using the provided token.
    For docker hub, host is registry-1.docker.io
    """
    manifest_url = f'https://{host}/v2/{repository}/manifests/{tag}'
    req = urllib.request.Request(manifest_url)
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Accept', 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json')

    with urllib.request.urlopen(req) as response:
        data = response.read()

    return json.loads(data.decode('utf-8'))


####################################################################

def get_manifest_digest_set(repo, tag):
    token = get_auth_token(repo)
    manifest = fetch_manifest(repo, tag, token)
    print(f"Manifest:", json.dumps(manifest, indent=2))
    if 'manifests' in manifest:
        return set([elem['digest'] for elem in manifest['manifests']])
    else:
        return set([elem['digest'] for elem in manifest['layers']])

OUTPUT_SCRIPT_CONTENT = f"""#!/bin/bash

set -e
"""
TAGS_TO_BE_SYNCED = []

for tag in SYNC_TAGS:
    print(f"---")
    print(f"Checking tag: {tag}")
    try:
        print(f"Checking: {SOURCE_REPO}:{tag}")
        source_digests = get_manifest_digest_set(SOURCE_REPO, tag)

        # If destination repo is not found, we don't need to check for existing tags
        try:
            print(f"Checking: {TARGET_REPO}:{tag}")
            target_digests = get_manifest_digest_set(TARGET_REPO, tag)
        except Exception as e:
            print(f"Error: {e}")
            target_digests = set()

        if source_digests == target_digests:
            print(f"Tag '{tag}' is already in sync")
            continue
        else:
            print(f"Tag '{tag}' is out of sync")
            TAGS_TO_BE_SYNCED.append(tag)
            OUTPUT_SCRIPT_CONTENT += f"\n"
            OUTPUT_SCRIPT_CONTENT += f"docker pull ghcr.io/{SOURCE_REPO}:{tag}\n"
            OUTPUT_SCRIPT_CONTENT += f"docker tag ghcr.io/{SOURCE_REPO}:{tag} ghcr.io/{TARGET_REPO}:{tag}\n"
            OUTPUT_SCRIPT_CONTENT += f"docker push ghcr.io/{TARGET_REPO}:{tag}\n"
    
    except Exception as e:
        print(f"Error:", e)
        print(f"Skipping tag '{tag}' due to error")
        continue

print(f"---")
print(f"Tags to be synced: {TAGS_TO_BE_SYNCED}")

with open(OUTPUT_SCRIPT, 'w') as f:
    f.write(OUTPUT_SCRIPT_CONTENT)
