#!/usr/bin/env python3
import json
import urllib.request
import urllib.parse
import sys
import os


TARGET_REPO = "ngxson/llama.cpp-test-mirror"
SOURCE_REPO = "ggerganov/llama.cpp"
SYNC_TAGS = [
    'server', 'light'
    #'server', 'light', 'full',
    #'server-intel', 'light-intel', 'full-intel',
    #'server-cuda', 'light-cuda', 'full-cuda',
    #'server-musa', 'light-musa', 'full-musa',
    #'server-vulkan', 'light-vulkan', 'full-vulkan'
]

####################################################################
# Registry API functions

def get_auth_token(repository, actions, host='ghcr.io', service='ghcr.io'):
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
        'scope': f'repository:{repository}:{actions}'
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

# Helper class to allow HTTP PUT
class PutRequest(urllib.request.Request):
    def get_method(self):
        return "PUT"

def push_manifest(dest_repository, reference, manifest_json, token, host='ghcr.io'):
    """
    Pushes a manifest (as JSON) to the destination repository.
    
    'reference' can be a tag (e.g. "latest") or a digest string.
    The Content-Type header is set based on the manifest's "mediaType" field.
    """
    url = f'https://{host}/v2/{dest_repository}/manifests/{reference}'
    media_type = manifest_json.get("mediaType", "application/vnd.docker.distribution.manifest.v2+json")
    data = json.dumps(manifest_json).encode('utf-8')
    req = PutRequest(url, data=data)
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', media_type)
    with urllib.request.urlopen(req) as response:
        status = response.getcode()
        resp_body = response.read().decode('utf-8')
    return status, resp_body

####################################################################
# Main function

def mirror_image(src_repo, src_ref, dest_repo, dest_tag, token_pull, token_push):
    print(f"Fetching manifest for {src_repo}:{src_ref}")
    manifest = fetch_manifest(src_repo, src_ref, token_pull)

    # Check if this is a multi-arch image index.
    if "manifests" in manifest:
        print("Detected multi-arch manifest index.")
        # For each sub-manifest, mirror it.
        for entry in manifest["manifests"]:
            sub_digest = entry.get("digest")
            platform = entry.get("platform", {})
            print(f"  Mirroring sub-manifest for platform {platform} with digest {sub_digest}")
            sub_manifest = fetch_manifest(src_repo, sub_digest, token_pull)
            status_sub, resp_sub = push_manifest(dest_repo, sub_digest, sub_manifest, token_push)
            print(resp_sub)
            print(f"  Pushed sub-manifest {sub_digest}: HTTP {status_sub}")
    else:
        print("Single-architecture manifest detected.")

    print("\nPushing top-level manifest (index or single manifest) to destination")
    status, response_body = push_manifest(dest_repo, dest_tag, manifest, token_push)
    return status, response_body

for tag in SYNC_TAGS:    
    # Obtain a token with both pull and push permissions for the source (and destination)
    token_pull = get_auth_token(SOURCE_REPO, 'pull')
    token_push = get_auth_token(TARGET_REPO, 'pull,push')

    try:
        status, resp = mirror_image(SOURCE_REPO, tag, TARGET_REPO, tag, token_pull, token_push)
        print(f"\nMirror push response: HTTP {status}")
        print(resp)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

