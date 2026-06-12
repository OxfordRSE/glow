from __future__ import annotations

import time
from typing import Any, Iterable

from .common import Console, DeploymentError, render_certificate_setup_instructions


def required_domain_names(domain_name: str) -> list[str]:
    return [domain_name, f"api.{domain_name}", f"odk.{domain_name}"]


def hostname_matches_pattern(*, hostname: str, pattern: str) -> bool:
    if hostname == pattern:
        return True
    if not pattern.startswith("*."):
        return False
    suffix = pattern[1:]
    if not hostname.endswith(suffix):
        return False
    hostname_labels = hostname.split(".")
    pattern_labels = pattern.split(".")
    return len(hostname_labels) == len(pattern_labels)


def certificate_covers_domain_set(certificate: dict[str, Any], domain_name: str) -> bool:
    covered_names = set(certificate.get("SubjectAlternativeNames", []))
    if certificate.get("DomainName"):
        covered_names.add(str(certificate["DomainName"]))
    return all(
        any(hostname_matches_pattern(hostname=hostname, pattern=pattern) for pattern in covered_names)
        for hostname in required_domain_names(domain_name)
    )


def describe_certificate(acm_client: Any, certificate_arn: str) -> dict[str, Any]:
    response = acm_client.describe_certificate(CertificateArn=certificate_arn)
    return dict(response["Certificate"])


def iter_certificates(acm_client: Any, statuses: Iterable[str]) -> list[dict[str, Any]]:
    certificates: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {"CertificateStatuses": list(statuses)}
    while True:
        response = acm_client.list_certificates(**kwargs)
        certificates.extend(response.get("CertificateSummaryList", []))
        token = response.get("NextToken")
        if not token:
            return certificates
        kwargs["NextToken"] = token


def find_matching_certificate(acm_client: Any, *, domain_name: str, statuses: Iterable[str]) -> dict[str, Any] | None:
    for summary in iter_certificates(acm_client, statuses):
        certificate_arn = summary.get("CertificateArn")
        if not isinstance(certificate_arn, str):
            continue
        certificate = describe_certificate(acm_client, certificate_arn)
        if certificate_covers_domain_set(certificate, domain_name):
            return certificate
    return None


def certificate_validation_records(certificate: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for option in certificate.get("DomainValidationOptions", []):
        record = option.get("ResourceRecord") or {}
        name = record.get("Name")
        record_type = record.get("Type")
        value = record.get("Value")
        if all(isinstance(item, str) and item for item in (name, record_type, value)):
            result.append({"name": name, "type": record_type, "value": value})
    return result


def wait_for_validation_records(acm_client: Any, certificate_arn: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while True:
        certificate = describe_certificate(acm_client, certificate_arn)
        if certificate_validation_records(certificate):
            return certificate
        if time.monotonic() >= deadline:
            return certificate
        time.sleep(2)


def request_certificate(acm_client: Any, *, domain_name: str) -> dict[str, Any]:
    response = acm_client.request_certificate(
        DomainName=domain_name,
        ValidationMethod="DNS",
        SubjectAlternativeNames=[f"api.{domain_name}", f"odk.{domain_name}"],
        IdempotencyToken=domain_name.replace(".", "")[:32],
    )
    certificate_arn = str(response["CertificateArn"])
    return wait_for_validation_records(acm_client, certificate_arn)


def resolve_issued_certificate(
    console: Console,
    acm_client: Any,
    *,
    domain_name: str,
    certificate_arn: str,
    dry_run: bool,
) -> dict[str, Any]:
    if certificate_arn:
        certificate = describe_certificate(acm_client, certificate_arn)
        if not certificate_covers_domain_set(certificate, domain_name):
            raise DeploymentError(
                f"certificate {certificate_arn} does not cover {domain_name}, api.{domain_name}, and odk.{domain_name}"
            )
        if certificate.get("Status") == "ISSUED":
            return certificate
        certificate = wait_for_validation_records(acm_client, certificate_arn)
        raise DeploymentError(
            render_certificate_setup_instructions(
                domain_name=domain_name,
                certificate_arn=certificate_arn,
                validation_records=certificate_validation_records(certificate),
                certificate_status=str(certificate.get("Status", "UNKNOWN")),
                dry_run=dry_run,
            )
        )

    issued = find_matching_certificate(acm_client, domain_name=domain_name, statuses=["ISSUED"])
    if issued:
        return issued

    pending = find_matching_certificate(acm_client, domain_name=domain_name, statuses=["PENDING_VALIDATION"])
    if not pending and dry_run:
        raise DeploymentError(
            "No issued ACM certificate is available, and dry-run mode will not request a new one. "
            "Request or validate a certificate first, then rerun the dry-run."
        )

    if not pending:
        console.info(f"Requesting ACM certificate for {domain_name}")
        pending = request_certificate(acm_client, domain_name=domain_name)

    raise DeploymentError(
        render_certificate_setup_instructions(
            domain_name=domain_name,
            certificate_arn=str(pending["CertificateArn"]),
            validation_records=certificate_validation_records(pending),
            certificate_status=str(pending.get("Status", "UNKNOWN")),
            dry_run=dry_run,
        )
    )
