# SysGap client-side assessment

The client currently uses a lightweight Python core with a platform-provider
boundary. Windows has detailed WMI collection. Linux now collects common
memory/volume data, CPU identity/core counts, and GPU names through `lspci`
when available; macOS uses the reliable common `psutil` path for now.
Unsupported fields remain unknown. The report records the provider and
collection capabilities so missing platform data is visible rather than
inferred.

The client asks about the intended workload, gathers a one-time platform
inventory, compares detectable capacity with curated workload-preset floors,
and writes one final local JSON and readable text report after a successful
guided run.

It does **not** run benchmarks or stress tests, invent telemetry, or claim to
identify a live bottleneck. Missing requirements and unsupported hardware
readings remain unknown. Profile floors are provisional planning heuristics,
not official requirements. Meeting a floor is not proof that an application
will perform well.

## Workload presets and fallback floors

Gaming, video editing, and local AI use curated offline presets rather than
free-form application, game, or model names. Presets record a stable ID and
data version in the report. Gaming presets cover 1080p, 1440p, and 4K quality
targets; editing presets cover 1080p light work and two 4K complexity levels;
AI presets cover up to 7B, 13B, and 30B parameter models with 4-bit
quantization. AI runs also ask for context length and CPU/GPU inference mode,
which adjust the planning floors transparently.

Preset values are planning heuristics, not vendor requirements or performance
guarantees. Users can still enter official numeric requirements, which
override the corresponding preset value.

When a user leaves an individual numeric requirement blank, the assessment and
catalog query use that metric's default from the selected workload preset,
then the purpose profile when no preset supplies that metric. Explicit numeric
answers override only their corresponding value.
`upgrade_planning` and `other` intentionally have no default profile. Profile
values are visible in the report with their source; they should not be
presented as requirements from a particular app or as proven bottleneck
thresholds.

| Profile | RAM | Dedicated VRAM | Physical CPU cores | Free workspace |
| --- | ---: | ---: | ---: | ---: |
| General use | 16 GiB | — | 4 | 30 GiB |
| Gaming | 16 GiB | 8 GiB | 6 | 100 GiB |
| Video editing | 32 GiB | 8 GiB | 8 | 200 GiB |
| Rendering | 32 GiB | 8 GiB | 8 | 200 GiB |
| Local AI | 32 GiB | 12 GiB | 6 | 100 GiB |

These are deliberately broad v1 planning assumptions. Gaming is a generic
1080p planning baseline without an FPS promise; editing and rendering depend
on the app, codec, scene, and CPU/GPU mode; local AI assumes small quantized
model experimentation and varies substantially by model and context length.
No CPU base-clock default is invented. The report shows per-metric target
attainment (observed capacity divided by its floor, capped at 100%) to make
shortfalls easy to read. These percentages are not component performance
scores, are not averaged into an overall score, and do not identify a
bottleneck.

The report also groups those values as separate CPU/GPU/RAM/storage
profile-fit scores. Each score uses only its own measured profile feature:
physical CPU core count, selected-adapter dedicated VRAM, installed RAM
capacity, or best-case free workspace on one volume. A score of 100 means
"meets this profile floor", not "100% performance". Unknown readings remain
unknown and do not trigger an upgrade suggestion. CPU architecture/sustained
performance, GPU compute/raster speed, RAM bandwidth, and storage I/O speed
are not scored because the client lacks comparable measurements for them.

The catalog also supplies these candidate features for context, not as hidden
performance scores:

| Component | Compared profile feature | Other reported catalog features |
| --- | --- | --- |
| CPU | Core count; optional user-supplied performance-core base clock | Threads, boost clock, socket, TDP |
| GPU | Dedicated VRAM capacity | Chipset, memory type, board length, interface, TDP |
| RAM | Kit capacity | Module count, module capacity, memory type, form factor, speed |
| Storage | Drive capacity as a lower-bound match for free-workspace floor | Drive type, form factor, interface, NVMe indicator |

The scores do not combine these unlike features into a single component
performance score. Candidate options are selected only after a known installed
shortfall, and are the one or two closest items that pass the profile/user
floors. They are capacity/specification options, not verified compatible
upgrades. The API has no reliable current prices, and laptop or desktop
compatibility checks are not available from the current collector/catalog, so
cost, affordability, sustainability, and physical upgradeability remain
unknown.

## Run on Windows

Requires Python 3.10 or newer.

For the guided collection-and-comparison flow, double-click
`SysGap.bat` in this folder. It runs the questionnaire and local hardware
assessment, then checks eligible CPU, GPU, RAM, and storage gaps against the
configured SysGap API. After comparison, the existing upload-consent prompt
lets you submit the combined report to the backend. Declining keeps the local
reports only. No benchmark, stress test, or browser-based report is used. The
optional 10-second ambient snapshot is off by default and starts no workload.

The same workflow is available through the structured CLI entry point:

```sh
python cli.py run
python cli.py run --sample-seconds 10
python cli.py run --no-color
python cli.py run --verbose
```

`diagnosis.py` remains available as a compatibility entry point. The Windows
batch launcher and the POSIX `run.sh` launcher invoke `cli.py run`.

The live terminal view is intentionally concise: it shows the current phase,
short prompts, a small result summary, and report paths. Rich formatting is
used when supported, while `--no-color` produces plain output for logs and
redirected terminals. Use `--verbose` when you want the technical collection
notes and profile assumptions during the run. The saved JSON report always
retains the complete technical data; the saved text report is a shorter
human-readable summary.

