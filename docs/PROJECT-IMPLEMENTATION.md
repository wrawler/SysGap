# SysGap Project Implementation Record

This document records the work completed to turn SysGap into a publicly
accessible diagnostic landing site with a browsable hardware catalog, Azure
hosting, and the custom domain `sysgap.wrawler.online`.

It is intentionally free of credentials, registry passwords, Terraform state,
deployment tokens, and other secrets.

## URL and configuration safety

The HTTPS URLs in this document are public service endpoints, not credentials.
It is safe for a public project record to mention:

- The public landing-page hostname.
- The public Azure Static Web Apps fallback hostname.
- The public API hostname.
- Local development URLs.
- Public API route paths.

These values can still be changed later, so treat them as deployment
configuration rather than immutable project constants. The API hostname must
not be confused with an API key: it identifies a public HTTP service and does
not grant access by itself.

The following must never be copied into this document or committed:

- Static Web Apps deployment tokens.
- Azure service-principal credentials.
- Azure Container Registry passwords.
- Terraform state files.
- Local `terraform.tfvars` values containing credentials.
- Storage connection strings, SAS tokens, or private keys.

## 1. Starting point

SysGap already contained:

- A FastAPI backend under `server/backend`.
- A generated hardware catalog under `server/backend/catalog`.
- A Windows client under `client`.
- Azure Terraform infrastructure under `infra/terraform`.
- Docker Compose and Nginx configuration under `server`.
- API tests covering catalog metadata, catalog queries, candidates, and
  validation.

The original backend exposed:

- `GET /healthz`
- `GET /readyz`
- `GET /api/v1/catalog`
- `GET /api/v1/catalog/{component}`
- `POST /api/v1/catalog/query`
- `GET /api/v1/catalog/candidates`
- `POST /api/v1/reports`
- `GET /api/v1/reports/{report_id}`

The catalog contained up to 200 retained records for each of:

- CPU
- GPU
- RAM
- Motherboard
- Storage

## 2. Static frontend implementation

A dependency-free frontend was added under `server/web`. It uses plain HTML,
CSS, and JavaScript rather than a frontend framework or bundler to keep the
runtime and memory footprint small.

### Landing page

The landing page was added at:

- `server/web/index.html`

It includes:

- SysGap product explanation.
- Primary client download call-to-action.
- Link to the hardware catalog.
- A three-part explanation of the product workflow.
- Responsive layout for desktop and mobile screens.
- Restrained color palette and typography.
- Light/dark mode toggle.
- Persisted theme preference using `localStorage`.
- System theme fallback using `prefers-color-scheme`.

### Shared styling

The visual system was added at:

- `server/web/styles.css`

The styles provide:

- CSS custom properties for light and dark themes.
- Responsive grid layouts.
- Accessible focusable buttons and links.
- Responsive mobile breakpoints.
- Card, tab, pagination, status, and callout components.
- No external CSS framework.

### Shared JavaScript

Frontend behavior was added at:

- `server/web/app.js`

It handles:

- Theme switching.
- Catalog component tabs.
- API requests.
- Loading, empty, and unavailable states.
- Catalog cards.
- Pagination.
- HTML escaping before inserting catalog values into cards.
- Component-aware title fallback logic.

## 3. Client download package

The landing page download button points to:

- `server/web/downloads/sysgap-client.zip`

The archive contains the client application and excludes local environments,
Python caches, and test caches.

It can be regenerated with:

```bash
rm server/web/downloads/sysgap-client.zip
zip -qr server/web/downloads/sysgap-client.zip client \
  -x 'client/.venv/*' \
     'client/__pycache__/*' \
     'client/tests/__pycache__/*' \
     'client/.pytest_cache/*'
```

The archive is intentionally tracked because it is a public deliverable linked
from the landing page.

## 4. Catalog page

The catalog page was added at:

- `server/web/catalog.html`

The page provides tabs for:

- CPU
- GPU
- Memory
- Motherboard
- Storage

Each tab requests one page of records from the API. The page size is 12
records, reducing the amount of data transferred and rendered at once.

The catalog displays:

- Responsive cards.
- A component label.
- A meaningful product title.
- A small set of technical specifications.
- Pagination controls.
- Loading state.
- Empty state.
- API-unavailable state.

### Catalog title correction

The first card implementation searched only early flattened specification
fields. This caused titles such as:

- CPU core counts.
- Motherboard `DDR4` or `DDR5`.
- GPU numeric memory values.

Inspection of `server/backend/catalog/catalog.json` showed that descriptive
product names were retained under `metadata.name`, for example:

- `AMD Ryzen Threadripper PRO 9995WX`
- `NVIDIA RTX PRO 6000 Blackwell Workstation Edition 96GB GDDR7`
- `Supermicro Intel C612 MBD-X10DAX Dual-CPU LGA2011-3 DDR4 EATX`
- `Seagate Exos M 36TB 3.5" HDD 7200RPM SATA 6.0 Gb/s`

The card logic was changed to prioritize:

1. `metadata.name`
2. `name`
3. `model`
4. `product_name`
5. Component-specific descriptive fallback

