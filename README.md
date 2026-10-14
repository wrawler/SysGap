<div align="center">
  <img src="assets/logo.png" alt="SysGap logo" width="300">
</div>

<p align="center">
  Hardware diagnostics and upgrade guidance based on observable system facts.
</p>

<p align="center">
  <a href="https://sysgap.wrawler.online"><img src="https://img.shields.io/website?url=https%3A%2F%2Fsysgap.wrawler.online&label=live%20site" alt="Live site status"></a>
  <a href="client/README.md"><img src="https://img.shields.io/badge/client-documentation-5b8def" alt="Client documentation"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/wrawler/PriceRig" alt="License"></a>
</p>

## Overview

SysGap is a telemetry-driven PC diagnostic engine. A lightweight Windows
client collects a one-time hardware inventory, the API evaluates the supplied
report, and the catalog API returns relevant component records and upgrade
candidates.

SysGap intentionally avoids claims it cannot support. It does not run
benchmarks or stress tests, invent telemetry, or treat a capacity match as
proof of application performance. Unknown and unassessed values remain
explicitly unknown.

## What is included

- A Windows hardware inventory and assessment client.
- A FastAPI backend for reports, catalog queries, and candidate selection.
- A generated catalog for CPU, GPU, RAM, motherboard, and storage.
- A responsive static landing page and catalog browser.
- Light and dark themes with a small dependency-free frontend.
- A downloadable client archive at
  `server/web/downloads/sysgap-client.zip`.
- Azure deployment infrastructure using Terraform.
- Azure Static Web Apps for the frontend.
- An Azure Container App with scale-to-zero for the API.

## Production site

- Landing page: <https://sysgap.wrawler.online>
- Catalog: <https://sysgap.wrawler.online/catalog>
- Azure fallback hostname:
  <https://orange-sea-02f787400.5.azurestaticapps.net>
- API health endpoint:
  <https://sysgap-api.greenisland-25c48125.eastasia.azurecontainerapps.io/healthz>

The public frontend is served by Azure Static Web Apps. The API runs separately
in an Azure Container App. The frontend's API origin is configured in
`server/web/config.js` during deployment.

## Architecture

```text
Browser
  |
  +-- Azure Static Web Apps
  |     +-- Landing page
  |     +-- Catalog browser
  |     +-- Client ZIP download
  |
  +-- Azure Container App
        +-- FastAPI API
        +-- Scale-to-zero compute
        +-- Catalog query service
        +-- Report storage integration
```

Local development uses Docker Compose:

```text
Nginx :8080
  +-- Static frontend
  +-- /api/ proxy
        |
        +-- FastAPI :8000
```

## Repository layout

```text
.
├── assets/                 Branding assets
├── client/                 Cross-platform inventory and assessment client
├── docs/                   Project and deployment documentation
├── infra/terraform/        Azure infrastructure definitions
├── server/backend/         FastAPI application and catalog artifacts
├── server/nginx/           Local Nginx configuration
├── server/web/             Static landing page and catalog
└── .github/workflows/      CI and deployment workflows
```

For the complete chronological implementation record, see
[`docs/PROJECT-IMPLEMENTATION.md`](docs/PROJECT-IMPLEMENTATION.md).

## Run the API and website locally

From the repository root:

```bash
cd server
docker compose up --build
```

Open:

- <http://localhost:8080/> for the landing page.
- <http://localhost:8080/catalog> for the catalog.
- <http://localhost:8080/healthz> for the health check.
- <http://localhost:8000/docs> for the FastAPI documentation.

To use another host port:

```bash
WEB_PORT=9090 docker compose up --build
```

The local API is also exposed directly at <http://localhost:8000>.

## Run the client

The client requires Python 3.10 or newer. Windows has detailed WMI inventory;
Linux and macOS use the conservative common inventory provider, with
unsupported fields reported as unknown.

```powershell
cd client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python collector.py
```

On Linux or macOS, use the launcher:

```bash
cd client
./run.sh
```

The structured CLI entry point is also available on every platform:

```bash
python cli.py run
```

The client collects hardware inventory and creates a local report. Guided runs
use curated workload presets instead of free-form application or model names.
Upload is disabled unless explicitly requested.

Use `python cli.py run --no-color` for plain log-friendly output or
`python cli.py run --verbose` for additional collection details. The terminal
stays concise; the JSON report retains the complete technical result and the
text report contains a shorter readable summary.

Client uploads enforce HTTPS (except loopback development), block redirects,
bound request and response sizes, and minimize telemetry by default. They send
coarse capacities and compact findings rather than device identity, paths,
raw questionnaire text, ambient samples, or lookup history. Use
`--share-details` with `--upload` only for explicit advanced sharing.

To upload to an API:

```powershell
$env:SYSGAP_REPORT_API_URL = "https://your-api-host/api/v1/reports"
python collector.py --upload
```

The client asks for upload consent and requires HTTPS except for localhost
development. See [`client/README.md`](client/README.md) for the assessment
methodology, supported options, and limitations.

## Catalog generation

The raw `open-db` directory is intentionally ignored by Git. Generate the
runtime catalog from a local copy of that dataset:

```bash
cd server/backend
PYTHONPATH=. python -m db.catalog_pipeline \
  --source ../../open-db \
  --output catalog/catalog.json \
  --manifest catalog/manifest.json
```

The reducer:

- Fingerprints capability and specification fields.
- Excludes vendor, product name, part number, and retailer identifiers from
  deduplication.
- Selects representatives deterministically.
- Prefers useful capacity and performance values.
- Retains between 150 and 200 records per component type.
- Defaults to 200 records per type.

The generated artifacts are:

- `server/backend/catalog/catalog.json`
- `server/backend/catalog/manifest.json`

