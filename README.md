# PriceRig

PriceRig is a telemetry-driven PC diagnostic engine. The client sends a small
hardware/telemetry payload, the API evaluates it, and the catalog API returns
compatible upgrade candidates.

## Runtime architecture

- **API:** FastAPI/Uvicorn in an Azure Container App with scale-to-zero enabled.
- **Catalog:** A generated, read-only JSON artifact containing up to 200
  specification-unique records for each of CPU, GPU, RAM, motherboard, and
  storage.
- **Reports:** JSON payloads in private Azure Blob Storage, with Azure Table
  Storage metadata for inexpensive lookup.
- **Local development:** Docker Compose, with reports stored in a named volume.
- **Edge/client data:** The API accepts telemetry; it does not require the
  client to upload the full source catalog.

Azure free grants and quotas change over time. The Terraform configuration uses
small scale-to-zero resources and LRS storage, but usage and log retention
should still be monitored.

## Build the catalog

The raw `open-db` directory is intentionally ignored by Git. Generate the
runtime artifact from a local copy of that dataset:

```bash
cd server/backend
PYTHONPATH=. python -m db.catalog_pipeline \
  --source ../../open-db \
  --output catalog/catalog.json \
  --manifest catalog/manifest.json
```

The reducer fingerprints only capability/specification fields. Vendor, product
name, part number, and retailer identifiers do not create separate entries.
The retained representative is selected deterministically, preferring useful
capacity/performance and then a stable source ID. `--target` accepts 150–200
and defaults to 200.

## Run locally

```bash
cd server
docker compose up --build
```

The API is available directly at `http://localhost:8000`; the Nginx entry point
is `http://localhost:8080`. Check `http://localhost:8080/healthz` before
sending requests. Override the host-facing web port when needed:

```bash
WEB_PORT=9090 docker compose up --build
```

Endpoints:

- `GET /api/v1/catalog/candidates?component=gpu&limit=25`
- `GET /api/v1/catalog/candidates?component=cpu&max_tdp=150`
- `POST /api/v1/reports`
- `GET /api/v1/reports/{report_id}`

For local development, omit Azure storage variables. To use Azure directly,
set `AZURE_STORAGE_ACCOUNT_URL` with managed-identity credentials, or set
`AZURE_TABLE_ACCOUNT_URL` as well. A connection string can be used for a
controlled development environment.

## Deploy to Azure

1. Create an Azure Container Registry and configure GitHub OIDC/Azure login
   secrets used by `.github/workflows/deploy.yml`.
2. Copy `infra/terraform/terraform.tfvars.example` to
   `infra/terraform/terraform.tfvars` and set the image/registry values.
3. Run:

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

The `api_url` output is the public Container App URL. The manual GitHub
workflow performs the same image build and Terraform deployment using a commit
tag.

## Credentials and Terraform variables

There are two supported ways to authenticate. Do not put real credentials in
the repository, in `terraform.tfvars.example`, or in chat.

### Local Terraform deployment

Install the Azure CLI, then sign in and select the subscription that should
receive the resources:

```bash
az login
az account list --output table
az account set --subscription "<AZURE_SUBSCRIPTION_ID_OR_NAME>"
az account show --output table
```

Before creating the registry, register the Azure resource providers used by
this deployment. Registration is subscription-level and may require
**Contributor** or **Owner** permissions:

```bash
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.Storage

az provider show \
  --namespace Microsoft.ContainerRegistry \
  --query registrationState \
  --output tsv
```

Wait until the command prints `Registered`. If it prints `Registering`, check
again after a short delay:

```bash
az provider show \
  --namespace Microsoft.ContainerRegistry \
  --query registrationState \
  --output tsv
```

The `azurerm` provider uses this Azure CLI session locally, so no
`client_secret` needs to be written to a file.

Create your local variable file from the checked-in example:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and replace the placeholders:

```hcl
location                    = "eastus"
project_name                = "pricerig"
container_image             = "YOUR_REGISTRY.azurecr.io/pricerig-api:latest"
container_registry_server   = "YOUR_REGISTRY.azurecr.io"
container_registry_username = "YOUR_ACR_USERNAME"
container_registry_password = "YOUR_ACR_PASSWORD"
```

`terraform.tfvars` is ignored by Git. The registry values can be obtained
after creating an Azure Container Registry:

