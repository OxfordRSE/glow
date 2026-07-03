# Glow Deployment Quick Start

## Command

```bash
uv run --project deploy/aws deploy/aws/deploy.py --domain eu.glow-project.org
```

Optional flags:

- `--certificate-arn arn:aws:acm:...`
- `--git-ref v1.2.3`
- `--aws-region eu-west-2`
- `--force-rebuild`
- `--dry-run`
- `--verbose`

## What It Does

1. Validates AWS credentials and the requested Git ref.
2. Ensures an S3 bucket exists for Terraform state.
3. Applies bootstrap Terraform for the runner AMI CodeBuild project.
4. Builds or reuses the thin runner AMI.
5. Applies main Terraform for ALB, ACM, IAM, launch template, and persistent EBS volume.
6. Launches a fresh EC2 runner instance.
7. Waits for SSM/bootstrap readiness.
8. Deregisters the old instance, stops the old stack, detaches the persistent data volume, and reattaches it to the new instance.
9. Activates the stack on the new instance and waits for health.
10. Registers the new instance in the ALB target groups and terminates the old instance.

If the volume handoff fails after the old instance is stopped, the tool attempts rollback by reattaching the volume to the old instance and restarting the old stack.

## Prerequisites

1. `uv`
2. `terraform`
3. `git`
4. AWS credentials that can manage EC2, ALB, ACM, S3, IAM, and CodeBuild

## Certificate Assumption

Successful deployment assumes an already-issued ACM certificate for:

- `<domain>`
- `api.<domain>`
- `odk.<domain>`

You can provide this explicitly with `--certificate-arn`, or let the deploy tool auto-discover a matching issued certificate in the target AWS account.

If no issued certificate is available, the deploy tool will stop and print the ACM validation records needed to get one issued.

## DNS Ownership Assumption

This deployment flow assumes **you do not own the Route53 zone**.

For a successful deployment, the tool prints the routing records to send to the external DNS owner:

1. Dashboard/API/ODK routing records to the ALB DNS name

If no issued ACM certificate exists yet, it also prints the validation CNAME records for the certificate request and then exits before main deployment.

The message is phrased as:

```text
Ask the owner of <enveloping-domain> to create these DNS records...
```

## HTTPS Behavior

In the successful path, the ALB is created directly in HTTPS mode.

- Port `443` serves the application.
- Port `80` redirects to HTTPS.
- Once the external DNS owner points the requested hostnames at the ALB, the site should behave normally without a follow-up deploy.

If no issued ACM certificate exists yet, deployment stops early and prints the validation records that need to be added before a later deploy can succeed.

That failure mode is expected and deliberate: there is no HTTP-only fallback ALB mode in this flow.

## Notes

- The root dashboard host may need `ALIAS`/`ANAME` support instead of a plain `CNAME` if the external DNS provider treats it as a zone apex.
- The deploy tool uses a thin runner AMI and builds the application containers on instance startup.
- The persistent application state remains on a single EBS volume in v1, so a brief outage during cutover is expected.
