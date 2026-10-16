"""Deploy the static Vite build to an isolated public Google Cloud Storage bucket.

Uses existing Application Default Credentials; never writes or prints access tokens.
"""
import argparse
import json
import mimetypes
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--project', required=True)
parser.add_argument('--bucket', required=True)
parser.add_argument('--dist', type=Path, default=Path('player/dist'))
parser.add_argument('--location', default='ASIA-NORTHEAST3')
parser.add_argument('--update', action='store_true', help='Update an existing bucket labeled for Desk Buddy')
args = parser.parse_args()
if not (args.dist / 'index.html').is_file():
    raise SystemExit('Build the player before deploying.')
adc_path = Path.home() / '.config/gcloud/application_default_credentials.json'
adc = json.loads(adc_path.read_text())
if adc.get('type') != 'authorized_user':
    raise SystemExit('This helper expects existing authorized_user ADC credentials.')
refresh = urllib.parse.urlencode({
    'grant_type': 'refresh_token', 'client_id': adc['client_id'],
    'client_secret': adc['client_secret'], 'refresh_token': adc['refresh_token'],
}).encode()
with urllib.request.urlopen(urllib.request.Request('https://oauth2.googleapis.com/token', data=refresh), timeout=30) as r:
    token = json.load(r)['access_token']


def api(method, url, body=None, content_type='application/json'):
    payload = json.dumps(body).encode() if isinstance(body, dict) else body
    request = urllib.request.Request(url, data=payload, method=method, headers={
        'Authorization': 'Bearer ' + token,
        'x-goog-user-project': args.project,
        'Content-Type': content_type,
    })
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = response.read()
            return json.loads(result) if result else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors='replace')
        raise SystemExit(f'{method} failed ({exc.code}): {detail}') from None


base = 'https://storage.googleapis.com/storage/v1/b'
name = urllib.parse.quote(args.bucket, safe='')
# Create a dedicated demo bucket only. An existing bucket is never overwritten implicitly.
bucket_spec = {
    'name': args.bucket, 'location': args.location,
    'storageClass': 'STANDARD',
    'labels': {'app': 'desk-buddy', 'purpose': 'hackathon-demo'},
    'iamConfiguration': {'uniformBucketLevelAccess': {'enabled': True}},
    'website': {'mainPageSuffix': 'index.html'},
}
if args.update:
    existing = api('GET', base + '/' + name)
    if existing.get('labels', {}).get('app') != 'desk-buddy':
        raise SystemExit('Refusing to update a bucket without the Desk Buddy app label.')
    print('Updating Desk Buddy bucket:', existing['name'], flush=True)
else:
    created = api('POST', base + '?project=' + urllib.parse.quote(args.project), bucket_spec)
    print('Created Google Cloud Storage bucket:', created['name'], flush=True)
for path in sorted(args.dist.rglob('*')):
    if not path.is_file():
        continue
    object_name = path.relative_to(args.dist).as_posix()
    content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    api('POST', 'https://storage.googleapis.com/upload/storage/v1/b/' + name + '/o?uploadType=media&name=' + urllib.parse.quote(object_name, safe=''), path.read_bytes(), content_type)
    api('PATCH', base + '/' + name + '/o/' + urllib.parse.quote(object_name, safe=''), {'cacheControl': 'public,max-age=60' if object_name == 'index.html' else 'public,max-age=3600'})
    print('Uploaded:', object_name, flush=True)
# The user approved public hosting of this demo and its prerecorded desk assets.
policy = api('GET', base + '/' + name + '/iam')
bindings = policy.setdefault('bindings', [])
if not any(b.get('role') == 'roles/storage.objectViewer' and 'allUsers' in b.get('members', []) for b in bindings):
    bindings.append({'role': 'roles/storage.objectViewer', 'members': ['allUsers']})
    api('PUT', base + '/' + name + '/iam', policy)
print('PUBLIC_URL=https://storage.googleapis.com/' + args.bucket + '/index.html', flush=True)
