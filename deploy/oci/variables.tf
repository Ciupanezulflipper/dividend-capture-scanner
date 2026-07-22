variable "tenancy_ocid" {
  description = "OCI tenancy OCID used to discover availability domains and platform images."
  type        = string
}

variable "region" {
  description = "OCI home region, for example eu-frankfurt-1."
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment OCID in which to create the scanner resources."
  type        = string
}

variable "ssh_public_key" {
  description = "OpenSSH public key installed for the ubuntu user."
  type        = string
  sensitive   = true
}

variable "ssh_allowed_cidr" {
  description = "Single trusted IPv4 CIDR allowed to SSH, for example 203.0.113.10/32."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_allowed_cidr, 0)) && var.ssh_allowed_cidr != "0.0.0.0/0"
    error_message = "Use a valid restricted IPv4 CIDR; 0.0.0.0/0 is not allowed."
  }
}

variable "availability_domain_index" {
  description = "Zero-based availability-domain index. Change this if Always Free capacity is unavailable."
  type        = number
  default     = 0
}

variable "instance_display_name" {
  description = "Display name for the compute instance."
  type        = string
  default     = "dqp-scanner"
}