On first launch, the batch file creates an isolated `.venv` in this folder and
installs the packages listed in `requirements.txt`; internet access is needed
for this setup. Later launches reuse that environment. If requirements change,
run `.venv\Scripts\python.exe -m pip install -r requirements.txt` from this
folder.

Reports are saved as one final JSON and one readable text file under
`reports/` after the guided workflow succeeds. If catalog lookup or upload
fails, the collection-only pair is retained so the user can recover locally.
The final JSON stores all per-component catalog lookups for local traceability,
but the readable report and `recommendations` section show only the selected
categories. Before upload, components with known numeric profile-fit scores
and passing catalog candidates are ranked by their shortfall from 100; only
the top two component categories are included in the backend payload. Each
selected category includes at most two candidate models. Unknown scores,
scores already at 100, and categories with no passing candidates are not
selected. The local report records the selected categories and their score
gaps; the all-component lookup data is not sent to the backend.
Uploads are minimized by default. The backend receives coarse hardware
capacities, structured preset context, effective requirement floors, compact
findings, and the selected shortlist. Device names, mount paths, raw
free-form requirement text, ambient samples, and full lookup history are
excluded. Pass `--share-details` with `--upload` only when you explicitly
want detailed hardware and questionnaire data included.

```powershell
python compare_and_submit.py --report .\reports\<assessment-file>.json `
  --components cpu gpu ram storage --upload --share-details
```
If the catalog API is unavailable, the local assessment remains available;
correct the network/API setting and rerun comparison with the saved JSON.
Each new assessment also includes a stable `report_id`, `client_version`,
collection provider, and collection capability map.

Install dependencies before first use:

```powershell
cd client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

To run collection alone, use `python collector.py`. To compare an existing
assessment manually, use `python compare_and_submit.py --report
.\reports\<assessment-file>.json --components cpu gpu ram storage`.

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

## Run on Linux or macOS

Linux and macOS use the same Python workflow and local report format. From a
terminal:

```sh
cd client
./run.sh
```

The launcher creates `client/.venv`, installs the platform-appropriate
requirements, and invokes the same guided workflow as `SysGap.bat`. The
platform-neutral inventory is intentionally conservative; detailed
platform-specific device data will be added through providers only when it can
be collected reliably.

The client performs no network operation during collection. Catalog lookup and
report upload remain separate, explicit opt-in actions.

Upload safety controls include HTTPS enforcement (except loopback development),
redirect blocking, rejection of embedded URL credentials, a 2 MiB request
limit, and a 1 MiB response limit. Local-only report metadata and complete
catalog lookup history are not included in the backend upload payload.

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
selected component and effective floors (user-entered values where provided,
otherwise selected purpose-profile defaults).
It does not send the hardware inventory to run catalog queries. It requests at
most 100 rows per API page, follows additional pages where needed, then returns
at most two candidates closest to the effective numeric floors. Candidates are
queried only for components with a detected shortfall against a known floor.
For multiple CPU floors or component capacities, closeness is ordered by the
sum of relative excess over each applicable floor. This is only a "closest
passing specs" ordering—not performance, price, value, or compatibility
ranking. The catalog has no reliable current prices, so affordability is
explicitly unavailable; the client does not call candidates cost-effective.

RAM, VRAM, and storage requirements are entered in GiB and converted to decimal
GB for the OpenDB-style catalog fields. The API does not publish units for
every capacity field, so this assumes those catalog fields use decimal GB;
verify candidates near a threshold against manufacturer specifications. When
detected RAM, selected-workload GPU VRAM, or free space on at least one volume
already meets the corresponding effective floor, no capacity-upgrade shortlist
is queried for that component. For multiple GPUs, the report only compares VRAM
when the questionnaire identifies one matching adapter; otherwise the
installed-GPU comparison is unknown. A candidate match says only that its
catalog fields meet the effective floors. It is not a diagnosis or proof of an
upgrade need.

The questionnaire asks for optional minimum CPU physical cores and CPU base
clock so those user values can override or extend a selected profile's core
floor. It never derives extra floors from a symptom. The assessment compares
physical core count when detected; Windows' reported maximum clock is not
substituted for the catalog's performance-core base clock, so that comparison
remains unknown. Catalog CPU candidates meeting the supplied floors do not
establish relative CPU performance.

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

`--components` defaults to all five categories. A component without an effective
positive floor is marked `not_ranked` without querying; a component whose
installed comparison is unknown does not receive upgrade suggestions. Motherboard
queries are currently withheld because no explicit selection criteria or
reliable compatibility data exists. Desktop, laptop, and unknown-form-factor
systems can all receive specification matches, but compatibility always
remains unknown. For laptops especially, the matching parts may be soldered,
non-upgradeable, or specific to the exact model; verify replaceability and
supported parts in the manufacturer's service manual before acting. RAM and
storage matches are capacity-based only; GPU and CPU matching also does not
establish relative performance or upgrade value. `--limit` can reduce the
maximum two candidate options per component to one.

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

The engine compares minimum RAM, dedicated VRAM, free storage, and CPU
physical-core requirements entered by the user or provided by the selected
purpose profile. Findings are based on detected capacities/core counts and
clearly labeled floors. CPU base-clock comparison remains unknown unless a
comparable measurement is available. The questionnaire
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

The test suite also covers provider selection, report persistence, CLI
delegation, upload payload boundaries, and local-only data exclusion.
