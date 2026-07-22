output "instance_public_ip" {
  description = "Public IPv4 address of the DQP scanner VM."
  value       = oci_core_instance.scanner.public_ip
}

output "post_boot_command" {
  description = "Command to run after cloud-init finishes."
  value       = "sudo bash /opt/dqp-scanner/deploy/oci/configure.sh"
}
