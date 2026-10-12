resource "google_compute_instance" "app_server" {
  name         = "bottleneck-node"
  machine_type = "e2-micro"
  tags         = ["bottleneck-server"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 30
      type  = "pd-standard"
    }
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.bottleneck_ip.address
    }
  }
}