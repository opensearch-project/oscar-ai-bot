# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the maven ecosystem remediation strategy (remediation-workers/maven).

Covers the build.gradle declaration-finder + minimal-diff editing: force
literals, direct-dep literals, in-repo ext vars, the downgrade guard, and the
out-of-scope (RemediationUnsupported) cases — core-inherited ``${versions.X}``,
indirection, and undeclared coordinates. The git/GitHub side is the shared flow,
tested with the npm suite.
"""

import importlib.util
import os
from unittest.mock import patch

import pytest

_WORKERS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..',
    'agents', 'SecurityAdvisories', 'remediation-workers',
)
_MAVEN_PATH = os.path.join(_WORKERS_PATH, 'maven')
_SHARED_PATH = os.path.join(_WORKERS_PATH, 'shared')


def _load_maven():
    """Load maven.py with its ``remediation`` dependency injected."""
    rem_spec = importlib.util.spec_from_file_location(
        'remediation', os.path.join(_SHARED_PATH, 'remediation.py'))
    rem = importlib.util.module_from_spec(rem_spec)
    rem_spec.loader.exec_module(rem)
    with patch.dict('sys.modules', {'remediation': rem}):
        mav_spec = importlib.util.spec_from_file_location(
            'maven_strategy', os.path.join(_MAVEN_PATH, 'maven.py'))
        mav = importlib.util.module_from_spec(mav_spec)
        mav_spec.loader.exec_module(mav)
    return mav, rem


def _ctx(maven, package='org.apache.logging.log4j/log4j-core',
         patched='2.25.4', **over):
    e = {'repo_name': 'alerting', 'cve_id': 'CVE-2026-0001',
         'package': package, 'patched_version': patched,
         'installed_version': '2.20.0'}
    e.update(over)
    return maven.build_context(e, 'v-e-e-m-a', 'opensearch-project')


def _gradle(tmp_path, body, name='build.gradle'):
    (tmp_path / name).write_text(body)


def _read(tmp_path, name='build.gradle'):
    return (tmp_path / name).read_text()


class TestSharedContract:
    """Guards the shared symbols the maven worker's main.py depends on — a missing
    CLEAN_WORKER_STATUSES crashed the ECS entrypoint at exit despite a successful
    remediation."""

    def test_clean_worker_statuses_present(self):
        _, rem = _load_maven()
        assert set(("success", "no_change", "unsupported",
                    "remediation_in_progress")).issubset(rem.CLEAN_WORKER_STATUSES)

    def test_unsupported_exception_present(self):
        _, rem = _load_maven()
        assert issubclass(rem.RemediationUnsupported, rem.RemediationError)


class TestBuildContext:
    def test_coordinate_normalized_and_artifact_used(self):
        maven, _ = _load_maven()
        ctx = _ctx(maven)
        assert ctx['coordinate'] == 'org.apache.logging.log4j:log4j-core'
        assert ctx['artifact'] == 'log4j-core'
        # branch + title use the bare artifact, CVE stays out of the title
        assert ctx['branch_name'] == 'oscar/cve-2026-0001-log4j-core'
        assert ctx['pr_title'] == 'Bump log4j-core to 2.25.4'
        assert 'CVE-2026-0001' not in ctx['pr_title']
        assert 'CVE-2026-0001' in ctx['pr_body']

    def test_colon_form_also_accepted(self):
        maven, _ = _load_maven()
        ctx = _ctx(maven, package='com.google.guava:guava', patched='33.5.0-jre')
        assert ctx['coordinate'] == 'com.google.guava:guava'

    def test_missing_field_raises(self):
        maven, rem = _load_maven()
        with pytest.raises(rem.RemediationError):
            maven.build_context({'cve_id': 'x', 'repo_name': 'r', 'package': 'g:a'},
                                'w', 'b')


class TestApplyFix:
    def test_force_literal_edited(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, 'resolutionStrategy {\n'
                '  force "org.apache.logging.log4j:log4j-core:2.20.0"\n}\n')
        maven.apply_fix(str(tmp_path), _ctx(maven))
        assert 'log4j-core:2.25.4' in _read(tmp_path)
        assert '2.20.0' not in _read(tmp_path)

    def test_direct_dep_literal_edited(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, "dependencies {\n"
                "  implementation 'org.jsoup:jsoup:1.20.1'\n}\n")
        ctx = _ctx(maven, package='org.jsoup/jsoup', patched='1.22.2')
        maven.apply_fix(str(tmp_path), ctx)
        assert "jsoup:1.22.2" in _read(tmp_path)
        assert ctx['bumped_sections'] == ['build.gradle']

    def test_in_repo_ext_var_edited(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, "ext {\n  log4j_version = '2.20.0'\n}\n"
                'dependencies {\n'
                '  force "org.apache.logging.log4j:log4j-core:${log4j_version}"\n}\n')
        maven.apply_fix(str(tmp_path), _ctx(maven))
        assert "log4j_version = '2.25.4'" in _read(tmp_path)

    def test_ext_var_in_gradle_properties_edited(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, 'dependencies {\n'
                '  force "org.apache.logging.log4j:log4j-core:${log4j_version}"\n}\n')
        _gradle(tmp_path, 'log4j_version=2.20.0\n', name='gradle.properties')
        maven.apply_fix(str(tmp_path), _ctx(maven))
        assert 'log4j_version=2.25.4' in _read(tmp_path, 'gradle.properties')

    def test_multiple_files_all_edited(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, 'force "org.apache.logging.log4j:log4j-core:2.20.0"\n')
        sub = tmp_path / 'plugin'
        sub.mkdir()
        _gradle(sub, 'force "org.apache.logging.log4j:log4j-core:2.20.0"\n')
        ctx = _ctx(maven)
        maven.apply_fix(str(tmp_path), ctx)
        assert 'log4j-core:2.25.4' in _read(tmp_path)
        assert 'log4j-core:2.25.4' in _read(sub)
        assert len(ctx['bumped_sections']) == 2

    def test_already_at_or_above_makes_no_edit(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, 'force "org.apache.logging.log4j:log4j-core:2.25.4"\n')
        ctx = _ctx(maven)
        maven.apply_fix(str(tmp_path), ctx)  # no raise
        assert ctx['bumped_sections'] == []  # shared flow -> no_change

    def test_map_form_literal_edited(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, "dependencies {\n"
                "  compileOnly group: 'com.fasterxml.jackson.core', "
                "name: 'jackson-databind', version: '2.17.1'\n}\n")
        ctx = _ctx(maven, package='com.fasterxml.jackson.core/jackson-databind',
                   patched='2.18.8')
        maven.apply_fix(str(tmp_path), ctx)
        assert "version: '2.18.8'" in _read(tmp_path)
        assert ctx['bumped_sections'] == ['build.gradle']

    def test_map_form_core_var_unsupported(self, tmp_path):
        maven, rem = _load_maven()
        _gradle(tmp_path, "dependencies {\n"
                "  compileOnly(group: 'org.apache.httpcomponents.core5', "
                'name: \'httpcore5\', version: "${versions.httpcore5}")\n}\n')
        ctx = _ctx(maven, package='org.apache.httpcomponents.core5/httpcore5',
                   patched='5.4.3')
        with pytest.raises(rem.RemediationUnsupported) as exc:
            maven.apply_fix(str(tmp_path), ctx)
        # correctly identified as core-inherited, NOT "not declared"
        assert 'versions.httpcore5' in str(exc.value)

    def test_map_form_does_not_cross_edit_sibling_same_version(self, tmp_path):
        # jackson-databind + jackson-annotations both at 2.17.1: only the target
        # coordinate's line is edited (span-scoped edit, not a global replace).
        maven, _ = _load_maven()
        _gradle(tmp_path, "dependencies {\n"
                "  compileOnly group: 'com.fasterxml.jackson.core', "
                "name: 'jackson-databind', version: '2.17.1'\n"
                "  compileOnly group: 'com.fasterxml.jackson.core', "
                "name: 'jackson-annotations', version: '2.17.1'\n}\n")
        ctx = _ctx(maven, package='com.fasterxml.jackson.core/jackson-databind',
                   patched='2.18.8')
        maven.apply_fix(str(tmp_path), ctx)
        out = _read(tmp_path)
        assert "name: 'jackson-databind', version: '2.18.8'" in out
        assert "name: 'jackson-annotations', version: '2.17.1'" in out  # untouched

    def test_core_inherited_variable_unsupported(self, tmp_path):
        maven, rem = _load_maven()
        _gradle(tmp_path, 'force "org.apache.httpcomponents.core5:httpcore5:'
                '${versions.httpcore5}"\n')
        ctx = _ctx(maven, package='org.apache.httpcomponents.core5/httpcore5',
                   patched='5.4.3')
        with pytest.raises(rem.RemediationUnsupported) as exc:
            maven.apply_fix(str(tmp_path), ctx)
        assert 'versions.httpcore5' in str(exc.value)

    def test_undeclared_coordinate_unsupported(self, tmp_path):
        maven, rem = _load_maven()
        _gradle(tmp_path, 'force "com.google.guava:guava:31.1-jre"\n')
        ctx = _ctx(maven)  # log4j-core, not declared here
        with pytest.raises(rem.RemediationUnsupported) as exc:
            maven.apply_fix(str(tmp_path), ctx)
        assert 'not declared' in str(exc.value)

    def test_no_build_gradle_unsupported(self, tmp_path):
        maven, rem = _load_maven()
        with pytest.raises(rem.RemediationUnsupported):
            maven.apply_fix(str(tmp_path), _ctx(maven))

    def test_literal_and_var_same_file_both_applied(self, tmp_path):
        # Regression (review #1): a literal edit and a same-file ${var} bump must
        # both survive — the var bump must not be clobbered by the literal write.
        maven, _ = _load_maven()
        _gradle(tmp_path,
                "ext {\n  log4j_version = '2.20.0'\n}\n"
                "dependencies {\n"
                "  implementation \"org.apache.logging.log4j:log4j-core:2.20.0\"\n"
                "  force \"org.apache.logging.log4j:log4j-core:${log4j_version}\"\n}\n")
        maven.apply_fix(str(tmp_path), _ctx(maven))  # log4j-core -> 2.25.4
        out = _read(tmp_path)
        assert "log4j-core:2.25.4" in out          # literal bumped
        assert "log4j_version = '2.25.4'" in out    # var bumped (not reverted)
        assert "2.20.0" not in out

    def test_unbraced_gstring_var_resolved(self, tmp_path):
        # Review #7: `$var` (no braces) is a valid Groovy GString and resolvable.
        maven, _ = _load_maven()
        _gradle(tmp_path,
                "ext {\n  log4j_version = '2.20.0'\n}\n"
                'force "org.apache.logging.log4j:log4j-core:$log4j_version"\n')
        maven.apply_fix(str(tmp_path), _ctx(maven))
        assert "log4j_version = '2.25.4'" in _read(tmp_path)

    def test_variable_defined_in_multiple_files_all_edited(self, tmp_path):
        # Review #4: a var set in >1 file must be bumped in every file.
        maven, _ = _load_maven()
        _gradle(tmp_path,
                'force "org.apache.logging.log4j:log4j-core:${log4j_version}"\n')
        _gradle(tmp_path, 'log4j_version=2.20.0\n', name='gradle.properties')
        sub = tmp_path / 'core'
        sub.mkdir()
        _gradle(sub, "ext { log4j_version = '2.20.0' }\n")
        maven.apply_fix(str(tmp_path), _ctx(maven))
        assert 'log4j_version=2.25.4' in _read(tmp_path, 'gradle.properties')
        assert "log4j_version = '2.25.4'" in _read(sub)

    def test_already_patched_literal_but_corevar_still_unsupported(self, tmp_path):
        # Review #3: one declaration already-patched must NOT mask an unevaluated
        # core-inherited declaration as no_change — surface it for review.
        maven, rem = _load_maven()
        _gradle(tmp_path,
                'force "org.apache.logging.log4j:log4j-core:2.25.4"\n'
                'force "org.apache.logging.log4j:log4j-core:${versions.log4j}"\n')
        with pytest.raises(rem.RemediationUnsupported):
            maven.apply_fix(str(tmp_path), _ctx(maven))  # patched 2.25.4


class TestHelpers:
    def test_to_colon_coord(self):
        maven, _ = _load_maven()
        assert maven._to_colon_coord('io.netty/netty-common') == 'io.netty:netty-common'
        assert maven._to_colon_coord('io.netty:netty-common') == 'io.netty:netty-common'

    def test_var_name(self):
        maven, _ = _load_maven()
        assert maven._var_name('${log4j_version}') == 'log4j_version'
        assert maven._var_name('${versions.httpcore5}') is None  # dotted -> core
        assert maven._var_name("${props.getProperty('x')}") is None

    def test_at_or_above_with_qualifiers(self):
        # at_or_above is the shared version helper (remediation.py), used by both
        # ecosystems; maven exercises the qualifier cases.
        _, rem = _load_maven()
        assert rem.at_or_above('33.5.0-jre', '31.1') is True
        assert rem.at_or_above('2.20.0', '2.25.4') is False
        assert rem.at_or_above('weird', '1.0') is False  # unparseable -> proceed

    def test_regenerate_is_noop(self, tmp_path):
        maven, _ = _load_maven()
        assert maven.regenerate(str(tmp_path), {}) is None