Examples of fallback titles include:

- CPU: `96 cores / 192 threads`
- GPU: chipset, capacity, and memory type
- RAM: capacity, memory type, and speed
- Motherboard: chipset, memory type, and form factor
- Storage: capacity, storage type, and interface

## 5. Catalog routing and the initial 404 issue

The original clean `/catalog` route worked through Nginx but failed with
simple static servers because those servers looked for a physical directory or
file.

The route support was made explicit through:

- `server/web/staticwebapp.config.json`
- `server/nginx/default.conf`

The Static Web Apps configuration now rewrites:

```text
/catalog → /catalog.html
```

The Nginx configuration also handles `/catalog`.

An intermediate `server/web/catalog/index.html` file was initially added as a
directory entry point. It displayed a plain text redirect message briefly on
some hosts. The Static Web Apps rewrite was later changed to point directly to
`catalog.html`, removing the white/plain-text flash during navigation.

## 6. Runtime API configuration

The frontend and API are hosted separately in production, so the frontend
cannot assume the API is available at its own origin.

A small runtime configuration file was added:

- `server/web/config.js`

It contains:

```javascript
window.SYSGAP_API_BASE = "https://your-api-host";
```

Local development can use an empty value to keep same-origin behavior:

```javascript
window.SYSGAP_API_BASE = "";
```

Production deployments replace the value with the public Container App API
origin.

The catalog request is formed as:

```text
{SYSGAP_API_BASE}/api/v1/catalog/{component}
```

## 7. Nginx and Docker Compose integration

The Nginx service was updated to mount the frontend:

```yaml
- ./web:/usr/share/nginx/html:ro
```

Nginx continues to proxy:

```text
/api/ → backend:8000/api/
```

Static assets receive cache headers where appropriate. The local stack can be
started with:

```bash
cd server
docker compose up --build
```

The local site is then available at:

```text
http://localhost:8080/
http://localhost:8080/catalog
```

## 8. API CORS support

The FastAPI application was updated in:

- `server/backend/db/main.py`

It reads:

```text
SYSGAP_ALLOWED_ORIGINS
```

The value is a comma-separated list of exact browser origins. Example:

```text
https://orange-sea-02f787400.5.azurestaticapps.net,https://sysgap.wrawler.online
```

The API uses FastAPI/Starlette CORS middleware and allows the required `GET`
and `POST` methods without enabling wildcard origins.

The API must be rebuilt and redeployed whenever backend middleware changes.
Changing an environment variable alone is not a substitute for deploying a
backend image containing the required code.

## 9. Azure hosting architecture

The production architecture was chosen to minimize cost while preserving
static load performance:

```text
Browser
  │
  ├── Azure Static Web Apps Free tier
  │     ├── Landing page
  │     ├── Catalog page
  │     └── Client ZIP download
  │
  └── Azure Container App
        └── FastAPI API, scale-to-zero
```

Azure Static Web Apps provides edge delivery and caching for the static
frontend. The API remains on the existing scale-to-zero Container App.

Terraform resources were added for:

- Azure Static Web App.
- Optional Static Web App custom domain.
- Frontend/API URL variables.
- API allowed-origin configuration.
- Frontend URL output.
- Static Web App deployment token output.

Relevant files:

- `infra/terraform/compute.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/terraform.tfvars.example`

The Static Web App region had to be changed to a region accepted by the
subscription policy. The working configuration uses:

```hcl
frontend_location = "eastasia"
```

## 10. Manual Static Web Apps deployment

The frontend was deployed manually before GitHub Actions was configured.

The Static Web Apps CLI was used:

```bash
npm install -g @azure/static-web-apps-cli
```

The production deployment command is:

```bash
swa deploy ./server/web \
  --env production \
  --deployment-token "$(terraform -chdir=infra/terraform output -raw frontend_deployment_token)"
```

The `--env production` flag is important. Without it, the CLI defaults to a
preview environment, which does not update the main
`azurestaticapps.net` hostname.

The deployed Azure hostname is currently:

```text
https://orange-sea-02f787400.5.azurestaticapps.net
```

The custom domain is:

```text
https://sysgap.wrawler.online
```

## 11. GitHub Actions deployment support

The deployment workflow is:

- `.github/workflows/deploy.yml`

It is manually triggered with `workflow_dispatch`.

The workflow:

1. Logs into Azure using OIDC credentials.
2. Logs into Azure Container Registry.
3. Builds and pushes the backend image.
4. Runs Terraform.
5. Injects the frontend API origin.
6. Deploys `server/web` to Azure Static Web Apps.

Required GitHub Actions secrets:

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

For the current deployment, the important values are public configuration
values (not secrets):

```text
FRONTEND_API_URL=https://sysgap-api.greenisland-25c48125.eastasia.azurecontainerapps.io
ALLOWED_FRONTEND_ORIGINS=https://orange-sea-02f787400.5.azurestaticapps.net,https://sysgap.wrawler.online
FRONTEND_CUSTOM_DOMAIN=sysgap.wrawler.online
```