```bash
az acr create \
  --resource-group "<EXISTING_OR_BOOTSTRAP_RESOURCE_GROUP>" \
  --name "<REGISTRY_NAME>" \
  --sku Basic

az acr show --name "<REGISTRY_NAME>" \
  --query loginServer --output tsv
az acr credential show --name "<REGISTRY_NAME>" \
  --query "{username:username,password:passwords[0].value}" \
  --output json
```

Use the returned login server, username, and password in the tfvars file.
Avoid printing the password in shared terminal logs. ACR admin credentials
are convenient for the initial setup but are long-lived; use a dedicated
short-lived or federated publishing identity for production CI.

### Push the first API image locally

For a first deployment using local Terraform, push the image before running
`terraform apply`. Container Apps needs to pull the image when it creates the
first revision.

From the repository root, with Docker running:

```bash
RESOURCE_GROUP="rg-pricerig"
LOCATION="eastasia"
ACR_NAME="sysgap"

az account show --output table
az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
  --query loginServer --output tsv

LOGIN_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query loginServer \
  --output tsv)

az acr login --name "$ACR_NAME"

docker build \
  --tag "$LOGIN_SERVER/pricerig-api:latest" \
  ./server/backend

docker push "$LOGIN_SERVER/pricerig-api:latest"
```

The build context must be `./server/backend`; that directory contains the
Dockerfile and the generated catalog artifact. Verify the image exists:

```bash
az acr repository show \
  --name "$ACR_NAME" \
  --repository pricerig-api \
  --output table
```

If `az acr login` fails, refresh `az login`, confirm the active subscription,
and check that the ACR name is correct. If Docker reports that the daemon is
unavailable, start Docker Desktop or the Docker service before retrying.

Make the local Terraform variables match the image you pushed:

```hcl
location                    = "eastasia"
project_name                = "sysgap"
container_image             = "sysgap.azurecr.io/pricerig-api:latest"
container_registry_server   = "sysgap.azurecr.io"
container_registry_username = "YOUR_ACR_USERNAME"
container_registry_password = "YOUR_ACR_PASSWORD"
```

Then deploy:

```bash
cd infra/terraform
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
terraform output api_url
```

The `container_image` registry hostname and tag must match the image pushed to
ACR. For a different registry or tag, update both the Docker tag/push command
and `container_image`.

This manual image push is only needed for local Terraform deployment. The
GitHub Actions workflow builds and pushes a commit-tagged image before it runs
Terraform.

Run a local deployment with:

```bash
terraform init
terraform plan
terraform apply
```

Terraform state contains resource details and must not be committed. Back up
it using a protected remote state backend before collaborating or running
deployments from CI.

### GitHub Actions deployment

The workflow at
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) does not read
your local `terraform.tfvars`. Add these **Actions secrets** in the GitHub
repository under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | Application/client ID of the Azure Entra workload identity |
| `AZURE_TENANT_ID` | Azure Entra tenant/directory ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `ACR_LOGIN_SERVER` | Registry server, such as `myregistry.azurecr.io` |
| `ACR_USERNAME` | ACR publishing username |
| `ACR_PASSWORD` | ACR publishing password/token |

The Azure login step uses GitHub OIDC. Configure an Entra application or
service principal with a federated credential whose subject matches the
repository and workflow branch, then grant it the smallest practical scope:

```bash
az ad app create --display-name "pricerig-github-actions"
az ad sp create --id "<APPLICATION_CLIENT_ID>"
```

In the Azure Portal, add a **Federated credential** to that application with:

- Organization/repository: your GitHub repository
- Entity type: branch
- Branch: `main` (or the branch used for deployment)
- Audience: `api://AzureADTokenExchange`

Grant the identity `Contributor` on the deployment resource group or
subscription, and `AcrPush` on the container registry. Keep the scope at the
resource-group level where possible. The workflow then builds an image tagged
with the commit SHA and passes its values to Terraform through `TF_VAR_*`
environment variables.

### Preflight checklist

Before deploying, verify:

1. `az account show` points to the intended subscription.
2. `Microsoft.ContainerRegistry` is `Registered`.
3. The ACR exists and its login server is correct.
4. `terraform.tfvars` contains no `replace-me` values.
5. `terraform fmt -check` and `terraform validate` pass.
6. GitHub Actions has all six secrets listed above if using CI.
7. The selected Azure identity can create Container Apps and assign storage
   roles.

## Validation

```bash
cd server/backend
PYTHONPATH=. pytest -q
python -m compileall -q db shared
```
