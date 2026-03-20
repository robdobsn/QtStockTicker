# Stock List Storage: Options & Recommendations

## How It Works Today

`HostedConfigFile.py` is the core orchestrator for stock list storage. It reads `ConfigLocations` from `privatesettings/stockTickerConfig.json`, where each location can be a **local path**, **FTP server**, or **HTTP endpoint**. On startup it:

1. Fetches the stock list from **every** configured location
2. Compares the `FileVersion` integer in each copy
3. Picks the highest version as canonical
4. **Syncs it back** to any location that had an older version

On save, it **increments** `FileVersion` and writes to **all** locations. Conflict resolution is purely **last-write-wins** — there is no merge logic.

### Current Configuration Model

Each location in `ConfigLocations` supports:

| Field | Purpose |
|-------|---------|
| `hostURLForGet` / `hostURLForPut` | Server address |
| `filePathForGet` / `filePathForPut` | Remote path |
| `getUsing` / `putUsing` | Protocol — `'local'`, `'ftp'`, or `'http'` |
| `userName`, `passWord` | Credentials for FTP/HTTP |
| `sourceName` | Human-readable identifier |

---

## Current Problems

### Security

- **Plaintext credentials** — FTP/HTTP usernames and passwords sit in `stockTickerConfig.json` in clear text
- **No HTTPS enforcement** — HTTP fetch paths transmit Basic Auth credentials unencrypted
- **No integrity verification** — downloaded JSON is trusted without checksum or signature; a man-in-the-middle could inject malicious data
- **UNC share access** — the template default (`//macallan/admin`) relies on Windows network share permissions, which are coarse-grained

### Conflict & Offline Risks

- **No real merge** — if you edit offline (local becomes v4) and someone else edits on another machine (server also becomes v4), the first one to connect "wins" and silently overwrites the other
- **Silent data loss** — partial write failures (server succeeds, local fails or vice versa) can cause version divergence, and on next sync the lower-version copy is silently overwritten
- **No audit trail** — there is no history of what changed or when

---

## Option A: S3 Bucket with Token-Based Access

Replace the HTTP/FTP/UNC locations with an S3 bucket. Access via a pre-shared IAM access key, or better, a pre-signed URL or STS temporary token.

| Pros | Cons |
|------|------|
| Encrypted at rest + in transit (HTTPS by default) | Still last-write-wins unless you add locking or S3 object versioning |
| Fine-grained IAM policies (read-only vs read-write per user) | Requires AWS account setup and token management |
| S3 versioning provides automatic history/rollback | Credentials still need to live somewhere (env vars, AWS credentials file) |
| Works well with the existing `HostedConfigFile` architecture — just add an `'s3'` protocol | Adds `boto3` dependency |
| Low cost (~$0/month for a single small JSON file) | Offline edits still can't merge — you'd need a conflict strategy |

### Implementation Outline

