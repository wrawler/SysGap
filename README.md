<div align="center">
  <img src="assets/logo.png" alt="Logmill Logo" width="300"/>
  
  **Telemetry-driven diagnostic engine for prescribing compatible PC hardware upgrades.**

</div>

A hardware suitability and upgrade-planning project. Its client-side v1 inventories hardware and compares detectable capacity against workload requirements supplied by the user. It does not claim to identify a live performance bottleneck without observing the application's workload.

Unlike generic bottleneck calculators that rely on crude percentage heuristics, the client reports explainable capacity comparisons, keeps unknown data explicit, and avoids universal CPU/GPU ratios.

## Architecture & Core Features

* **Client-side assessment (v1):** The Python client gathers Windows hardware inventory, asks purpose-specific questions, and writes local JSON/text reports. An optional short passive sample observes current activity; it does not start a workload or establish application performance.

* **Explainable decision rules:** Explicit capacity comparisons are made only where the user provides a requirement. Unknown inputs remain unknown; the client does not calculate a universal CPU/GPU ratio or infer a bottleneck from synthetic values.

* **Planned: upgrade recommendations:** Catalog-backed compatibility and candidate ranking are future integration work. The client v1 does not recommend specific upgrades or claim physical/electrical compatibility.

* **Infrastructure as Code (IaC):** Fully reproducible cloud environment targeting the GCP Always-Free tier (`e2-micro`), provisioned via **Terraform** and configured via **Ansible**.

* **Planned: report dashboard:** A static report page and persistent report API are not part of the current client-side branch.

## Technology Stack

* **Edge Client:** Python (`psutil`, Windows WMI, optional `pynvml`)
* **Backend API:** FastAPI, Uvicorn, Python 3.11
* **Database:** SQLite (WAL Mode)
* **Frontend:** HTML5, Tailwind CSS
* **Web Server:** Nginx Alpine
* **DevOps & Cloud:** Google Cloud Platform (GCP), Terraform, Ansible, Docker

## Repository Structure

```text
bottleneck-remove/
├── infra/                         # Cloud & System Orchestration
│   ├── terraform/                 # GCP VM, Static IP, Firewalls
│   └── ansible/                   # OS config, Swapfile, Docker setup
├── server/                        # Cloud Application Stack
│   ├── docker-compose.yml         # Container orchestration
│   ├── nginx/                     # Reverse proxy & static frontend
│   ├── backend/                   # FastAPI application & SQLite DB
│   └── shared/                    # Two-pass rule engine (rules_engine.py)
└── client/                        # Desktop assessment utility
    ├── collector.py               # Questionnaire, inventory, report and optional API upload
    ├── hardware_inventory.py
    ├── decision_engine.py
    ├── questionnaire.py
    └── tests/
```

## Run the Client Locally (Windows)

```powershell
cd client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python collector.py
```

Reports are saved locally under `client/reports/`. To test the complete client
and upload flow without depending on the unfinished backend, follow the
localhost mock API instructions in [client/README.md](client/README.md).
The production API contract, persistent report storage, and dashboard remain
integration work.

Run the decision/API unit tests with:

```powershell
cd client
python -m unittest discover -s tests -v
```

## Infrastructure & Cloud Deployment (GCP)

This project is configured to deploy to Google Cloud's **Always Free** tier (`us-central1`, `e2-micro`, 30GB Standard Disk). 

**1. Provision Infrastructure with Terraform:**

```bash
cd infra/terraform
# Define your GCP Project ID in terraform.tfvars prior to execution
terraform init
terraform apply
```

*Note the `server_public_ip` output generated upon completion.*

**2. Configure Host & Deploy with Ansible:**

```bash
cd ../ansible
# Append the generated IP to inventory.ini
ansible-playbook -i inventory.ini playbook.yml
```

Ansible will automatically authenticate, allocate a 2GB swap file to protect the 1GB RAM VM, install the Docker runtime, and initialize the `docker-compose.yml` stack.

## License

Distributed under the MIT License. See `LICENSE` for more information.
