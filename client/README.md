# PriceRig client-side assessment

The client asks about the intended workload, gathers a one-time Windows
hardware inventory, compares detectable capacity only with requirements the
user supplies, and writes a local JSON and readable text report.

It does **not** run benchmarks or stress tests, invent telemetry, or claim to
identify a live bottleneck. Missing requirements and unsupported hardware
readings remain unknown. Meeting a minimum-capacity requirement is not proof
that an application will perform well.

## Run on Windows

Requires Python 3.10 or newer.

```powershell
cd client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python collector.py
```

Detailed device inventory uses Windows Management Instrumentation (WMI).
`psutil` supplies point-in-time memory and volume-capacity readings. GPU
dedicated memory may be unavailable from Windows WMI on some drivers; the
collector does not infer it from shared memory. No serial numbers, product
keys, hostnames, usernames, or network identifiers are collected.

### Optional passive sample

`python collector.py --sample-seconds 10` observes current CPU, memory, disk
I/O rates, and NVIDIA GPU activity for at most 30 seconds. It does not start
any work, stress the device, or ask the user to reproduce a problem. Its
results are explicitly labeled as a short ambient snapshot and are not used
to claim a workload bottleneck. The sample is disabled by default.

## SysGap catalog and optional report upload

Catalog lookups use the SysGap API by default. Override its base URL with
`SYSGAP_API_BASE_URL` or `--api-url`. Upload is separate and disabled unless
requested:

```powershell
$env:SYSGAP_API_BASE_URL = "https://your-sysgap-api-host"
python compare_and_submit.py --report .\reports\assessment_YYYYMMDD.json `
  --components cpu gpu ram storage
```

This makes read-only `POST /api/v1/catalog/query` calls containing only the
selected component and explicit numeric requirements from the questionnaire.
It does not send the hardware inventory to run catalog queries. It requests at
most five rows per component. Matching catalog rows are not performance
rankings or proof of upgrade need/compatibility. The API catalog currently has
no declared units for all numeric capacity fields, so results near a capacity
threshold should be verified against the manufacturer's specifications.

The questionnaire asks for optional minimum CPU physical cores and CPU base
clock so CPU queries can use explicit floors such as the API's documented
`cores.total >= 6` and `clocks.performance.base >= 3.2` filters. It never
derives those floors from a symptom or workload label.

To also submit the combined report, only after reviewing it and the server
behavior, add `--upload`. The client asks for explicit consent and posts to
`POST /api/v1/reports`. HTTPS is required except for localhost development.
The API currently runs a legacy gaming diagnosis against `telemetry.utilization`;
an inventory-only client report does not provide workload utilization, and the
server may consequently store a misleading “balanced” diagnosis. The client
does not fabricate utilization values. The API's report URL is a JSON retrieval
endpoint (`GET /api/v1/reports/{report_id}`), not a verified static HTML page.
Confirm these behaviors with the backend owner before using report upload for a
demo.

## Catalog shortlist

Use `--catalog-root "C:\path\to\open-db"` instead of the remote API URL only
for local/offline development. A single command queries the remote catalog and
combines its results into readable and JSON reports (replace the report
filename with the JSON path printed by `collector.py`):

```powershell
python compare_and_submit.py --report .\reports\assessment_YYYYMMDD.json `
  --components cpu gpu ram storage motherboard
```

`--components` defaults to all five categories. A category without a positive
structured requirement is marked `not_ranked` without querying. Motherboard
queries are currently withheld because no explicit selection criteria or
reliable compatibility data exists. Desktop, laptop, and unknown-form-factor
systems can all receive specification matches, but compatibility always
remains unknown. For laptops especially, the matching parts may be soldered,
non-upgradeable, or specific to the exact model; verify replaceability and
supported parts in the manufacturer's service manual before acting. RAM and
storage matches are capacity-based only; GPU and CPU matching also does not
establish relative performance or upgrade value. `--limit` can lower the
per-category API result cap from five.

To submit the combined report too, add `--upload`; the client prompts for
consent. To query and upload using a non-default API, pass
`--api-url "https://your-sysgap-api-host"`. The command may also use
`--recommendations` with previously generated shortlist JSON files instead of
querying the API or local catalog.

### Test the complete client-to-API flow locally

The repository includes a localhost-only mock API. It holds accepted payloads
in memory, writes nothing to disk, and is not for deployment.

1. In a PowerShell window, start the mock:

   ```powershell
   cd client
   python dev_api.py
   ```

2. In a second PowerShell window, run the assessment and upload to the mock:

   ```powershell
   cd client
   python collector.py --api-url http://127.0.0.1:8765/api/v1/reports --upload
   ```

   Complete the questionnaire. The collector saves local reports, displays
   the upload-consent prompt, and prints the mock `report_url` after consent.

3. Open that URL in a browser to inspect the exact JSON body received by the
   mock. Reports exist only while the mock process is running.

4. Stop the mock with Ctrl+C. The mock also has a loopback-only shutdown route:
   `http://127.0.0.1:8765/__shutdown`.

## Assessment methodology and limitations

The engine performs explicit comparisons only for minimum RAM, dedicated VRAM,
and free storage requirements that the user enters. These findings are based
on detected capacities and user-supplied requirements. The questionnaire
allows a URL/document reference for those requirements; the client records but
does not independently verify that source. CPU model text is not converted to
a performance score without a curated, comparable CPU data source.

The purpose-specific questions provide context for the report; they do not
create hidden generic minimum requirements. “Unknown” and “not assessed” are
intentional results where a reliable comparison is not possible. Symptoms are
recorded but not attributed to a component because the application workload
was not observed.

Run unit tests from this folder:

```powershell
python -m unittest discover -s tests -v
```