The manifest records source counts, unique specifications, retained records,
and duplicates for each category.

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/healthz` | Liveness check |
| `GET` | `/readyz` | Catalog readiness check |
| `GET` | `/api/v1/catalog` | Catalog counts and queryable fields |
| `GET` | `/api/v1/catalog/{component}` | Paginated component listing |
| `POST` | `/api/v1/catalog/query` | Filtered, sorted, projected catalog query |
| `GET` | `/api/v1/catalog/candidates` | Compatibility-oriented candidates |
| `POST` | `/api/v1/reports` | Store an assessment report |
| `GET` | `/api/v1/reports/{report_id}` | Retrieve a report |

Example catalog query:

```json
{
  "component": "gpu",
  "filters": [
    {"field": "memory", "min": 8},
    {"field": "tdp", "max": 250},
    {"field": "interface", "eq": "PCIe x16"}
  ],
  "sort": {"field": "memory", "direction": "desc"},
  "fields": ["opendb_id", "memory", "memory_type", "chipset", "tdp"],
  "offset": 0,
  "limit": 25
}
```

Supported filter operators are `eq`, `min`, `max`, and `in`. Queryable fields
are component-specific and are returned by `GET /api/v1/catalog`.

## Frontend deployment

The frontend is plain HTML, CSS, and JavaScript under `server/web`; no build
step or frontend framework is required.

Regenerate the public client download after changing files under `client/`:

```bash
rm server/web/downloads/sysgap-client.zip
zip -qr server/web/downloads/sysgap-client.zip client \
  -x 'client/.venv/*' \
     'client/__pycache__/*' \
     'client/tests/__pycache__/*' \
     'client/.pytest_cache/*'
```

Verify the archive:

```bash
unzip -tq server/web/downloads/sysgap-client.zip
```

Deploy manually to the production Static Web App:

```bash
swa deploy ./server/web \
  --env production \
  --deployment-token "$(terraform -chdir=infra/terraform output -raw frontend_deployment_token)"
```

The `--env production` flag is required when deploying to the main
`azurestaticapps.net` hostname. Without it, the CLI defaults to a preview
environment.

## Azure infrastructure

Terraform configuration is under `infra/terraform`.

Create a local variables file:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Set the registry, image, frontend API origin, and allowed frontend origins in
the local file. A production configuration has this shape:

```hcl
location                  = "eastasia"
project_name              = "sysgap"
container_image           = "YOUR_REGISTRY.azurecr.io/sysgap-api:TAG"
container_registry_server = "YOUR_REGISTRY.azurecr.io"
container_registry_username = "YOUR_ACR_USERNAME"
container_registry_password = "YOUR_ACR_PASSWORD"

frontend_api_url         = "https://your-api-host.azurecontainerapps.io"
allowed_frontend_origins = "https://your-static-app.azurestaticapps.net,https://your-domain.example"
frontend_custom_domain  = "your-domain.example"
```

Run:

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

Useful outputs:

```bash
terraform output -raw api_url
terraform output -raw frontend_url
terraform output -raw frontend_deployment_token
```

Azure subscriptions can restrict Static Web App regions. The default
`frontend_location` is `eastasia`, but use a region permitted by your
subscription if Azure returns `RequestDisallowedByAzure`.

## Custom domains

The Terraform variable for a custom hostname is:

```hcl
frontend_custom_domain = "www.example.com"
```

For a subdomain:

1. Set `frontend_custom_domain` in local `terraform.tfvars`.
2. Add the custom hostname to `allowed_frontend_origins`.
3. Run `terraform apply`.
4. Add the TXT validation record provided by Azure.
5. Add the CNAME provided by Azure or point the subdomain to the Static Web
   App hostname.
6. Wait for DNS propagation and Azure validation.
7. Test the custom HTTPS hostname.

Keep the Azure fallback hostname in `allowed_frontend_origins` while migrating
so both addresses continue to work.

## GitHub Actions deployment

The manual deployment workflow is:

[`/.github/workflows/deploy.yml`](.github/workflows/deploy.yml)

It builds and pushes the API image, applies Terraform, injects the frontend
API URL, and deploys `server/web` to Azure Static Web Apps.

Configure these repository Actions secrets before using the workflow:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
ACR_LOGIN_SERVER
ACR_USERNAME
ACR_PASSWORD
AZURE_STATIC_WEB_APPS_API_TOKEN
FRONTEND_API_URL
ALLOWED_FRONTEND_ORIGINS
FRONTEND_CUSTOM_DOMAIN
```

Azure login uses GitHub OIDC. Grant the identity only the permissions needed
to deploy the resource group and push to the container registry.

## Storage and runtime configuration

For local development, Azure storage variables can be omitted. The local
Compose setup stores reports in a named volume.

For Azure storage, the API supports:

- `AZURE_STORAGE_ACCOUNT_URL`
- `AZURE_TABLE_ACCOUNT_URL`
- `AZURE_BLOB_CONTAINER`
- `AZURE_TABLE_NAME`

The API CORS allowlist is configured with:

```text
SYSGAP_ALLOWED_ORIGINS
```

It must contain exact origins separated by commas, without trailing slashes.
For example:

```text
https://your-static-app.azurestaticapps.net,https://www.example.com
```

## Testing and validation

Backend tests:

```bash
PYTHONPATH=server/backend .venv/bin/python -m pytest server/backend/tests -q
```

Client tests:

```bash
cd client
python -m pytest tests -q
```

Python compilation:

```bash
PYTHONPATH=server/backend .venv/bin/python -m compileall -q server/backend/db server/backend/shared
```

Terraform validation:

```bash
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
```

Static Web Apps configuration:

```bash
jq empty server/web/staticwebapp.config.json
```

## License

See [`LICENSE`](LICENSE).