Do not place these secrets or registry passwords in tracked files.

## 12. Custom domain setup

The custom domain was configured as:

```hcl
frontend_custom_domain = "sysgap.wrawler.online"
```

The API allowlist was expanded to include both the default Azure hostname and
the custom hostname:

```hcl
allowed_frontend_origins = "https://orange-sea-02f787400.5.azurestaticapps.net,https://sysgap.wrawler.online"
```

The DNS process was:

1. Register the custom hostname with the Azure Static Web App.
2. Add the TXT validation record supplied by Azure.
3. Add the CNAME mapping the custom subdomain to the Azure Static Web App
   hostname.
4. Wait for DNS propagation and Azure validation.
5. Confirm managed HTTPS becomes available.
6. Add the custom hostname to the API CORS allowlist.
7. Redeploy/restart the backend so the new environment is active.

The exact DNS record names and values supplied by Azure take precedence over
generic examples. For a subdomain, Cloudflare commonly uses:

```text
Type: CNAME
Name: www-or-app
Target: <static-app-hostname>.azurestaticapps.net
Proxy: DNS only
```

The final working domain is:

```text
https://sysgap.wrawler.online
```

## 13. Troubleshooting performed

### Static Web Apps deployment appeared empty

Cause: the CLI deployed to `preview` while the production hostname was being
opened.

Fix:

```bash
swa deploy ./server/web --env production ...
```

### Catalog showed “temporarily unavailable”

The API itself was reachable and returned catalog data, but browser requests
were blocked when the custom origin was missing from CORS.

The API was tested with:

```bash
curl -sS -D - -o /dev/null \
  -H "Origin: https://sysgap.wrawler.online" \
  "$API_URL/api/v1/catalog/CPU?offset=0&limit=12"
```

The expected response includes:

```text
HTTP/2 200
access-control-allow-origin: https://sysgap.wrawler.online
```

### Container App revision restart failed

The Azure Container App used an Express environment, which does not support
custom revision suffixes and returned:

```text
ExpressEnvironmentFeatureNotSupported
```

The fix was to update the environment variable without
`--revision-suffix`, or deploy a new image through Terraform:

```bash
az containerapp update \
  --name sysgap-api \
  --resource-group sysgap-rg \
  --set-env-vars \
  'SYSGAP_ALLOWED_ORIGINS=https://orange-sea-02f787400.5.azurestaticapps.net,https://sysgap.wrawler.online'
```

### Catalog title quality

The API data was correct. The issue was frontend title selection, not the
source catalog. Prioritizing `metadata.name` corrected the display.

## 14. Validation completed

The following checks passed during implementation:

```bash
PYTHONPATH=server/backend .venv/bin/python -m pytest server/backend/tests -q
```

Result:

```text
5 passed
```

Additional checks:

- Python backend compilation passed.
- Terraform formatting passed for tracked Terraform files.
- Terraform validation passed.
- Static Web Apps configuration JSON parsed successfully.
- Client ZIP integrity test passed.
- Nginx configuration test passed.
- Local `/catalog` route returned successfully.
- API catalog endpoint returned `200`.
- API CORS behavior was verified for the Azure and custom frontend origins.
- Production Static Web Apps deployment completed successfully.

## 15. Secrets and repository safety

The following must remain untracked:

```text
infra/terraform/terraform.tfvars
infra/terraform/.terraform/
infra/terraform/*.tfstate
infra/terraform/*.tfstate.*
```

The repository `.gitignore` excludes these files.

Never commit:

- Azure client secrets.
- ACR passwords.
- Static Web Apps deployment tokens.
- Terraform state.
- Local `terraform.tfvars`.
- Personal access tokens.

The public API hostname in `server/web/config.js` is configuration, not a
credential. It is safe to expose in browser-delivered JavaScript, but it must
not be confused with an API key or deployment token.

## 16. Current operating model

For manual frontend deployment:

```bash
swa deploy ./server/web \
  --env production \
  --deployment-token "$(terraform -chdir=infra/terraform output -raw frontend_deployment_token)"
```

For infrastructure/API changes:

```bash
terraform -chdir=infra/terraform plan
terraform -chdir=infra/terraform apply
```

For API image changes:

1. Build a new backend image.
2. Push it to Azure Container Registry.
3. Update `container_image`.
4. Apply Terraform.
5. Verify the active API revision.
6. Test the API and CORS headers.

For frontend changes:

1. Run the frontend/static checks.
2. Deploy with `--env production`.
3. Verify `/`, `/catalog`, and the download URL.
4. Hard-refresh the browser if cached assets are suspected.

## 17. Useful URLs

Production frontend:

```text
https://sysgap.wrawler.online
```

Catalog:

```text
https://sysgap.wrawler.online/catalog
```

Azure Static Web Apps fallback hostname:

```text
https://orange-sea-02f787400.5.azurestaticapps.net
```

API:

```text
https://sysgap-api.greenisland-25c48125.eastasia.azurecontainerapps.io
```

Health check:

```text
https://sysgap-api.greenisland-25c48125.eastasia.azurecontainerapps.io/healthz
```