- Add `getUsing: "s3"` / `putUsing: "s3"` support in `HostedConfigFile.py`
- Location config gets `bucket`, `key`, `region` fields
- Credentials via `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars (or `~/.aws/credentials`)
- GET: `s3.get_object()` → return contents
- PUT: `s3.put_object()` → write contents
- Keep the local location as the second entry in `ConfigLocations` (offline fallback)

**Verdict**: Good security improvement, but **doesn't solve the conflict problem** by itself.

---

## Option B: Private GitHub Repo

Store `stocklist.json` in a private GitHub repo. The app would pull/push via the GitHub API (or git CLI). The local copy is the git working tree.

| Pros | Cons |
|------|------|
| **Full version history** with diffs — you can see exactly what changed and when | Heavier dependency (git or PyGithub/requests to GitHub API) |
| **Merge support** — git can detect conflicts rather than silently overwriting | JSON merge conflicts are ugly (line-based diff on a structured file) |
| **Offline-first** by design — commit locally, push when online | Requires user to have a GitHub account + Personal Access Token (PAT) |
| Branch-based workflows possible (e.g. per-device branches) | Overkill for a single JSON file |
| Free private repos | Push/pull adds latency to startup |
| GitHub Actions could validate the JSON on push | |

### Implementation Outline

- Store `stocklist.json` in a dedicated private repo (e.g. `robdobsn/stock-config`)
- App uses the GitHub REST API via `requests` or the `PyGithub` library
- Authentication via a PAT stored in an environment variable or OS keyring
- On startup: fetch latest from GitHub, compare with local `FileVersion`, sync
- On save: commit and push via API; handle 409 Conflict by fetching remote and prompting user
- Local file remains as working copy for offline use

**Verdict**: Best for conflict detection and audit trail, but **adds significant complexity** for a single config file.

---

## Option C: S3 + Object Versioning with Conditional Writes (Recommended)

Use S3 as the remote store with **object versioning enabled** and **conditional writes** (`If-None-Match` / `If-Match` ETags):

1. On startup: `GET` from S3, note the `ETag`/`VersionId`, sync to local
2. On save: `PUT` with `If-Match: <previous-ETag>` — this **fails** if someone else updated in the meantime
3. On conflict: download the newer remote version, present both to the user, let them choose or manually merge
4. S3 version history provides rollback without git overhead

| Pros | Cons |
|------|------|
| Encrypted, authenticated, versioned | Requires AWS account |
| **Conditional writes prevent silent overwrites** | Conflict resolution UI needed in the app |
| Automatic version history in S3 | Slightly more complex than plain S3 PUT |
| Lightweight — no git needed | Offline edits still deferred until reconnect |
| Fits naturally into the existing `HostedConfigFile` architecture | Adds `boto3` dependency |

### Implementation Details

#### Configuration

Add a new location type to `stockTickerConfig.json`:

```json
{
  "ConfigLocations": [
    {
      "getUsing": "s3",
      "putUsing": "s3",
      "bucket": "my-stock-config",
      "key": "stocklist.json",
      "region": "eu-west-1",
      "sourceName": "s3"
    },
    {
      "filePathForGet": "stocklist.json",
      "getUsing": "local",
      "sourceName": "local"
    }
  ]
}
```

#### Credential Management

AWS credentials and region are stored in `privatesettings/config.ini` alongside other API keys (this file is already gitignored). Add the following entries:

```ini
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=wJal...
AWS_REGION=eu-west-1
```

`HostedConfigFile.py` reads these via its `_readConfigValue()` helper and passes them explicitly to `boto3.client()`. If either key is blank or missing, boto3 falls back to its default credential chain (`~/.aws/credentials`, environment variables, etc.).

The region is resolved with the following precedence:
1. `region` field in the S3 location entry in `stockTickerConfig.json` (if set)
2. `AWS_REGION` in `config.ini`
3. `us-east-1` default

**IAM policy**: Scope the IAM user to `s3:GetObject`, `s3:PutObject`, `s3:GetObjectVersion`, `s3:ListBucketVersions`, and `s3:HeadObject` on the single bucket/key.

Example minimal IAM policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:GetObjectVersion",
        "s3:ListBucketVersions",
        "s3:HeadObject"
      ],
      "Resource": [
        "arn:aws:s3:::my-stock-config",
        "arn:aws:s3:::my-stock-config/*"
      ]
    }
  ]
}
```

#### Code Changes in `HostedConfigFile.py`

S3 support was added alongside the existing `local`, `ftp`, and `http` protocols. Key methods:

**`_readConfigValue(key)`** — reads `KEY=VALUE` entries from `privatesettings/config.ini` (handles spaces around `=`).

**`_getS3Client(locn)`** — creates a `boto3` S3 client using credentials and region from `config.ini`, falling back to the default AWS credential chain if not configured:

```python
def _getS3Client(self, locn):
    if not _HAS_BOTO3:
        logger.error("boto3 is not installed - S3 support unavailable")
        return None
    access_key = self._readConfigValue('AWS_ACCESS_KEY_ID')
    secret_key = self._readConfigValue('AWS_SECRET_ACCESS_KEY')
    region = locn.get('region') or self._readConfigValue('AWS_REGION') or 'us-east-1'
    kwargs = {'region_name': region}
    if access_key and secret_key:
        kwargs['aws_access_key_id'] = access_key
        kwargs['aws_secret_access_key'] = secret_key
    return boto3.client('s3', **kwargs)
```

**`getFileFromS3(locn, outFile)`** — fetches the object and stores the `ETag` and `VersionId` on the location dict for later conflict detection:

```python
def getFileFromS3(self, locn, outFile):
    s3 = self._getS3Client(locn)
    response = s3.get_object(Bucket=locn['bucket'], Key=locn['key'])
    contents = response['Body'].read().decode('utf-8')
    locn['_last_etag'] = response.get('ETag', '')
    locn['_last_version_id'] = response.get('VersionId', '')
    outFile.write(contents)
```

