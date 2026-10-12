resource "google_compute_address" "bottleneck_ip" {
  name = "bottleneck-static-ip"
}

resource "google_compute_firewall" "web_firewall" {
  name    = "allow-web-traffic"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22", "80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["bottleneck-server"]
}