"""Company-profile field extraction & assertion tests.

Moved out of the monolithic ``tests/test_system.py`` (SystemService test-split,
batch B). Reuses the shared ``SystemServiceTestBase`` fixture from
``tests/support``; behaviour is identical to the original methods.
"""

from __future__ import annotations

import json
import unittest

from app.models import (
    CompanyProfileFieldAssertion,
    Document,
    Evidence,
    ResearchReportAsset,
    RightsTag,
)
from tests.support import SystemServiceTestBase


class CompanyProfileTests(SystemServiceTestBase):
    def test_company_profile_coverage_audit_reports_deep_missing_fields(self) -> None:
        audit = self.router.dispatch(
            "POST",
            "/api/company-profiles/coverage/audit",
            {"symbols": ["DEMO"], "limit": 1},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        self.assertEqual(audit.data["schema_id"], "company-profile-deep-field-coverage-v1")
        self.assertEqual(audit.data["issuer_count"], 1)
        row = audit.data["companies"][0]
        self.assertEqual(row["issuer_id"], "issuer_001")
        self.assertTrue(row["fields"]["legal_name"]["present"])
        self.assertTrue(row["fields"]["security_ids"]["present"])
        self.assertFalse(row["fields"]["business_summary"]["present"])
        self.assertIn("business_summary", row["missing_fields"])
        self.assertGreater(audit.data["field_missing_counts"]["business_summary"], 0)
        self.assertTrue(any(task["field"] == "business_summary" for task in row["research_tasks"]))

        alias = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-coverage/audit",
            {"symbols": ["DEMO"], "required_fields": ["legal_name", "business_summary"]},
            actor="data",
            role="analyst",
        )
        self.assertTrue(alias.success, alias.error)
        self.assertEqual(alias.data["required_fields"], ["legal_name", "business_summary"])

    def test_company_profile_coverage_audit_counts_official_sources_and_evidence(self) -> None:
        issuer = self.service.store.issuers["issuer_001"]
        issuer.region = "East China"
        issuer.sector = "Technology"
        issuer.industry = "Components"
        issuer.company_details = {"business_summary": "Demo supplies advanced components.", "products": ["Demo module"]}
        issuer.fundamentals = {"period": "2026Q1", "revenue": 1200.0, "net_income": 180.0, "gross_margin": 0.42, "cash": 300.0, "debt": 80.0}
        issuer.valuation_metrics = {"pe": 22.0}
        issuer.data_sources = ["src_sec"]
        security = self.service.store.securities["sec_001"]
        security.security_type = "common_stock"
        security.listing_date = "2020-01-02"
        self.service.register_market_data_point(
            {
                "data_id": "md_demo_profile_latest",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "market": "A",
                "as_of_date": "2026-06-24",
                "close": 12.3,
                "volume": 123456,
                "amount": 1000000,
            },
            actor="data",
        )
        document = Document(
            document_id="doc_demo_annual",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="annual_report",
            source_id="src_sec",
            source_type="regulatory",
            source_uri="https://example.test/demo-annual-report",
            rights_tag=RightsTag("public"),
            body="Demo supplies advanced components. Revenue and profit were disclosed.",
            title="Demo annual report",
        )
        self.service.store.documents[document.document_id] = document
        self.service.store.evidence["evi_demo_business"] = Evidence(
            evidence_id="evi_demo_business",
            document_id=document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text="Demo supplies advanced components.",
            canonical_text="Demo supplies advanced components.",
            confidence=0.95,
            issuer_id="issuer_001",
            security_id="sec_001",
        )

        audit = self.router.dispatch(
            "POST",
            "/api/company-profiles/coverage/audit",
            {"symbols": ["DEMO"], "include_optional": True, "limit": 1},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        fields = audit.data["companies"][0]["fields"]
        self.assertTrue(fields["business_summary"]["present"])
        self.assertTrue(fields["products"]["present"])
        self.assertTrue(fields["revenue"]["present"])
        self.assertTrue(fields["net_income"]["present"])
        self.assertTrue(fields["authorized_documents"]["present"])
        self.assertTrue(fields["field_evidence_ids"]["present"])
        self.assertIn("evi_demo_business", fields["evidence_backlinks"]["evidence_ids"])
        self.assertTrue(fields["close"]["present"])
        self.assertTrue(fields["amount"]["present"])

    def test_company_profile_coverage_audit_keeps_research_reports_opinion_only(self) -> None:
        research_document = Document(
            document_id="doc_demo_research",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="research_report",
            source_id="local_research_reports",
            source_type="broker_research",
            source_uri="local://demo-research",
            rights_tag=RightsTag("public"),
            body="Demo Corp research view says business momentum is improving.",
            title="Demo research report",
        )
        self.service.store.documents[research_document.document_id] = research_document
        self.service.store.evidence["evi_demo_research"] = Evidence(
            evidence_id="evi_demo_research",
            document_id=research_document.document_id,
            section="research_report_citation",
            page_no=1,
            bbox="research",
            span_text="Research opinion on Demo.",
            canonical_text="Research opinion on Demo.",
            confidence=0.8,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        self.service.store.research_reports["rr_demo_bound"] = ResearchReportAsset(
            report_id="rr_demo_bound",
            source_id="local_research_reports",
            broker="Local Broker",
            file_path="/tmp/demo.pdf",
            file_name="demo.pdf",
            title="Demo local research",
            document_id=research_document.document_id,
            issuer_id="issuer_001",
            security_id="sec_001",
            status="text_indexed",
        )

        audit = self.router.dispatch(
            "POST",
            "/api/company-profiles/coverage/audit",
            {"symbols": ["DEMO"], "required_fields": ["authorized_documents", "field_evidence_ids", "business_summary", "research_report_count"]},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        fields = audit.data["companies"][0]["fields"]
        self.assertTrue(fields["research_report_count"]["present"])
        self.assertEqual(fields["research_report_count"]["source_policy"], "opinion_slot")
        self.assertFalse(fields["authorized_documents"]["present"])
        self.assertFalse(fields["field_evidence_ids"]["present"])
        self.assertFalse(fields["business_summary"]["present"])
        self.assertEqual(fields["business_summary"]["missing_reason"], "research_report_or_local_reference_is_not_fact_source")
        self.assertEqual(audit.data["rules"]["research_reports"], "opinion_and_attention_slots_only_not_fact_source")

    def test_company_profile_field_extraction_updates_from_official_evidence(self) -> None:
        self.service.register_source(
            {
                "source_id": "src_company_ir",
                "source_type": "company_ir",
                "allowed_document_types": ["official_business_overview"],
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="risk",
        )
        document = Document(
            document_id="doc_demo_ir_profile",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="official_business_overview",
            source_id="src_company_ir",
            source_type="company_ir",
            source_uri="https://example.test/demo-ir-profile",
            rights_tag=RightsTag("public"),
            body="",
            title="Demo company IR profile",
        )
        self.service.store.documents[document.document_id] = document
        self.service.store.evidence["evi_demo_ir_profile"] = Evidence(
            evidence_id="evi_demo_ir_profile",
            document_id=document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text=(
                "Business overview: Demo Corp is engaged in cloud AI chips and data center acceleration. "
                "Products include AI accelerator module, inference card. Official website: https://demo.example.com. "
                "Investor relations: https://demo.example.com/investors. Headquarters: Shanghai, China. "
                "Employees 12,300. CEO Jane Doe. CFO John Smith. Customers include Alpha Cloud, Beta Auto. "
                "Suppliers include Gamma Foundry, Delta Packaging. FY2026 revenue 1200 million "
                "and net income 180 million with gross margin 42%. Cash 300 million and debt 80 million."
            ),
            canonical_text=(
                "Business overview: Demo Corp is engaged in cloud AI chips and data center acceleration. "
                "Products include AI accelerator module, inference card. Official website: https://demo.example.com. "
                "Investor relations: https://demo.example.com/investors. Headquarters: Shanghai, China. "
                "Employees 12,300. CEO Jane Doe. CFO John Smith. Customers include Alpha Cloud, Beta Auto. "
                "Suppliers include Gamma Foundry, Delta Packaging. FY2026 revenue 1200 million "
                "and net income 180 million with gross margin 42%. Cash 300 million and debt 80 million."
            ),
            confidence=0.93,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        fields_to_extract = [
            "business_summary",
            "products",
            "website_url",
            "ir_url",
            "headquarters",
            "employee_count",
            "management",
            "key_customers",
            "key_suppliers",
            "period",
            "revenue",
            "net_income",
            "gross_margin",
            "cash",
            "debt",
        ]

        dry_run = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {
                "symbols": ["DEMO"],
                "fields": fields_to_extract,
                "require_evidence": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertEqual(dry_run.data["status"], "dry_run")
        self.assertGreaterEqual(dry_run.data["totals"]["fields_planned"], 15)
        self.assertNotIn("issuer_001", self.service.store.company_profiles)
        self.assertEqual(len(self.service.store.company_profile_field_assertions), 0)

        executed = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {
                "symbols": ["DEMO"],
                "fields": fields_to_extract,
                "require_evidence": True,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["status"], "executed")
        self.assertEqual(executed.data["totals"]["profiles_saved"], 1)
        issuer = self.service.store.issuers["issuer_001"]
        self.assertIn("cloud AI chips", issuer.company_details["business_summary"])
        self.assertIn("AI accelerator module", issuer.company_details["products"])
        self.assertEqual(issuer.company_details["website_url"], "https://demo.example.com")
        self.assertEqual(issuer.company_details["ir_url"], "https://demo.example.com/investors")
        self.assertIn("Shanghai", issuer.company_details["headquarters"])
        self.assertEqual(issuer.company_details["employee_count"], 12300)
        self.assertIn({"role": "CEO", "name": "Jane Doe"}, issuer.company_details["management"])
        self.assertIn("Alpha Cloud", issuer.company_details["key_customers"])
        self.assertIn("Gamma Foundry", issuer.company_details["key_suppliers"])
        self.assertEqual(issuer.fundamentals["period"], "FY2026")
        self.assertEqual(issuer.fundamentals["revenue"], 1200000000.0)
        self.assertEqual(issuer.fundamentals["net_income"], 180000000.0)
        self.assertEqual(issuer.fundamentals["gross_margin"], 0.42)
        profile = self.service.store.company_profiles["issuer_001"]
        self.assertIn("src_company_ir", profile.source_ids)
        self.assertIn("evi_demo_ir_profile", profile.evidence_ids)
        assertions = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions",
            {"symbols": ["DEMO"], "limit": 50},
            actor="data",
            role="analyst",
        )
        self.assertTrue(assertions.success, assertions.error)
        assertion_fields = {item["field_name"] for item in assertions.data["assertions"]}
        for field_name in ["business_summary", "website_url", "ir_url", "management", "key_customers", "revenue"]:
            self.assertIn(field_name, assertion_fields)
        website_assertion = next(item for item in assertions.data["assertions"] if item["field_name"] == "website_url")
        self.assertEqual(website_assertion["evidence_ids"], ["evi_demo_ir_profile"])
        self.assertEqual(website_assertion["source_policy"], "fact_or_governed_record")

        metrics = self.router.dispatch(
            "GET",
            "/api/company-financial-metrics",
            {"symbols": ["DEMO"], "limit": 10},
            actor="data",
            role="analyst",
        )
        self.assertTrue(metrics.success, metrics.error)
        self.assertEqual(metrics.data["schema_id"], "financial-metrics-v1")
        metrics_by_name = {item["metric_name"]: item for item in metrics.data["metrics"]}
        self.assertEqual(metrics_by_name["revenue"]["period"], "FY2026")
        self.assertEqual(metrics_by_name["revenue"]["value"], 1200000000.0)
        self.assertEqual(metrics_by_name["net_income"]["value"], 180000000.0)
        self.assertEqual(metrics_by_name["gross_margin"]["unit"], "ratio")
        self.assertEqual(metrics_by_name["revenue"]["source_ids"], ["src_company_ir"])
        self.assertEqual(metrics_by_name["revenue"]["evidence_ids"], ["evi_demo_ir_profile"])
        intelligence = self.router.dispatch("GET", "/api/company-intelligence/DEMO", {}, actor="data", role="analyst")
        self.assertTrue(intelligence.success, intelligence.error)
        self.assertEqual(intelligence.data["facts_and_events"]["latest_financial_snapshot"]["revenue"], 1200000000.0)

        audit = self.router.dispatch(
            "POST",
            "/api/company-profiles/coverage/audit",
            {"symbols": ["DEMO"], "required_fields": ["business_summary", "products", "revenue", "net_income", "field_evidence_ids"]},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        fields = audit.data["companies"][0]["fields"]
        self.assertTrue(fields["business_summary"]["present"])
        self.assertTrue(fields["products"]["present"])
        self.assertTrue(fields["revenue"]["present"])
        self.assertTrue(fields["net_income"]["present"])
        self.assertTrue(fields["field_evidence_ids"]["present"])
        self.assertTrue(any(item["resource_type"] == "financial_metric" for item in fields["revenue"]["source_records"]))

    def test_company_profile_coverage_requires_field_specific_evidence(self) -> None:
        issuer = self.service.store.issuers["issuer_001"]
        issuer.company_details = {"business_summary": "Manually entered summary without field evidence."}
        issuer.fundamentals = {"period": "FY2026", "revenue": 1200000000.0}
        document = Document(
            document_id="doc_demo_revenue_only",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="annual_report",
            source_id="src_sec",
            source_type="regulatory",
            source_uri="https://example.test/demo-revenue-only",
            rights_tag=RightsTag("public"),
            body="",
            title="Demo revenue only annual report",
        )
        self.service.store.documents[document.document_id] = document
        self.service.store.evidence["evi_demo_revenue_only"] = Evidence(
            evidence_id="evi_demo_revenue_only",
            document_id=document.document_id,
            section="financials",
            page_no=1,
            bbox="p1",
            span_text="FY2026 revenue 1200 million.",
            canonical_text="FY2026 revenue 1200 million.",
            confidence=0.95,
            issuer_id="issuer_001",
            security_id="sec_001",
        )

        audit = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-coverage/audit",
            {"symbols": ["DEMO"], "required_fields": ["business_summary", "revenue"], "require_evidence": True},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        fields = audit.data["companies"][0]["fields"]
        self.assertFalse(fields["business_summary"]["present"])
        self.assertTrue(fields["revenue"]["present"])
        self.assertEqual(fields["revenue"]["evidence_ids"], ["evi_demo_revenue_only"])

    def test_company_profile_field_assertion_conflict_requires_review_before_replacement(self) -> None:
        first_document = Document(
            document_id="doc_demo_website_old",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="official_business_overview",
            source_id="src_company_ir_old",
            source_type="company_ir",
            source_uri="https://example.test/demo-old",
            rights_tag=RightsTag("public"),
            body="",
            title="Demo old official website",
        )
        self.service.store.documents[first_document.document_id] = first_document
        self.service.store.evidence["evi_demo_website_old"] = Evidence(
            evidence_id="evi_demo_website_old",
            document_id=first_document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text="Official website: https://demo.example.com.",
            canonical_text="Official website: https://demo.example.com.",
            confidence=0.90,
            issuer_id="issuer_001",
            security_id="sec_001",
        )

        first = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {"symbols": ["DEMO"], "fields": ["website_url"], "require_evidence": True, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(first.success, first.error)
        self.assertEqual(first.data["totals"]["fields_updated"], 1)
        old_assertion_id = first.data["companies"][0]["applied"]["assertion_ids"][0]
        self.assertEqual(self.service.store.issuers["issuer_001"].company_details["website_url"], "https://demo.example.com")

        second_document = Document(
            document_id="doc_demo_website_new",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="official_business_overview",
            source_id="src_company_ir_new",
            source_type="company_ir",
            source_uri="https://example.test/demo-new",
            rights_tag=RightsTag("public"),
            body="",
            title="Demo new official website",
        )
        self.service.store.documents[second_document.document_id] = second_document
        self.service.store.evidence["evi_demo_website_new"] = Evidence(
            evidence_id="evi_demo_website_new",
            document_id=second_document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text="Official website: https://new-demo.example.com.",
            canonical_text="Official website: https://new-demo.example.com.",
            confidence=0.99,
            issuer_id="issuer_001",
            security_id="sec_001",
        )

        conflict = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {
                "symbols": ["DEMO"],
                "fields": ["website_url"],
                "require_evidence": True,
                "refresh_existing": True,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(conflict.success, conflict.error)
        self.assertEqual(conflict.data["totals"]["fields_updated"], 0)
        self.assertEqual(conflict.data["totals"]["assertions_recorded"], 1)
        self.assertEqual(conflict.data["totals"]["conflict_assertions"], 1)
        applied = conflict.data["companies"][0]["applied"]
        self.assertEqual(applied["updated_fields"], [])
        conflict_assertion_id = applied["assertion_ids"][0]
        self.assertEqual(self.service.store.issuers["issuer_001"].company_details["website_url"], "https://demo.example.com")
        self.assertNotIn("src_company_ir_new", self.service.store.company_profiles["issuer_001"].source_ids)
        conflict_assertion = self.service.store.company_profile_field_assertions[conflict_assertion_id]
        self.assertEqual(conflict_assertion.assertion_status, "conflict_candidate")
        self.assertEqual(conflict_assertion.review_status, "needs_review")
        self.assertEqual(conflict_assertion.conflicts_with, [old_assertion_id])

        query = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions",
            {"symbols": ["DEMO"], "field_name": "website_url", "limit": 10},
            actor="data",
            role="analyst",
        )
        self.assertTrue(query.success, query.error)
        self.assertEqual(query.data["conflict_count"], 1)

        reviewed = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions/review",
            {"assertion_id": conflict_assertion_id, "action": "approve", "note": "new official website supersedes old IR page"},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(reviewed.success, reviewed.error)
        self.assertEqual(reviewed.data["superseded_assertion_ids"], [old_assertion_id])
        self.assertEqual(self.service.store.issuers["issuer_001"].company_details["website_url"], "https://new-demo.example.com")
        self.assertEqual(self.service.store.company_profile_field_assertions[old_assertion_id].assertion_status, "superseded")
        self.assertEqual(self.service.store.company_profile_field_assertions[old_assertion_id].resolved_by, conflict_assertion_id)
        self.assertEqual(self.service.store.company_profile_field_assertions[conflict_assertion_id].assertion_status, "active")
        self.assertEqual(self.service.store.company_profile_field_assertions[conflict_assertion_id].review_status, "approved")

        active_query = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions",
            {"symbols": ["DEMO"], "field_name": "website_url", "assertion_status": "active", "limit": 10},
            actor="data",
            role="analyst",
        )
        self.assertTrue(active_query.success, active_query.error)
        self.assertEqual([item["assertion_id"] for item in active_query.data["assertions"]], [conflict_assertion_id])
        superseded_query = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions",
            {"symbols": ["DEMO"], "field_name": "website_url", "assertion_status": "superseded", "limit": 10},
            actor="data",
            role="analyst",
        )
        self.assertTrue(superseded_query.success, superseded_query.error)
        self.assertEqual([item["assertion_id"] for item in superseded_query.data["assertions"]], [old_assertion_id])

        audit = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-coverage/audit",
            {"symbols": ["DEMO"], "required_fields": ["website_url"], "require_evidence": True},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        website_field = audit.data["companies"][0]["fields"]["website_url"]
        self.assertTrue(website_field["present"])
        self.assertEqual(website_field["assertion_ids"], [conflict_assertion_id])
        self.assertEqual(website_field["evidence_ids"], ["evi_demo_website_new"])

    def test_company_profile_field_assertion_reject_keeps_existing_profile_value(self) -> None:
        first_document = Document(
            document_id="doc_demo_website_reject_old",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="official_business_overview",
            source_id="src_company_ir_reject_old",
            source_type="company_ir",
            source_uri="https://example.test/reject-old",
            rights_tag=RightsTag("public"),
            body="",
            title="Demo old official website",
        )
        self.service.store.documents[first_document.document_id] = first_document
        self.service.store.evidence["evi_demo_website_reject_old"] = Evidence(
            evidence_id="evi_demo_website_reject_old",
            document_id=first_document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text="Official website: https://stable-demo.example.com.",
            canonical_text="Official website: https://stable-demo.example.com.",
            confidence=0.90,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        first = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {"symbols": ["DEMO"], "fields": ["website_url"], "require_evidence": True, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(first.success, first.error)
        old_assertion_id = first.data["companies"][0]["applied"]["assertion_ids"][0]

        second_document = Document(
            document_id="doc_demo_website_reject_new",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="official_business_overview",
            source_id="src_company_ir_reject_new",
            source_type="company_ir",
            source_uri="https://example.test/reject-new",
            rights_tag=RightsTag("public"),
            body="",
            title="Demo unsupported replacement website",
        )
        self.service.store.documents[second_document.document_id] = second_document
        self.service.store.evidence["evi_demo_website_reject_new"] = Evidence(
            evidence_id="evi_demo_website_reject_new",
            document_id=second_document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text="Official website: https://unconfirmed-demo.example.com.",
            canonical_text="Official website: https://unconfirmed-demo.example.com.",
            confidence=0.99,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        conflict = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {
                "symbols": ["DEMO"],
                "fields": ["website_url"],
                "require_evidence": True,
                "refresh_existing": True,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(conflict.success, conflict.error)
        conflict_assertion_id = conflict.data["companies"][0]["applied"]["assertion_ids"][0]

        rejected = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions/review",
            {"assertion_id": conflict_assertion_id, "action": "reject", "note": "replacement source rejected"},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(rejected.success, rejected.error)
        self.assertEqual(self.service.store.issuers["issuer_001"].company_details["website_url"], "https://stable-demo.example.com")
        self.assertEqual(self.service.store.company_profile_field_assertions[old_assertion_id].assertion_status, "active")
        self.assertEqual(self.service.store.company_profile_field_assertions[conflict_assertion_id].assertion_status, "rejected")
        self.assertEqual(self.service.store.company_profile_field_assertions[conflict_assertion_id].review_status, "rejected")

        audit = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-coverage/audit",
            {"symbols": ["DEMO"], "required_fields": ["website_url"], "require_evidence": True},
            actor="data",
            role="analyst",
        )
        self.assertTrue(audit.success, audit.error)
        website_field = audit.data["companies"][0]["fields"]["website_url"]
        self.assertTrue(website_field["present"])
        self.assertEqual(website_field["assertion_ids"], [old_assertion_id])
        self.assertEqual(website_field["evidence_ids"], ["evi_demo_website_reject_old"])

    def test_company_profile_field_assertion_query_recommends_and_batch_rejects_conflicts(self) -> None:
        old_document = Document(
            document_id="doc_demo_batch_old",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="official_business_overview",
            source_id="src_company_ir_batch_old",
            source_type="company_ir",
            source_uri="https://example.test/batch-old",
            rights_tag=RightsTag("public"),
            body="",
            title="Demo batch old profile",
        )
        self.service.store.documents[old_document.document_id] = old_document
        self.service.store.evidence["evi_demo_batch_old"] = Evidence(
            evidence_id="evi_demo_batch_old",
            document_id=old_document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text="Official website: https://batch-old.example.com. Investor relations: https://batch-old.example.com/ir.",
            canonical_text="Official website: https://batch-old.example.com. Investor relations: https://batch-old.example.com/ir.",
            confidence=0.86,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        first = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {"symbols": ["DEMO"], "fields": ["website_url", "ir_url"], "require_evidence": True, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(first.success, first.error)

        new_document = Document(
            document_id="doc_demo_batch_new",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="official_business_overview",
            source_id="src_company_ir_batch_new",
            source_type="company_ir",
            source_uri="https://example.test/batch-new",
            rights_tag=RightsTag("public"),
            body="",
            title="Demo batch new profile",
        )
        self.service.store.documents[new_document.document_id] = new_document
        self.service.store.evidence["evi_demo_batch_new"] = Evidence(
            evidence_id="evi_demo_batch_new",
            document_id=new_document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text="Official website: https://batch-new.example.com. Investor relations: https://batch-new.example.com/ir.",
            canonical_text="Official website: https://batch-new.example.com. Investor relations: https://batch-new.example.com/ir.",
            confidence=0.98,
            issuer_id="issuer_001",
            security_id="sec_001",
        )
        conflict = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {
                "symbols": ["DEMO"],
                "fields": ["website_url", "ir_url"],
                "require_evidence": True,
                "refresh_existing": True,
                "execute": True,
            },
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(conflict.success, conflict.error)
        conflict_ids = conflict.data["companies"][0]["applied"]["assertion_ids"]
        self.assertEqual(len(conflict_ids), 2)

        query = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions",
            {"symbols": ["DEMO"], "assertion_status": "conflict_candidate", "limit": 10},
            actor="data",
            role="analyst",
        )
        self.assertTrue(query.success, query.error)
        self.assertEqual(query.data["conflict_count"], 2)
        first_conflict = query.data["assertions"][0]
        self.assertTrue(first_conflict["conflicting_assertions"])
        self.assertIn("review_recommendation", first_conflict)
        self.assertIn(first_conflict["review_recommendation"]["recommended_action"], {"prefer_candidate_after_review", "manual_compare_required", "prefer_existing_after_review"})

        rejected = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions/review",
            {"assertion_ids": conflict_ids, "action": "reject", "note": "batch reject from review workbench"},
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(rejected.success, rejected.error)
        self.assertEqual(rejected.data["status"], "reviewed_batch")
        self.assertEqual(rejected.data["reviewed_count"], 2)
        self.assertEqual(self.service.store.issuers["issuer_001"].company_details["website_url"], "https://batch-old.example.com")
        self.assertEqual(self.service.store.issuers["issuer_001"].company_details["ir_url"], "https://batch-old.example.com/ir")
        for assertion_id in conflict_ids:
            self.assertEqual(self.service.store.company_profile_field_assertions[assertion_id].assertion_status, "rejected")
            self.assertEqual(self.service.store.company_profile_field_assertions[assertion_id].metadata["resolution_note"], "batch reject from review workbench")

    def test_company_profile_field_assertion_batch_approve_supersedes_old_values(self) -> None:
        issuer = self.service.store.issuers["issuer_001"]
        issuer.company_details = {
            **dict(issuer.company_details),
            "website_url": "https://batch-approve-old.example.com",
            "ir_url": "https://batch-approve-old.example.com/ir",
        }
        old_website = CompanyProfileFieldAssertion(
            assertion_id="cpfa_batch_approve_old_website",
            issuer_id="issuer_001",
            security_id="sec_001",
            field_name="website_url",
            value="https://batch-approve-old.example.com",
            normalized_value=json.dumps("https://batch-approve-old.example.com"),
            source_ids=["src_company_ir_batch_approve_old"],
            document_ids=["doc_batch_approve_old"],
            evidence_ids=["evi_batch_approve_old_website"],
            confidence=0.82,
            assertion_status="active",
            review_status="auto_generated",
            metadata={"source_type": "company_ir"},
        )
        old_ir = CompanyProfileFieldAssertion(
            assertion_id="cpfa_batch_approve_old_ir",
            issuer_id="issuer_001",
            security_id="sec_001",
            field_name="ir_url",
            value="https://batch-approve-old.example.com/ir",
            normalized_value=json.dumps("https://batch-approve-old.example.com/ir"),
            source_ids=["src_company_ir_batch_approve_old"],
            document_ids=["doc_batch_approve_old"],
            evidence_ids=["evi_batch_approve_old_ir"],
            confidence=0.82,
            assertion_status="active",
            review_status="auto_generated",
            metadata={"source_type": "company_ir"},
        )
        new_website = CompanyProfileFieldAssertion(
            assertion_id="cpfa_batch_approve_new_website",
            issuer_id="issuer_001",
            security_id="sec_001",
            field_name="website_url",
            value="https://batch-approve-new.example.com",
            normalized_value=json.dumps("https://batch-approve-new.example.com"),
            source_ids=["src_company_ir_batch_approve_new"],
            document_ids=["doc_batch_approve_new"],
            evidence_ids=["evi_batch_approve_new_website"],
            confidence=0.97,
            assertion_status="conflict_candidate",
            review_status="needs_review",
            conflicts_with=[old_website.assertion_id],
            metadata={"source_type": "company_ir"},
        )
        new_ir = CompanyProfileFieldAssertion(
            assertion_id="cpfa_batch_approve_new_ir",
            issuer_id="issuer_001",
            security_id="sec_001",
            field_name="ir_url",
            value="https://batch-approve-new.example.com/ir",
            normalized_value=json.dumps("https://batch-approve-new.example.com/ir"),
            source_ids=["src_company_ir_batch_approve_new"],
            document_ids=["doc_batch_approve_new"],
            evidence_ids=["evi_batch_approve_new_ir"],
            confidence=0.97,
            assertion_status="conflict_candidate",
            review_status="needs_review",
            conflicts_with=[old_ir.assertion_id],
            metadata={"source_type": "company_ir"},
        )
        for assertion in [old_website, old_ir, new_website, new_ir]:
            self.service.store.company_profile_field_assertions[assertion.assertion_id] = assertion

        reviewed = self.router.dispatch(
            "POST",
            "/api/company-database/profile-field-assertions/review",
            {
                "assertion_ids": [new_website.assertion_id, new_ir.assertion_id],
                "action": "approve",
                "note": "batch approve from review workbench",
            },
            actor="analyst",
            role="analyst",
        )
        self.assertTrue(reviewed.success, reviewed.error)
        self.assertEqual(reviewed.data["status"], "reviewed_batch")
        self.assertEqual(reviewed.data["reviewed_count"], 2)
        self.assertEqual(set(reviewed.data["superseded_assertion_ids"]), {old_website.assertion_id, old_ir.assertion_id})
        self.assertEqual(issuer.company_details["website_url"], "https://batch-approve-new.example.com")
        self.assertEqual(issuer.company_details["ir_url"], "https://batch-approve-new.example.com/ir")
        for assertion_id in [new_website.assertion_id, new_ir.assertion_id]:
            assertion = self.service.store.company_profile_field_assertions[assertion_id]
            self.assertEqual(assertion.assertion_status, "active")
            self.assertEqual(assertion.review_status, "approved")
            self.assertEqual(assertion.metadata["resolution_note"], "batch approve from review workbench")
        for assertion_id in [old_website.assertion_id, old_ir.assertion_id]:
            assertion = self.service.store.company_profile_field_assertions[assertion_id]
            self.assertEqual(assertion.assertion_status, "superseded")
            self.assertEqual(assertion.review_status, "superseded")
            self.assertIn(assertion.resolved_by, {new_website.assertion_id, new_ir.assertion_id})

    def test_company_profile_field_extraction_keeps_research_reports_opinion_only(self) -> None:
        research_document = Document(
            document_id="doc_demo_research_profile_extract",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="research_report",
            source_id="local_research_reports",
            source_type="broker_research",
            source_uri="local://demo-research-profile",
            rights_tag=RightsTag("public"),
            body="Business overview: Demo Corp is engaged in cloud AI chips. Products include AI module. FY2026 revenue 1200 million.",
            title="Demo research profile note",
        )
        self.service.store.documents[research_document.document_id] = research_document
        self.service.store.evidence["evi_demo_research_profile_extract"] = Evidence(
            evidence_id="evi_demo_research_profile_extract",
            document_id=research_document.document_id,
            section="research_report_citation",
            page_no=1,
            bbox="research",
            span_text=research_document.body,
            canonical_text=research_document.body,
            confidence=0.9,
            issuer_id="issuer_001",
            security_id="sec_001",
        )

        executed = self.router.dispatch(
            "POST",
            "/api/company-profiles/fields/extract",
            {"symbols": ["DEMO"], "fields": ["business_summary", "products", "revenue"], "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(executed.success, executed.error)
        self.assertEqual(executed.data["totals"]["documents_scanned"], 0)
        self.assertEqual(executed.data["totals"]["fields_updated"], 0)
        self.assertEqual(executed.data["totals"]["skipped_research_or_reference_documents"], 1)
        self.assertNotIn("business_summary", self.service.store.issuers["issuer_001"].company_details)
        self.assertNotIn("issuer_001", self.service.store.company_profiles)
        self.assertEqual(len(self.service.store.company_profile_field_assertions), 0)

    def test_company_profile_field_extraction_does_not_overwrite_without_refresh(self) -> None:
        issuer = self.service.store.issuers["issuer_001"]
        issuer.company_details = {"business_summary": "Existing official summary."}
        document = Document(
            document_id="doc_demo_ir_refresh",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="official_business_overview",
            source_id="src_company_ir",
            source_type="company_ir",
            source_uri="https://example.test/demo-ir-refresh",
            rights_tag=RightsTag("public"),
            body="Business overview: Updated official business summary for advanced AI modules.",
            title="Demo company IR refresh",
        )
        self.service.store.documents[document.document_id] = document
        self.service.store.evidence["evi_demo_ir_refresh"] = Evidence(
            evidence_id="evi_demo_ir_refresh",
            document_id=document.document_id,
            section="business_overview",
            page_no=1,
            bbox="p1",
            span_text=document.body,
            canonical_text=document.body,
            confidence=0.92,
            issuer_id="issuer_001",
            security_id="sec_001",
        )

        skipped = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {"symbols": ["DEMO"], "fields": ["business_summary"], "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(skipped.success, skipped.error)
        self.assertEqual(skipped.data["totals"]["fields_updated"], 0)
        self.assertEqual(self.service.store.issuers["issuer_001"].company_details["business_summary"], "Existing official summary.")

        refreshed = self.router.dispatch(
            "POST",
            "/api/company-database/profile-fields/extract",
            {"symbols": ["DEMO"], "fields": ["business_summary"], "refresh_existing": True, "execute": True},
            actor="data",
            role="data_engineer",
        )
        self.assertTrue(refreshed.success, refreshed.error)
        self.assertEqual(refreshed.data["totals"]["fields_updated"], 1)
        self.assertIn("Updated official business summary", self.service.store.issuers["issuer_001"].company_details["business_summary"])
        self.assertIn("evi_demo_ir_refresh", self.service.store.company_profiles["issuer_001"].evidence_ids)



if __name__ == "__main__":
    unittest.main()