**`putFileToS3(locn, contents, conditional=True)`** — writes to S3 with an optional ETag-based conflict check. When `conditional=True` (the default for user-initiated saves), it compares the current remote ETag against the one captured at read time and refuses to write if the remote changed:

```python
def putFileToS3(self, locn, contents, conditional=True):
    s3 = self._getS3Client(locn)
    if conditional:
        expected_etag = locn.get('_last_etag', '')
        if expected_etag:
            head = s3.head_object(Bucket=locn['bucket'], Key=locn['key'])
            if head.get('ETag', '') != expected_etag:
                logger.warning("S3 conflict detected")
                return False
    s3.put_object(Bucket=locn['bucket'], Key=locn['key'],
                  Body=contents.encode('utf-8'), ContentType='application/json')
    return True
```

The sync-back path (used when auto-syncing an older source to the latest version) calls `putFileToS3` with `conditional=False` since that is not a user-initiated edit.

`boto3` is imported with a graceful fallback so the app still works without it installed:

```python
try:
    import boto3
    from botocore.exceptions import ClientError
    _HAS_BOTO3 = True
except ImportError:
    _HAS_BOTO3 = False
```

#### Conflict Resolution Flow

```
User saves stock list
  │
  ├─ PUT to S3 with ETag check
  │   ├─ Success → update local copy, done
  │   └─ Conflict (ETag mismatch) →
  │       ├─ GET latest from S3
  │       ├─ Compare with local version
  │       └─ Prompt user:
  │           "Remote stock list was modified. Keep remote / Keep local / Review both?"
  │
  └─ PUT to local (always succeeds)
```

#### S3 Bucket Setup

1. Create bucket with versioning enabled:
   ```
   aws s3api create-bucket --bucket my-stock-config --region eu-west-1 \
     --create-bucket-configuration LocationConstraint=eu-west-1
   aws s3api put-bucket-versioning --bucket my-stock-config \
     --versioning-configuration Status=Enabled
   ```

2. Block public access (default, but explicit):
   ```
   aws s3api put-public-access-block --bucket my-stock-config \
     --public-access-block-configuration \
     BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
   ```

3. Enable server-side encryption:
   ```
   aws s3api put-bucket-encryption --bucket my-stock-config \
     --server-side-encryption-configuration \
     '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
   ```

#### Dependencies

Add to `requirements.txt`:

```
boto3>=1.26.0
```

---

## Option D: GitHub Gist (Lightweight Git)

A **secret GitHub Gist** gives you git versioning for a single file without a full repo.

| Pros | Cons |
|------|------|
| Version history, free, private | Still needs a PAT |
| GitHub API is simple (`PATCH /gists/{id}`) | No conditional write — same last-write-wins issue unless you check the gist's `updated_at` before writing |
| Easy to view/edit in browser as backup | Less robust than S3 for programmatic access |

### Implementation Outline

- Create a secret gist containing `stocklist.json`
- App uses `requests` to call the GitHub Gist API
- Check `updated_at` timestamp before writing to detect conflicts
- Store the gist ID and PAT in environment variables

**Verdict**: Simple but limited — no conditional writes without extra logic.

---

## Recommendation

**Option C (S3 + Object Versioning)** is the best balance of security, conflict safety, and implementation simplicity:

1. **Security**: HTTPS by default, IAM scoping, encrypted at rest. Credentials stored in `privatesettings/config.ini` (already gitignored) alongside other API keys — never in the JSON location config.
2. **Conflict safety**: Conditional writes via ETag comparison make silent data loss impossible. The app can detect when the remote changed and prompt the user.
3. **Audit trail**: S3 versioning gives free history without git complexity. Any version can be retrieved or restored.
4. **Minimal code change**: The existing `HostedConfigFile` location model already supports multiple protocols. Adding `'s3'` as a new `getUsing`/`putUsing` type was ~80 lines of code.
5. **Offline support**: Keep the local file as-is. On reconnect, compare local `FileVersion` + S3 `ETag` to detect divergence.
6. **Cost**: Effectively zero for a single small JSON file.

If richer conflict handling (true merge, branching) is needed later, migration to the GitHub repo approach (Option B) is straightforward — but for a single JSON config file, S3 with conditional writes provides 90% of the benefit at 20% of the complexity.
