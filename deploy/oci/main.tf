provider "oci" {
  region = var.region
}

data "oci_identity_availability_domains" "available" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.tenancy_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_vcn" "dqp" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.42.0.0/16"]
  display_name   = "dqp-vcn"
  dns_label      = "dqpvcn"
}

resource "oci_core_internet_gateway" "dqp" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.dqp.id
  display_name   = "dqp-internet-gateway"
  enabled        = true
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.dqp.id
  display_name   = "dqp-public-routes"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.dqp.id
  }
}

resource "oci_core_security_list" "scanner" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.dqp.id
  display_name   = "dqp-scanner-security-list"

  ingress_security_rules {
    protocol = "6"
    source   = var.ssh_allowed_cidr

    tcp_options {
      min = 22
      max = 22
    }
  }

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.dqp.id
  cidr_block                 = "10.42.1.0/24"
  display_name               = "dqp-public-subnet"
  dns_label                  = "dqppublic"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.scanner.id]
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_instance" "scanner" {
  availability_domain = data.oci_identity_availability_domains.available.availability_domains[var.availability_domain_index].name
  compartment_id      = var.compartment_ocid
  display_name        = var.instance_display_name
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }

  create_vnic_details {
    assign_public_ip = true
    subnet_id        = oci_core_subnet.public.id
    display_name     = "dqp-scanner-vnic"
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = 50
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
      bootstrap_b64 = base64encode(file("${path.module}/bootstrap.sh"))
    }))
  }

  freeform_tags = {
    application = "dividend-capture-scanner"
    cost_scope  = "always-free-target"
  }
}
