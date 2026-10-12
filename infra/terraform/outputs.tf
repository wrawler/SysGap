output "server_public_ip" {
  description = "Public IP of the bottleneck instance to configure in Ansible"
  value       = google_compute_address.bottleneck_ip.address
}