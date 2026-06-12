from __future__ import annotations

from glow_aws_deploy.certificates import certificate_covers_domain_set, hostname_matches_pattern
from glow_aws_deploy.common import enveloping_domain, github_raw_file_url, render_dns_instructions


def test_enveloping_domain_for_subdomain() -> None:
    assert enveloping_domain("eu.glow-project.org") == "glow-project.org"


def test_enveloping_domain_for_short_domain() -> None:
    assert enveloping_domain("example.com") == "example.com"


def test_github_raw_file_url() -> None:
    assert github_raw_file_url(
        "https://github.com/OxfordRSE/glow.git",
        "abc123",
        "deploy/aws/runner/VERSION",
    ) == "https://raw.githubusercontent.com/OxfordRSE/glow/abc123/deploy/aws/runner/VERSION"


def test_render_dns_instructions_mentions_alias_for_apex() -> None:
    text = render_dns_instructions(
        domain_name="example.com",
        alb_dns_name="alb.example.elb.amazonaws.com",
        certificate_status="PENDING_VALIDATION",
        validation_records=[
            {"name": "_abc.example.com", "type": "CNAME", "value": "_def.acm-validations.aws."}
        ],
    )
    assert "owner of `example.com`" in text
    assert "ALIAS/ANAME" in text
    assert "PENDING_VALIDATION" in text


def test_render_dns_instructions_without_validation_records() -> None:
    text = render_dns_instructions(
        domain_name="example.com",
        alb_dns_name="alb.example.elb.amazonaws.com",
        certificate_status="ISSUED",
    )
    assert "Certificate validation records:" not in text
    assert "Application routing records:" in text


def test_hostname_matches_pattern() -> None:
    assert hostname_matches_pattern(hostname="api.example.com", pattern="*.example.com")
    assert not hostname_matches_pattern(hostname="example.com", pattern="*.example.com")
    assert not hostname_matches_pattern(hostname="deep.api.example.com", pattern="*.example.com")


def test_certificate_covers_domain_set() -> None:
    certificate = {
        "DomainName": "example.com",
        "SubjectAlternativeNames": ["example.com", "*.example.com"],
    }
    assert certificate_covers_domain_set(certificate, "example.com")
