# OCI deployment for DQP

This package provisions a small ARM Linux VM and installs the Dividend Quality Pullback scanner as a `systemd` timer. It targets OCI Always Free limits, but Terraform cannot guarantee billing eligibility. Confirm that every selected resource is labelled **Always Free eligible** in the OCI plan and console before applying.

## Architecture

- OCI Ampere A1 Flex: 1 OCPU, 6 GB RAM
- Ubuntu 24.04 ARM
- 50 GB boot volume
- Public subnet with outbound internet
- SSH restricted to one caller-supplied CIDR
- Scanner timer: weekdays at 10:00 America/New_York
- Local watchdog: weekdays at 11:00 America/New_York
- Optional external dead-man integration through `HEALTHCHECKS_PING_URL`
- Persistent history, reports, and logs under `/var/lib/dqp-scanner` and `/var/log/dqp-scanner`

No Telegram secret is placed in Terraform state or GitHub. Secrets are entered once over SSH after provisioning.

## Prerequisites

1. An active OCI tenancy with an Always Free-eligible Ampere A1 shape available in its home region.
2. Terraform 1.6+ and OCI API authentication configured.
3. An SSH public key.
4. Your current public IPv4 address expressed as a `/32` CIDR.

## Provision

```bash
cd deploy/oci
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with the real values.
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

The configuration intentionally rejects `0.0.0.0/0` for SSH.

If OCI returns `Out of host capacity`, change `availability_domain_index` or retry later. Do not switch to a paid shape without reviewing cost.

## Finish secure configuration

Wait for cloud-init, then use the Terraform output:

```bash
terraform output -raw ssh_command
ssh ubuntu@SERVER_IP
cloud-init status --wait
sudo bash /opt/dqp-scanner/deploy/oci/configure.sh
```

The configuration script:

- writes Telegram credentials to `/etc/dqp-scanner.env` with mode `0600`;
- enables the scanner and watchdog timers;
- runs a five-ticker, no-Telegram dry-run;
- prints the installed timers.

## Verification

```bash
systemctl list-timers --all 'dqp-*'
sudo systemctl start dqp-scanner.service
sudo journalctl -u dqp-scanner.service -n 200 --no-pager
sudo cat /var/lib/dqp-scanner/last_healthy_run_ny.txt
```

A healthy run requires both exit code 0 and a generated health JSON with `is_collapsed=false`. Provider-collapse runs do not update the healthy marker.

## Updating code after a reviewed merge

```bash
sudo git -C /opt/dqp-scanner fetch --prune origin
sudo git -C /opt/dqp-scanner checkout main
sudo git -C /opt/dqp-scanner reset --hard origin/main
sudo /opt/dqp-scanner/.venv/bin/python -m pip install -r /opt/dqp-scanner/requirements.txt
sudo systemctl daemon-reload
```

## Reliability boundary

The 11:00 watchdog runs on the same VM, so it can report scanner failures only when the VM and its network are alive. Configure `HEALTHCHECKS_PING_URL` for a genuinely external missed-run detector. The scanner wrapper pings that URL only after a non-collapsed run and calls `/fail` after an unhealthy run.

## Cost controls

- Keep the shape at `VM.Standard.A1.Flex`, 1 OCPU, 6 GB RAM.
- Keep the boot volume at 50 GB.
- Review `terraform plan` for any non-free resource.
- Create an OCI budget alert even when targeting Always Free.
- Never assume a resource is free solely because it appears in this template.
