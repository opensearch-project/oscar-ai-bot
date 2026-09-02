# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the npm ecosystem remediation strategy (remediation-workers/npm/npm.py).

Covers the pure, testable logic: context building, package.json declaration
detection, minimal-diff editing (direct deps + resolutions, operator
preservation), the downgrade guard, and the out-of-scope error for undeclared
transitives. The git/GitHub side (clone/commit/PR) is exercised end-to-end
against the live fork, not here.
"""

import importlib.util
import json
import os
import subprocess
from unittest.mock import patch

import pytest

_NPM_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..',
    'agents', 'SecurityAdvisories', 'remediation-workers', 'npm',
)


def _load_npm():
    """Load npm.py with its ``remediation`` dependency injected."""
    rem_spec = importlib.util.spec_from_file_location(
        'remediation', os.path.join(_NPM_PATH, 'remediation.py'))
    rem = importlib.util.module_from_spec(rem_spec)
    rem_spec.loader.exec_module(rem)
    with patch.dict('sys.modules', {'remediation': rem}):
        npm_spec = importlib.util.spec_from_file_location(
            'npm_strategy', os.path.join(_NPM_PATH, 'npm.py'))
        npm = importlib.util.module_from_spec(npm_spec)
        npm_spec.loader.exec_module(npm)
    return npm, rem


def _write_pkg(tmp_path, manifest):
    (tmp_path / 'package.json').write_text(json.dumps(manifest, indent=2))


def _read_pkg(tmp_path):
    return json.loads((tmp_path / 'package.json').read_text())


def _write_lock(tmp_path, *packages):
    """Write a minimal yarn.lock with a resolved entry per given package."""
    lines = []
    for name, version in packages:
        lines.append(f'{name}@^{version}:\n  version "{version}"\n')
    (tmp_path / 'yarn.lock').write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


class TestBuildContext:
    def _event(self, **over):
        e = {'repo_name': 'alerting-dashboards-plugin', 'cve_id': 'CVE-2026-12143',
             'package': 'form-data', 'patched_version': '4.0.6',
             'installed_version': '4.0.4'}
        e.update(over)
        return e

    def test_builds_generic_title_cve_in_body_and_branch(self):
        npm, _ = _load_npm()
        ctx = npm.build_context(self._event(), 'v-e-e-m-a', 'opensearch-project')
        assert ctx['write_owner'] == 'v-e-e-m-a'
        assert ctx['base_owner'] == 'opensearch-project'
        assert ctx['base_branch'] == 'main'
        # generic title, no CVE id
        assert ctx['pr_title'] == 'Bump form-data to 4.0.6'
        assert 'CVE-2026-12143' not in ctx['pr_title']
        assert 'CVE-2026-12143' not in ctx['commit_message']
        # CVE recorded in body + branch
        assert 'CVE-2026-12143' in ctx['pr_body']
        assert ctx['branch_name'].startswith('oscar/cve-2026-12143-form-data-')

    def test_missing_required_field_raises(self):
        npm, rem = _load_npm()
        with pytest.raises(rem.RemediationError):
            npm.build_context(self._event(patched_version=''), 'v-e-e-m-a', 'opensearch-project')


# ---------------------------------------------------------------------------
# declaration detection + apply_fix
# ---------------------------------------------------------------------------


class TestApplyFix:
    def test_resolution_only_edits_and_installs(self, tmp_path):
        npm, _ = _load_npm()
        _write_pkg(tmp_path, {'name': 'x',
                              'resolutions': {'form-data': '4.0.4', 'other': '1.0.0'}})
        ctx = {'package_name': 'form-data', 'patched_version': '4.0.6'}
        npm.apply_fix(str(tmp_path), ctx)
        data = _read_pkg(tmp_path)
        assert data['resolutions']['form-data'] == '4.0.6'
        assert data['resolutions']['other'] == '1.0.0'   # untouched
        assert ctx['method'] == 'install'
        assert ctx['bumped_sections'] == ['resolutions']

    def test_direct_dep_only_uses_yarn_upgrade(self, tmp_path):
        # Direct dep, no resolution -> yarn upgrade handles the edit in
        # regenerate; apply_fix must NOT touch package.json.
        npm, _ = _load_npm()
        _write_pkg(tmp_path, {'name': 'x', 'dependencies': {'lodash': '^4.17.20'}})
        before = (tmp_path / 'package.json').read_text()
        ctx = {'package_name': 'lodash', 'patched_version': '4.17.21'}
        npm.apply_fix(str(tmp_path), ctx)
        assert ctx['method'] == 'upgrade'
        assert (tmp_path / 'package.json').read_text() == before  # unchanged
        assert ctx['bumped_sections'] == ['dependencies']

    def test_in_both_deps_and_resolutions_edits_both(self, tmp_path):
        # A resolution overrides the dep, so yarn upgrade alone would miss it —
        # both must be edited + yarn install.
        npm, _ = _load_npm()
        _write_pkg(tmp_path, {'name': 'x',
                              'dependencies': {'form-data': '4.0.4'},
                              'resolutions': {'form-data': '4.0.4'}})
        ctx = {'package_name': 'form-data', 'patched_version': '4.0.6'}
        npm.apply_fix(str(tmp_path), ctx)
        data = _read_pkg(tmp_path)
        assert data['dependencies']['form-data'] == '4.0.6'
        assert data['resolutions']['form-data'] == '4.0.6'
        assert ctx['method'] == 'install'
        assert set(ctx['bumped_sections']) == {'dependencies', 'resolutions'}

    def test_undeclared_transitive_adds_resolution(self, tmp_path):
        # Not a direct dep and not in resolutions, but IS in yarn.lock (a real
        # transitive) -> add a resolutions entry.
        npm, _ = _load_npm()
        _write_pkg(tmp_path, {'name': 'x',
                              'dependencies': {'react': '^18.0.0'},
                              'resolutions': {'other': '1.0.0'}})
        _write_lock(tmp_path, ('linkify-it', '3.0.3'), ('react', '18.0.0'))
        ctx = {'package_name': 'linkify-it', 'patched_version': '5.0.2'}
        npm.apply_fix(str(tmp_path), ctx)
        data = _read_pkg(tmp_path)
        assert data['resolutions']['linkify-it'] == '5.0.2'
        assert data['resolutions']['other'] == '1.0.0'   # existing kept
        assert ctx['method'] == 'install'

    def test_undeclared_adds_resolutions_block_when_missing(self, tmp_path):
        # No resolutions block at all -> create one (still valid JSON).
        npm, _ = _load_npm()
        _write_pkg(tmp_path, {'name': 'x', 'dependencies': {'react': '^18.0.0'}})
        _write_lock(tmp_path, ('linkify-it', '3.0.3'))
        ctx = {'package_name': 'linkify-it', 'patched_version': '5.0.2'}
        npm.apply_fix(str(tmp_path), ctx)
        data = _read_pkg(tmp_path)
        assert data['resolutions']['linkify-it'] == '5.0.2'
        assert data['dependencies']['react'] == '^18.0.0'  # untouched
        assert ctx['method'] == 'install'

    def test_not_a_dependency_raises(self, tmp_path):
        # Not declared AND not in yarn.lock -> not a dep of this repo; refuse to
        # add a dead resolution.
        npm, rem = _load_npm()
        _write_pkg(tmp_path, {'name': 'x', 'dependencies': {'react': '^18.0.0'}})
        _write_lock(tmp_path, ('react', '18.0.0'))   # no linkify-it
        ctx = {'package_name': 'linkify-it', 'patched_version': '5.0.2'}
        with pytest.raises(rem.RemediationError) as exc:
            npm.apply_fix(str(tmp_path), ctx)
        assert 'not a dependency of this repository' in str(exc.value)

    def test_skips_when_resolution_already_patched(self, tmp_path):
        # Fix landed between scan and remediation -> no downgrade, no work.
        npm, _ = _load_npm()
        _write_pkg(tmp_path, {'name': 'x', 'resolutions': {'form-data': '4.0.8'}})
        before = (tmp_path / 'package.json').read_text()
        ctx = {'package_name': 'form-data', 'patched_version': '4.0.6'}
        npm.apply_fix(str(tmp_path), ctx)
        assert (tmp_path / 'package.json').read_text() == before  # unchanged
        assert ctx['method'] == 'none'
        assert ctx['bumped_sections'] == []

    def test_skips_when_direct_dep_already_patched(self, tmp_path):
        npm, _ = _load_npm()
        _write_pkg(tmp_path, {'name': 'x', 'dependencies': {'lodash': '^4.17.30'}})
        ctx = {'package_name': 'lodash', 'patched_version': '4.17.21'}
        npm.apply_fix(str(tmp_path), ctx)
        assert ctx['method'] == 'none'


# ---------------------------------------------------------------------------
# version helpers
# ---------------------------------------------------------------------------


class TestVersionHelpers:
    def test_version_prefix(self):
        npm, _ = _load_npm()
        assert npm._version_prefix('^4.0.4') == '^'
        assert npm._version_prefix('~1.2.3') == '~'
        assert npm._version_prefix('>=1.0.0') == '>='
        assert npm._version_prefix('4.0.4') == ''

    def test_at_or_above(self):
        npm, _ = _load_npm()
        assert npm._at_or_above('4.0.8', '4.0.6') is True
        assert npm._at_or_above('4.0.6', '4.0.6') is True
        assert npm._at_or_above('4.0.4', '4.0.6') is False
        assert npm._at_or_above('^4.0.4', '4.0.6') is False  # operator ignored


# ---------------------------------------------------------------------------
# Slack result notification (async worker replies in the originating thread)
# ---------------------------------------------------------------------------


class TestSlackNotification:
    def test_format_message_success_includes_pr_url(self):
        _, rem = _load_npm()
        msg = rem._format_slack_message({
            'status': 'success', 'cve_id': 'CVE-2026-1', 'pr_url': 'https://x/pull/9'})
        assert 'CVE-2026-1' in msg and 'https://x/pull/9' in msg

    def test_format_message_no_change_and_error(self):
        _, rem = _load_npm()
        nc = rem._format_slack_message(
            {'status': 'no_change', 'cve_id': 'CVE-2026-2', 'message': 'already ok'})
        err = rem._format_slack_message(
            {'status': 'error', 'cve_id': 'CVE-2026-3', 'message': 'yarn blew up'})
        assert 'already ok' in nc
        assert 'yarn blew up' in err and 'failed' in err.lower()

    def test_notify_posts_when_thread_context_present(self):
        _, rem = _load_npm()
        event = {'slack_channel': 'C1', 'slack_thread_ts': '123.45'}
        result = {'status': 'success', 'cve_id': 'CVE-2026-1', 'pr_url': 'https://x/pull/9'}
        with patch.object(rem, '_resolve_slack_token', return_value='xoxb-tok'), \
                patch.object(rem, '_post_slack_message') as post:
            rem._notify_slack(event, result)
        post.assert_called_once()
        args = post.call_args[0]
        assert args[0] == 'xoxb-tok' and args[1] == 'C1' and args[2] == '123.45'
        assert 'https://x/pull/9' in args[3]

    def test_notify_skips_without_thread_context(self):
        _, rem = _load_npm()
        with patch.object(rem, '_post_slack_message') as post, \
                patch.object(rem, '_resolve_slack_token', return_value='xoxb-tok'):
            rem._notify_slack({}, {'status': 'success'})              # no channel/ts
            rem._notify_slack({'slack_channel': 'C1'}, {'status': 'success'})  # no ts
        post.assert_not_called()

    def test_notify_skips_when_no_token(self):
        _, rem = _load_npm()
        event = {'slack_channel': 'C1', 'slack_thread_ts': '123.45'}
        with patch.object(rem, '_resolve_slack_token', return_value=''), \
                patch.object(rem, '_post_slack_message') as post:
            rem._notify_slack(event, {'status': 'success'})
        post.assert_not_called()

    def test_notify_swallows_post_errors(self):
        _, rem = _load_npm()
        event = {'slack_channel': 'C1', 'slack_thread_ts': '123.45'}
        with patch.object(rem, '_resolve_slack_token', return_value='xoxb-tok'), \
                patch.object(rem, '_post_slack_message', side_effect=RuntimeError('boom')):
            rem._notify_slack(event, {'status': 'success'})  # must not raise


class TestHandleWiring:
    """Guards the handle -> _execute path. Regression test for a name collision
    where the flow function shadowed the subprocess `_run` helper, causing
    handle() to exec the event dict instead of running the remediation."""

    def test_handle_returns_result_dict_not_crash(self):
        npm, rem = _load_npm()
        # No token -> _execute early-returns a clean error BEFORE any subprocess.
        # With the old `_run` collision this raised FileNotFoundError instead.
        with patch.object(rem, '_resolve_token', return_value=''):
            result = rem.handle(
                {'repo_name': 'r', 'cve_id': 'CVE-1', 'package': 'p',
                 'patched_version': '1.0.0'}, npm)
        assert isinstance(result, dict)
        assert result['status'] == 'error'
        assert 'credential' in result['message'].lower()

    def test_handle_invokes_execute_not_subprocess_run(self):
        # _execute (the flow) and _run (the subprocess helper) must be distinct.
        _, rem = _load_npm()
        assert rem._execute is not rem._run
        # the subprocess helper takes (cmd, label, ...); the flow takes (event, strategy)
        import inspect
        assert list(inspect.signature(rem._execute).parameters)[:2] == ['event', 'strategy']
        assert list(inspect.signature(rem._run).parameters)[:2] == ['cmd', 'label']


def _load_main():
    """Load main.py (ECS entrypoint) with npm + remediation injected."""
    npm, rem = _load_npm()
    with patch.dict('sys.modules', {'remediation': rem, 'npm': npm}):
        main_spec = importlib.util.spec_from_file_location(
            'ecs_main', os.path.join(_NPM_PATH, 'main.py'))
        main = importlib.util.module_from_spec(main_spec)
        main_spec.loader.exec_module(main)
    return main, npm, rem


class TestEcsEntrypoint:
    """ECS/Fargate entrypoint: env vars -> event dict -> remediation.handle."""

    _ENV = {
        'REPO_NAME': 'security-analytics-dashboards-plugin',
        'CVE_ID': 'CVE-2026-48779',
        'PACKAGE': 'ws',
        'PATCHED_VERSION': '7.5.11',
        'INSTALLED_VERSION': '7.5.10',
        'BASE_BRANCH': 'main',
        'SLACK_CHANNEL': 'C0APV94Q1JP',
        'SLACK_THREAD_TS': '1788210459.939479',
    }

    def test_event_from_env_maps_all_keys(self):
        main, _, _ = _load_main()
        with patch.dict(os.environ, self._ENV, clear=False):
            event = main._event_from_env()
        assert event == {
            'repo_name': 'security-analytics-dashboards-plugin',
            'cve_id': 'CVE-2026-48779',
            'package': 'ws',
            'patched_version': '7.5.11',
            'installed_version': '7.5.10',
            'base_branch': 'main',
            'slack_channel': 'C0APV94Q1JP',
            'slack_thread_ts': '1788210459.939479',
        }

    def test_missing_env_vars_become_empty(self):
        main, _, _ = _load_main()
        minimal = {'REPO_NAME': 'r', 'CVE_ID': 'CVE-1', 'PACKAGE': 'p',
                   'PATCHED_VERSION': '1.0.0'}
        # Ensure the optional vars are absent from the environment.
        with patch.dict(os.environ, minimal, clear=True):
            event = main._event_from_env()
        assert event['repo_name'] == 'r'
        assert event['installed_version'] == ''
        assert event['base_branch'] == ''
        assert event['slack_channel'] == ''
        assert event['slack_thread_ts'] == ''

    def test_main_calls_handle_with_env_event_and_npm(self):
        main, npm, rem = _load_main()
        captured = {}

        def fake_handle(event, strategy):
            captured['event'] = event
            captured['strategy'] = strategy
            return {'status': 'success', 'pr_url': 'http://x/1'}

        with patch.object(rem, 'handle', side_effect=fake_handle), \
                patch.dict(os.environ, self._ENV, clear=False):
            rc = main.main()
        assert rc == 0
        assert captured['strategy'] is npm
        assert captured['event']['repo_name'] == 'security-analytics-dashboards-plugin'
        assert captured['event']['slack_thread_ts'] == '1788210459.939479'

    def test_main_returns_zero_on_no_change(self):
        main, _, rem = _load_main()
        with patch.object(rem, 'handle', return_value={'status': 'no_change'}), \
                patch.dict(os.environ, self._ENV, clear=False):
            assert main.main() == 0

    def test_main_returns_nonzero_on_error(self):
        main, _, rem = _load_main()
        with patch.object(rem, 'handle', return_value={'status': 'error', 'message': 'boom'}), \
                patch.dict(os.environ, self._ENV, clear=False):
            assert main.main() == 1


class TestRegenerateTimeout:
    """A hung yarn must fail fast (Fargate has no max task duration)."""

    def test_yarn_timeout_raises_remediation_error(self):
        npm, rem = _load_npm()
        with patch.object(npm.subprocess, 'run',
                          side_effect=subprocess.TimeoutExpired(cmd='yarn', timeout=1)):
            with pytest.raises(rem.RemediationError) as exc:
                npm.regenerate('/tmp/does-not-matter', {'method': 'install'})
        assert 'timed out' in str(exc.value)
