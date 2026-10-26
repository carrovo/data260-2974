# HW7 Part 4 — Bay Wheels Official Data Preparation

This phase prepares model-independent tools and two acceptance datasets for
Bay Wheels / Lyft Bikes in the San Francisco Bay Area. It does not run a
ReAct agent and does not require Ollama, MySQL, or the HW7 web application.

## Official sources and cloud status

The workflow permits only these official sources:

- Pricing request URL:
  `https://www.lyft.com/bikes/bay-wheels/pricing`
- Expected pricing redirect:
  `https://lyftbikes.com/pricing`
- System-data page:
  `https://www.lyft.com/bikes/bay-wheels/system-data`
- Trip archive index:
  `https://s3.amazonaws.com/baywheels-data/index.html`
- Pinned archive for this workflow:
  `https://s3.amazonaws.com/baywheels-data/202401-baywheels-tripdata.zip`
  (month `202401`)

On 2026-10-26, this cloud environment attempted all three supplied source
URLs. Both normal and escalated network attempts failed before an HTTP
response with `CONNECT tunnel failed, response 403`. A direct request to
`https://lyftbikes.com/pricing` failed the same way. Consequently, this
commit intentionally contains no claimed official pricing snapshot and no
claimed official trip-derived CSV.

For cloud execution, allow outbound HTTPS to exactly these domains:

- `www.lyft.com`
- `lyftbikes.com`
- `www.lyftbikes.com` (redirect compatibility)
- `s3.amazonaws.com`
- `baywheels-data.s3.amazonaws.com` (S3 redirect compatibility)

The committed HTML fixture is labeled `TEST-ONLY`; it tests the parser and is
not evidence of current pricing. Offline scenario tests create temporary
synthetic rows whose IDs begin with `SYNTHETIC-TEST-`, label the manifest as
non-official, and delete all generated files at test completion.

## Mac prerequisites

- macOS zsh and Python 3.12.
- The repository's `.venv` with `requirements.txt` installed.
- Outbound HTTPS access to the domains above.
- Approximately 1 GB of temporary free space. The runner enforces a 750 MB
  archive limit. The exact ZIP size is supplied by the official server,
  printed after download, and saved with its SHA-256 in
  `tmp/hw7-part4/archive_metadata.json`.

From the repository root:

```zsh
git fetch origin
git switch hw7-work
git pull --ff-only origin hw7-work
source .venv/bin/activate
```

## Download, capture, and generate

The following single command:

1. captures the official pricing page with a timeout and 3 MB limit;
2. saves its requested/final URL, UTC and PDT capture times, exact parsed
   passages, raw HTML size, and SHA-256;
3. downloads the pinned January 2024 archive to the ignored `tmp/` area;
4. records archive URL, month, byte count, and SHA-256;
5. creates two 600-row scenario CSV files with LF endings; and
6. verifies that the pricing evidence produces opposite acceptance winners.

```zsh
python code/hw7_part4_data.py prepare \
  --month 202401 \
  --url https://s3.amazonaws.com/baywheels-data/202401-baywheels-tripdata.zip
```

No raw ZIP is written under `reports/` or intended for Git. The exact archive
URL is validated against the official S3 bucket and the requested month.

To run each stage separately:

```zsh
python code/hw7_part4_data.py capture-policy
python code/hw7_part4_data.py download-archive \
  --month 202401 \
  --url https://s3.amazonaws.com/baywheels-data/202401-baywheels-tripdata.zip
python code/hw7_part4_data.py generate-scenarios \
  --month 202401 \
  --url https://s3.amazonaws.com/baywheels-data/202401-baywheels-tripdata.zip
```

## Expected outputs

Successful official preparation creates:

- `reports/hw07/data/part4/policy/pricing_page.html`
- `reports/hw07/data/part4/policy/pricing_snapshot.json`
- `reports/hw07/data/part4/scenarios/membership_wins.csv`
- `reports/hw07/data/part4/scenarios/pay_per_use_wins.csv`
- `reports/hw07/data/part4/scenarios/transformation_manifest.json`
- `reports/hw07/data/part4/scenarios/scenario_summary.json`

The snapshot must parse and cite evidence for all of the following before
scenario generation is allowed:

- Month pass: `$29/month`
- Classic non-member: `$1` unlock plus `$0.19/min`
- Member classic: first 45 minutes included, then `$0.17/min`
- Non-member ebike: `$1` unlock plus `$0.49/min`
- Member ebike: `$0.17/min`

The pricing numbers used by the cost calculation are read from the captured
snapshot's `pricing_rules`; they are not separate untraceable constants.
Hash verification links each parsed rule back to the saved HTML bytes.

Each scenario preserves every original source column and adds only
`scenario_target`:

- `membership_wins`: the first 40 valid classic rides of at most 45 minutes
  in official archive order are assigned to the target user.
- `pay_per_use_wins`: the two shortest qualifying classic rides are assigned
  to the target user, with source-row order breaking ties.
- Both files are filled to 600 rows with official background trips.
- Background rows never contribute to target-user cost.
- The only synthetic production overlay is the target-user assignment; trip
  facts remain official rows.

The manifest documents these selection rules, source archive/member/hash,
preserved and added fields, cost assumptions, and each expected winner. The
expected winner is an acceptance-fixture assertion only; it must not be used
as an agent answer.

## Validation

After preparation:

```zsh
python code/hw7_part4_data.py verify
```

Run the deterministic offline suite:

```zsh
python code/test_hw7_part4_offline.py
```

Run one optional real pricing integration capture. It prints `SKIP` with the
network error when the official domains are unavailable and never substitutes
fixture text for an official capture:

```zsh
python code/test_hw7_part4_integration.py
```

To query either generated CSV through the bounded SQL tool in later UI work,
set its path outside model-controlled arguments:

```zsh
export HW7_PART4_CSV_PATH="$PWD/reports/hw07/data/part4/scenarios/membership_wins.csv"
```

The model-facing `csv_sql` schema accepts only `{"sql": "..."}`. It cannot
select a filesystem path.

## Cleanup

Remove only the uncommitted source archive and its metadata:

```zsh
rm -f tmp/hw7-part4/202401-baywheels-tripdata.zip
rm -f tmp/hw7-part4/archive_metadata.json
rmdir tmp/hw7-part4 2>/dev/null || true
```

The pricing snapshot, manifests, summaries, and two small scenario CSV files
remain as reproducibility evidence. Delete them only if you intend to rerun
the complete preparation workflow.
