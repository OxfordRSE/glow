# Glow AWS Deployment

This deployment flow uses:

- Terraform for durable infrastructure
- CodeBuild + Packer for a thin runner AMI
- Python orchestration for EC2 launch, EBS handoff, health checks, and rollback

Run it with:

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

Important:

- This flow assumes the DNS zone is managed by someone else.
- A successful deployment requires an `ISSUED` ACM certificate that covers the root, `api.`, and `odk.` hostnames.
- If you do not provide `--certificate-arn`, the deploy tool tries to discover a matching issued certificate automatically.
- If no issued certificate is available, the deploy tool requests or reuses a pending ACM certificate, prints the validation records for the external DNS owner, and stops before creating the HTTPS ALB listeners.
- When the certificate already exists and is issued, the ALB is configured directly in HTTPS mode and port `80` redirects to `443`.
