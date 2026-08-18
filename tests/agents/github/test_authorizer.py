# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for agents/github/lambda/authorizer.py."""

import importlib.util
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest

_GITHUB_LAMBDA_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'github', 'lambda',
))


@pytest.fixture(autouse=True)
def _isolate_module():
    """Load authorizer fresh for each test, then clean up."""
    sys.path.insert(0, _GITHUB_LAMBDA_DIR)
    yield
    sys.path.remove(_GITHUB_LAMBDA_DIR)
    for mod_name in ['authorizer', 'http_client']:
        sys.modules.pop(mod_name, None)


def _load_authorizer():
    """Import authorizer with a mocked http_client."""
    sys.modules.pop('authorizer', None)
    sys.modules.pop('http_client', None)
    mock_http = MagicMock()
    mock_http.ORG = 'opensearch-project'
    sys.modules['http_client'] = mock_http

    spec = importlib.util.spec_from_file_location(
        'authorizer', os.path.join(_GITHUB_LAMBDA_DIR, 'authorizer.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestIsWriteOperation:

    def test_write_functions(self):
        mod = _load_authorizer()
        for fn in ['merge_pr', 'create_issue', 'close_issue', 'transfer_issue',
                   'add_comment', 'bulk_comment', 'bulk_merge_prs']:
            assert mod.is_write_operation(fn) is True

    def test_read_functions(self):
        mod = _load_authorizer()
        for fn in ['get_pr_details', 'list_prs', 'search_issues', 'list_issues',
                   'get_repo_maintainers']:
            assert mod.is_write_operation(fn) is False


class TestValidateOrgScope:

    def test_valid_org_returns_none(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("list_issues", {"organization": "opensearch-project"})
        assert result is None

    def test_empty_org_param_returns_none(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("list_issues", {"organization": ""})
        assert result is None

    def test_no_org_param_returns_none(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("list_issues", {})
        assert result is None

    def test_wrong_org_rejected(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("list_issues", {"organization": "evil-org"})
        assert result is not None
        assert "evil-org" in result
        assert "not permitted" in result

    def test_transfer_issue_valid_target(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("transfer_issue", {"target_repo": "other-repo"})
        assert result is None

    def test_transfer_issue_cross_org_rejected(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("transfer_issue", {"target_repo": "evil-org/repo"})
        assert result is not None
        assert "evil-org/repo" in result
        assert "outside" in result

    def test_repo_with_matching_org_prefix_valid(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("get_pr_details", {"repo": "opensearch-project/OpenSearch"})
        assert result is None

    def test_repo_without_slash_valid(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("get_pr_details", {"repo": "OpenSearch"})
        assert result is None

    def test_repo_with_wrong_org_prefix_rejected(self):
        mod = _load_authorizer()
        result = mod.validate_org_scope("get_pr_details", {"repo": "attacker/evil-repo"})
        assert result is not None
        assert "attacker/evil-repo" in result
        assert "outside" in result


class TestAuditLog:

    def test_write_operation_logs_at_info(self, caplog):
        mod = _load_authorizer()
        with caplog.at_level(logging.INFO, logger='authorizer'):
            mod.audit_log(
                "merge_pr", {"repo": "OpenSearch", "pr_number": "42"},
                "success", True, "req-123",
            )
        assert any("AUDIT" in r.message and "WRITE" in r.message for r in caplog.records)

    def test_read_operation_logs_at_info(self, caplog):
        mod = _load_authorizer()
        with caplog.at_level(logging.INFO, logger='authorizer'):
            mod.audit_log(
                "get_pr_details", {"repo": "OpenSearch", "pr_number": "42"},
                "success", True, "req-456",
            )
        assert any("AUDIT" in r.message and "READ" in r.message for r in caplog.records)

    def test_failed_operation_logs_at_error(self, caplog):
        mod = _load_authorizer()
        with caplog.at_level(logging.ERROR, logger='authorizer'):
            mod.audit_log(
                "merge_pr", {"repo": "OpenSearch", "pr_number": "42"},
                "Not Found", False, "req-789",
            )
        assert any("AUDIT" in r.message and "Not Found" in r.message for r in caplog.records)

    def test_session_attributes_included(self, caplog):
        mod = _load_authorizer()
        with caplog.at_level(logging.INFO, logger='authorizer'):
            mod.audit_log(
                "merge_pr", {"repo": "OpenSearch", "pr_number": "42"},
                "success", True, "req-abc",
                session_attributes={"requester_user_id": "U_REQ", "approver_user_id": "U_APP"},
            )
        log_text = " ".join(r.message for r in caplog.records)
        assert "U_REQ" in log_text
        assert "U_APP" in log_text

    def test_write_params_included(self, caplog):
        mod = _load_authorizer()
        with caplog.at_level(logging.INFO, logger='authorizer'):
            mod.audit_log(
                "transfer_issue",
                {"repo": "OpenSearch", "issue_number": "10", "target_repo": "other-repo"},
                "success", True, "req-transfer",
            )
        log_text = " ".join(r.message for r in caplog.records)
        assert "issue_number" in log_text
        assert "target_repo" in log_text

    def test_bulk_issue_numbers_included(self, caplog):
        mod = _load_authorizer()
        with caplog.at_level(logging.INFO, logger='authorizer'):
            mod.audit_log(
                "bulk_comment",
                {"repo": "N/A", "issue_numbers": "1,2,3"},
                "success", True, "req-bulk",
            )
        log_text = " ".join(r.message for r in caplog.records)
        assert "issue_numbers" in log_text
