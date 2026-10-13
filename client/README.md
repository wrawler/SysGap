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

## Optional report upload

Upload is disabled unless requested. Configure the **full** report endpoint
with `PRICERIG_REPORT_API_URL` or `--api-url`, then run:

```powershell
$env:PRICERIG_REPORT_API_URL = "https://your-host/api/v1/reports"
python collector.py --upload
```

The client displays an upload consent prompt. HTTPS is required except for
localhost development. It sends a versioned JSON body with `task`, `hardware`,
and `telemetry` fields to match the current draft API shape; `telemetry.kind`
is `inventory_assessment`, not live workload telemetry. Confirm the endpoint,
accepted schema, response fields, and report URL behavior with the backend
owner before using a deployed service.

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
