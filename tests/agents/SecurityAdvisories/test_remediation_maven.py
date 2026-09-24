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
import io
import json
import os
from unittest.mock import patch

import pytest

_WORKERS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..',
    'agents', 'SecurityAdvisories', 'remediation-workers',
)
_MAVEN_PATH = os.path.join(_WORKERS_PATH, 'maven')
_SHARED_PATH = os.path.join(_WORKERS_PATH, 'shared')

# Load the maven planner under a UNIQUE module name (the npm worker also has an
# `llm_planner`; a bare `import llm_planner` on sys.path would collide in
# sys.modules). We inject it as `llm_planner` only while loading maven.py below.
_llm_spec = importlib.util.spec_from_file_location(
    'maven_llm_planner', os.path.join(_MAVEN_PATH, 'llm_planner.py'))
llm_planner = importlib.util.module_from_spec(_llm_spec)
_llm_spec.loader.exec_module(llm_planner)

# The real plan_edit / write_force_edit, captured before the autouse fixture patches
# them out — lets a test drive the actual Bedrock parse path with only the client mocked.
_ORIG_PLAN_EDIT = llm_planner.plan_edit
_ORIG_WRITE_FORCE_EDIT = llm_planner.write_force_edit


@pytest.fixture(autouse=True)
def _llm_off_by_default():
    """Default the LLM OFF so tests exercise the deterministic paths. LLM-path tests
    override ``plan_edit`` / ``write_force_edit`` with their own return value."""
    with patch.object(llm_planner, 'plan_edit', return_value=None), \
         patch.object(llm_planner, 'write_force_edit', return_value=None):
        yield


def _load_maven():
    """Load maven.py with its ``remediation`` + ``llm_planner`` deps injected."""
    rem_spec = importlib.util.spec_from_file_location(
        'remediation', os.path.join(_SHARED_PATH, 'remediation.py'))
    rem = importlib.util.module_from_spec(rem_spec)
    rem_spec.loader.exec_module(rem)
    # Inject our planner as `llm_planner` only for maven.py's import (restored on
    # exit), so it never persists in sys.modules to collide with the npm suite.
    with patch.dict('sys.modules', {'remediation': rem, 'llm_planner': llm_planner}):
        mav_spec = importlib.util.spec_from_file_location(
            'maven_strategy', os.path.join(_MAVEN_PATH, 'maven.py'))
        mav = importlib.util.module_from_spec(mav_spec)
        mav_spec.loader.exec_module(mav)
    # Unit tests never hit the network: stub the core-catalog fetch to fail, so
    # _core_managed_version returns None (-> literal force / plain unsupported)
    # unless a test explicitly patches mav._core_managed_version / mav._http_get.
    # Keep the real _http_get accessible for its own direct test.
    mav._real_http_get = mav._http_get
    mav._http_get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network in tests"))
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


def _catalog(tmp_path, versions='log4j = "2.20.0"\n',
             libraries=('log4jcore = { group = "org.apache.logging.log4j", '
                        'name = "log4j-core", version.ref = "log4j" }\n'),
             gradlew=False):
    """Write a gradle/libs.versions.toml (marks a core-style repo)."""
    (tmp_path / 'gradle').mkdir(exist_ok=True)
    (tmp_path / 'gradle' / 'libs.versions.toml').write_text(
        f"[versions]\n{versions}\n[libraries]\n{libraries}")
    if gradlew:
        (tmp_path / 'gradlew').write_text("#!/bin/sh\n")


def _catalog_text(tmp_path):
    return (tmp_path / 'gradle' / 'libs.versions.toml').read_text()


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

    def test_origin_files_carried_onto_context(self):
        maven, _ = _load_maven()
        origin_files = ['libs/opensaml/build.gradle']
        ctx = _ctx(maven, origin_files=origin_files)
        assert ctx['origin_files'] == origin_files

    def test_origin_files_default_to_empty_list(self):
        # absent origin (npm-style event / release-tag scan) -> [], never None,
        # so the force path can iterate it unconditionally.
        maven, _ = _load_maven()
        ctx = _ctx(maven)
        assert ctx['origin_files'] == []

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

    def test_transitive_undeclared_adds_force_block(self, tmp_path):
        maven, _ = _load_maven()
        # commons-beanutils isn't declared here; it's pulled transitively. With the
        # transitive class, the worker pins it via a resolutionStrategy.force block.
        _gradle(tmp_path, "dependencies {\n  implementation 'org.jsoup:jsoup:1.20.1'\n}\n")
        ctx = _ctx(maven, package='commons-beanutils/commons-beanutils',
                   patched='1.11.0', declaration_class='transitive')
        maven.apply_fix(str(tmp_path), ctx)
        text = _read(tmp_path)
        assert 'allprojects {' in text
        assert 'resolutionStrategy' in text
        assert "force 'commons-beanutils:commons-beanutils:1.11.0'" in text
        assert ctx['bumped_sections'] == ['build.gradle (force)']

    def test_llm_force_edit_applied_when_verified(self, tmp_path):
        maven, _ = _load_maven()
        # Existing resolutionStrategy block; the (mocked) LLM folds the pin into it
        # rather than appending a fresh block. Verified edit is applied as-is.
        original = ("allprojects {\n  configurations.all {\n    resolutionStrategy {\n"
                    "      force 'com.example:foo:1.0'\n    }\n  }\n}\n")
        _gradle(tmp_path, original)
        ctx = _ctx(maven, package='org.apache.httpcomponents.core5/httpcore5',
                   patched='5.4.3', declaration_class='transitive')
        edit = {
            "old_string": "      force 'com.example:foo:1.0'",
            "new_string": "      force 'com.example:foo:1.0'\n"
                          "      force 'org.apache.httpcomponents.core5:httpcore5:5.4.3'",
        }
        with patch.object(llm_planner, 'write_force_edit', return_value=edit):
            maven.apply_fix(str(tmp_path), ctx)
        text = _read(tmp_path)
        assert "httpcore5:5.4.3" in text
        assert text.count("resolutionStrategy") == 1     # folded in, no new block
        assert ctx['bumped_sections'] == ['build.gradle (force, llm)']

    @pytest.mark.parametrize("original,old,new,expect_snippet", [
        # string force block:  force "g:a:v"
        ("configurations.all {\n  resolutionStrategy {\n"
         "    force 'com.example:foo:1.0'\n  }\n}\n",
         "    force 'com.example:foo:1.0'",
         "    force 'com.example:foo:1.0'\n"
         "    force 'org.apache.httpcomponents.core5:httpcore5:5.4.3'",
         "httpcore5:5.4.3"),
        # method force block:  force("g:a:v")
        ("subprojects {\n  configurations.all {\n    resolutionStrategy {\n"
         "      force(\"com.example:foo:1.0\")\n    }\n  }\n}\n",
         "      force(\"com.example:foo:1.0\")",
         "      force(\"com.example:foo:1.0\")\n"
         "      force(\"org.apache.httpcomponents.core5:httpcore5:5.4.3\")",
         'httpcore5:5.4.3'),
        # dotted form:  resolutionStrategy.force "g:a:v"
        ("subprojects {\n  configurations.all {\n"
         "    resolutionStrategy.force \"com.example:foo:1.0\"\n  }\n}\n",
         "    resolutionStrategy.force \"com.example:foo:1.0\"",
         "    resolutionStrategy.force \"com.example:foo:1.0\"\n"
         "    resolutionStrategy.force \"org.apache.httpcomponents.core5:httpcore5:5.4.3\"",
         "httpcore5:5.4.3"),
        # eachDependency / useVersion
        ("configurations.all {\n  resolutionStrategy {\n    eachDependency { d ->\n"
         "      if (d.requested.group == 'com.example') { d.useVersion '1.0' }\n"
         "    }\n  }\n}\n",
         "      if (d.requested.group == 'com.example') { d.useVersion '1.0' }",
         "      if (d.requested.group == 'com.example') { d.useVersion '1.0' }\n"
         "      if (d.requested.group == 'org.apache.httpcomponents.core5' && "
         "d.requested.name == 'httpcore5') { d.useVersion '5.4.3' }",
         "useVersion '5.4.3'"),
    ], ids=["string_force", "method_force", "dotted_force", "each_dependency"])
    def test_llm_force_edit_folds_into_each_idiom(self, tmp_path, original, old, new,
                                                  expect_snippet):
        maven, _ = _load_maven()
        _gradle(tmp_path, original)
        ctx = _ctx(maven, package='org.apache.httpcomponents.core5/httpcore5',
                   patched='5.4.3', declaration_class='transitive')
        with patch.object(llm_planner, 'write_force_edit',
                          return_value={"old_string": old, "new_string": new}):
            maven.apply_fix(str(tmp_path), ctx)
        text = _read(tmp_path)
        assert expect_snippet in text
        # folded into the existing block — no fresh allprojects block appended
        assert "// Pin" not in text
        assert ctx['bumped_sections'] == ['build.gradle (force, llm)']

    def test_llm_force_edit_nonunique_anchor_falls_back(self, tmp_path):
        maven, _ = _load_maven()
        # old_string appears twice -> ambiguous -> reject -> deterministic append.
        original = "force 'x:y:1'\nforce 'x:y:1'\n"
        _gradle(tmp_path, original)
        ctx = _ctx(maven, package='org.apache.httpcomponents.core5/httpcore5',
                   patched='5.4.3', declaration_class='transitive')
        edit = {"old_string": "force 'x:y:1'",
                "new_string": "force 'x:y:1'\nforce 'org.apache.httpcomponents.core5:httpcore5:5.4.3'"}
        with patch.object(llm_planner, 'write_force_edit', return_value=edit):
            maven.apply_fix(str(tmp_path), ctx)
        text = _read(tmp_path)
        assert "// Pin" in text                       # fell back to appended block
        assert ctx['bumped_sections'] == ['build.gradle (force)']

    def test_llm_force_edit_wrong_version_falls_back_to_append(self, tmp_path):
        maven, _ = _load_maven()
        original = "plugins { id 'java' }\n"
        _gradle(tmp_path, original)
        ctx = _ctx(maven, package='org.apache.httpcomponents.core5/httpcore5',
                   patched='5.4.3', declaration_class='transitive')
        # LLM returns a pin at the WRONG version -> verification rejects -> append.
        edit = {
            "old_string": "plugins { id 'java' }",
            "new_string": "plugins { id 'java' }\n"
                          "allprojects { configurations.all { resolutionStrategy {\n"
                          "  force 'org.apache.httpcomponents.core5:httpcore5:9.9.9'\n"
                          "} } }",
        }
        with patch.object(llm_planner, 'write_force_edit', return_value=edit):
            maven.apply_fix(str(tmp_path), ctx)
        text = _read(tmp_path)
        assert "httpcore5:5.4.3" in text            # deterministic append used
        assert "9.9.9" not in text
        assert ctx['bumped_sections'] == ['build.gradle (force)']

    def test_verify_force_edit_rules(self):
        maven, _ = _load_maven()
        base = "a\nb\n  force 'g:a:1.0'\n"
        # additions-only, correct pin -> ok
        good = "a\nb\n  force 'g:a:1.0'\n  force 'com.x:y:2.5.0'\n"
        assert maven._verify_force_edit(base, good, "com.x:y", "2.5.0") is True
        # removed/changed an existing line -> reject
        changed = "a\nB\n  force 'g:a:1.0'\n  force 'com.x:y:2.5.0'\n"
        assert maven._verify_force_edit(base, changed, "com.x:y", "2.5.0") is False
        # added a pin for a DIFFERENT version -> reject
        wrongver = base + "  force 'com.x:y:9.9.9'\n"
        assert maven._verify_force_edit(base, wrongver, "com.x:y", "2.5.0") is False
        # added a pin for ANOTHER dependency -> reject (token != patched)
        otherdep = base + "  force 'com.x:y:2.5.0'\n  force 'other:dep:3.0.0'\n"
        assert maven._verify_force_edit(base, otherdep, "com.x:y", "2.5.0") is False
        # no-op edit -> reject
        assert maven._verify_force_edit(base, base, "com.x:y", "2.5.0") is False

    def test_verify_force_edit_var_token(self):
        # expected_token is a ${versions.X} var (core-managed re-assert).
        maven, _ = _load_maven()
        base = 'a\nb\n  force "g:a:1.0"\n'
        tok = '${versions.jackson_databind}'
        # double-quoted GString pin at the var -> ok (no literal version introduced)
        good = base + f'  force "com.x:y:{tok}"\n'
        assert maven._verify_force_edit(base, good, "com.x:y", "2.5.0",
                                        expected_token=tok) is True
        # single-quoted (wouldn't interpolate) -> reject
        single = base + f"  force 'com.x:y:{tok}'\n"
        assert maven._verify_force_edit(base, single, "com.x:y", "2.5.0",
                                        expected_token=tok) is False
        # sneaks in a foreign literal version alongside the var -> reject
        sneaky = base + f'  force "com.x:y:{tok}"\n  force "z:w:9.9.9"\n'
        assert maven._verify_force_edit(base, sneaky, "com.x:y", "2.5.0",
                                        expected_token=tok) is False
        # sneaks in ANOTHER dep pinned via a var (colon form) -> reject (coord regex)
        sneaky_var = base + f'  force "com.x:y:{tok}"\n  force "z:w:{tok}"\n'
        assert maven._verify_force_edit(base, sneaky_var, "com.x:y", "2.5.0",
                                        expected_token=tok) is False
        # extra dep via eachDependency useVersion (var) — no foreign g:a: colon, so the
        # coord regex misses it; the "exactly one pin statement" check rejects it.
        sneaky_each = base + (f'  force "com.x:y:{tok}"\n'
                              f'  if (d.name == \'z\') {{ d.useVersion "{tok}" }}\n')
        assert maven._verify_force_edit(base, sneaky_each, "com.x:y", "2.5.0",
                                        expected_token=tok) is False

    def test_transitive_but_actually_declared_edits_declaration(self, tmp_path):
        maven, _ = _load_maven()
        # Stale scan says transitive, but the dep IS declared directly on HEAD:
        # the deterministic scan finds it and edits the literal — no force block.
        _gradle(tmp_path, "dependencies {\n  implementation 'org.jsoup:jsoup:1.20.1'\n}\n")
        ctx = _ctx(maven, package='org.jsoup/jsoup', patched='1.22.2',
                   declaration_class='transitive')
        maven.apply_fix(str(tmp_path), ctx)
        text = _read(tmp_path)
        assert 'jsoup:1.22.2' in text
        assert 'allprojects {' not in text          # forced path NOT taken
        assert ctx['bumped_sections'] == ['build.gradle']

    def test_core_inherited_undeclared_is_unsupported_not_forced(self, tmp_path):
        maven, rem = _load_maven()
        # Transitive only via org.opensearch.* -> core-inherited: manual review, no force.
        _gradle(tmp_path, "dependencies {\n  implementation 'org.jsoup:jsoup:1.20.1'\n}\n")
        ctx = _ctx(maven, package='org.apache.httpcomponents.client5/httpclient5',
                   patched='5.6.4', declaration_class='core_inherited')
        with pytest.raises(rem.RemediationUnsupported) as exc:
            maven.apply_fix(str(tmp_path), ctx)
        assert 'core' in str(exc.value).lower()
        assert 'allprojects {' not in _read(tmp_path)   # no force block written

    def test_core_inherited_message_enriched_with_core_version(self, tmp_path):
        # core_inherited + core confirmed on a vulnerable version -> the decline names
        # core's actual version and points the fix at core (the safeguard message).
        maven, rem = _load_maven()
        _gradle(tmp_path, "dependencies {\n  implementation 'org.jsoup:jsoup:1.20.1'\n}\n")
        maven._core_managed_version = lambda coord: '5.6.0'   # core below patched
        ctx = _ctx(maven, package='org.apache.httpcomponents.client5/httpclient5',
                   patched='5.6.4', declaration_class='core_inherited')
        with pytest.raises(rem.RemediationUnsupported) as exc:
            maven.apply_fix(str(tmp_path), ctx)
        msg = str(exc.value)
        assert '5.6.0' in msg and 'vulnerable' in msg.lower() and 'core' in msg.lower()

    def test_undeclared_unknown_class_stays_unsupported(self, tmp_path):
        maven, rem = _load_maven()
        # No declaration and no transitive signal -> unchanged unsupported behavior.
        _gradle(tmp_path, 'force "com.google.guava:guava:31.1-jre"\n')
        ctx = _ctx(maven)  # declaration_class defaults to 'unknown'
        with pytest.raises(rem.RemediationUnsupported):
            maven.apply_fix(str(tmp_path), ctx)

    def test_transitive_no_root_build_gradle_unsupported(self, tmp_path):
        maven, rem = _load_maven()
        # Transitive, but the only build.gradle is in a submodule (no root to force
        # in) -> unsupported rather than a misplaced block.
        sub = tmp_path / 'plugin'
        sub.mkdir()
        _gradle(sub, "dependencies {\n  implementation 'org.jsoup:jsoup:1.20.1'\n}\n")
        ctx = _ctx(maven, package='commons-beanutils/commons-beanutils',
                   patched='1.11.0', declaration_class='transitive')
        with pytest.raises(rem.RemediationUnsupported) as exc:
            maven.apply_fix(str(tmp_path), ctx)
        assert 'root build.gradle' in str(exc.value)

    def test_transitive_single_origin_file_forces_in_submodule(self, tmp_path):
        # opensaml pattern: undeclared transitive resolving through ONE submodule ->
        # force in that submodule's own configurations.all (not root allprojects).
        maven, _ = _load_maven()
        (tmp_path / 'build.gradle').write_text("plugins { id 'java' }\n")  # root, not target
        sub = tmp_path / 'libs' / 'opensaml'
        sub.mkdir(parents=True)
        (sub / 'build.gradle').write_text(
            "configurations.all {\n  resolutionStrategy {\n    force 'x:y:1.0'\n  }\n}\n")
        ctx = _ctx(maven, package='com.fasterxml.jackson.core/jackson-databind',
                   patched='2.21.5', declaration_class='transitive',
                   origin_files=['libs/opensaml/build.gradle'])
        maven.apply_fix(str(tmp_path), ctx)
        sub_text = (sub / 'build.gradle').read_text()
        assert 'jackson-databind:2.21.5' in sub_text
        assert 'allprojects {' not in sub_text          # submodule scope, not root
        assert ctx['bumped_sections'] == ['libs/opensaml/build.gradle (force)']
        assert 'jackson' not in (tmp_path / 'build.gradle').read_text()  # root untouched

    def test_transitive_multiple_origin_files_falls_back_to_root(self, tmp_path):
        # jetty pattern: undeclared transitive resolving through several modules ->
        # no single owner -> root allprojects cascade (main-faithful; precise
        # per-owner handling is deferred, see todo-follow-ups.md). Not declined.
        maven, _ = _load_maven()
        (tmp_path / 'build.gradle').write_text("plugins { id 'java' }\n")
        for rel in ('plugins/repository-hdfs', 'test/fixtures/hdfs-fixture'):
            d = tmp_path / rel
            d.mkdir(parents=True)
            (d / 'build.gradle').write_text("dependencies {}\n")
        origin_files = ['build.gradle', 'plugins/repository-hdfs/build.gradle',
                        'test/fixtures/hdfs-fixture/build.gradle']
        ctx = _ctx(maven, package='org.eclipse.jetty/jetty-http', patched='12.0.31',
                   declaration_class='transitive', origin_files=origin_files)
        maven.apply_fix(str(tmp_path), ctx)
        text = (tmp_path / 'build.gradle').read_text()   # root cascade
        assert 'allprojects {' in text
        assert 'org.eclipse.jetty:jetty-http:12.0.31' in text
        assert ctx['bumped_sections'] == ['build.gradle (force)']
        # submodules untouched (the pin cascades from root)
        assert 'jetty' not in (tmp_path / 'test/fixtures/hdfs-fixture/build.gradle').read_text()

    # --- security#6550 pattern: jackson-databind "declared" only via a core-managed
    # ${versions.jackson_databind} (root force + implementation), but a submodule BOM
    # (libs/opensaml -> jackson-bom) overrides it. Scan classifies transitive, origin
    # names libs/opensaml -> force there (NOT core_inherited unsupported, NOT root).
    # The version form depends on what core resolves the var to. ---

    @staticmethod
    def _security_opensaml_tree(tmp_path):
        (tmp_path / 'build.gradle').write_text(
            'configurations { all { resolutionStrategy {\n'
            '  force "com.fasterxml.jackson.core:jackson-databind:${versions.jackson_databind}"\n'
            '} } }\n'
            'dependencies {\n'
            '  implementation "com.fasterxml.jackson.core:jackson-databind:${versions.jackson_databind}"\n'
            '}\n')
        sub = tmp_path / 'libs' / 'opensaml'
        sub.mkdir(parents=True)
        (sub / 'build.gradle').write_text(
            'configurations.all {\n  resolutionStrategy {\n'
            '    force "org.apache.commons:commons-lang3:3.18.0"\n  }\n}\n')
        # origin_files as the Lambda distills it (single resolving module)
        return ['libs/opensaml/build.gradle']

    def test_core_var_reuses_var_when_core_patched(self, tmp_path):
        # core manages jackson_databind at >= patched -> re-assert the maintainer's
        # ${versions.jackson_databind} in libs/opensaml (double-quoted GString).
        maven, _ = _load_maven()
        origin_files = self._security_opensaml_tree(tmp_path)
        maven._core_managed_version = lambda coord: '2.22.2'   # core is patched
        ctx = _ctx(maven, package='com.fasterxml.jackson.core/jackson-databind',
                   patched='2.22.0', declaration_class='transitive', origin_files=origin_files)
        maven.apply_fix(str(tmp_path), ctx)
        sub_text = (tmp_path / 'libs' / 'opensaml' / 'build.gradle').read_text()
        assert ('force "com.fasterxml.jackson.core:jackson-databind:'
                '${versions.jackson_databind}"') in sub_text        # var, double-quoted
        assert '2.22.0' not in sub_text                             # no literal pin
        assert ctx['bumped_sections'] == ['libs/opensaml/build.gradle (force)']

    def test_core_var_folds_into_existing_block_via_llm(self, tmp_path):
        # var pin + LLM available -> fold one line into libs/opensaml's EXISTING
        # configurations.all (maintainer style), not a fresh appended block.
        maven, _ = _load_maven()
        origin_files = self._security_opensaml_tree(tmp_path)
        maven._core_managed_version = lambda coord: '2.22.2'   # core patched -> var
        fold = {
            "old_string": '    force "org.apache.commons:commons-lang3:3.18.0"',
            "new_string": '    force "org.apache.commons:commons-lang3:3.18.0"\n'
                          '    force "com.fasterxml.jackson.core:jackson-databind:'
                          '${versions.jackson_databind}"',
        }
        ctx = _ctx(maven, package='com.fasterxml.jackson.core/jackson-databind',
                   patched='2.22.0', declaration_class='transitive', origin_files=origin_files)
        with patch.object(llm_planner, 'write_force_edit', return_value=fold):
            maven.apply_fix(str(tmp_path), ctx)
        sub_text = (tmp_path / 'libs' / 'opensaml' / 'build.gradle').read_text()
        assert ('force "com.fasterxml.jackson.core:jackson-databind:'
                '${versions.jackson_databind}"') in sub_text     # var, double-quoted
        assert sub_text.count('configurations.all {') == 1       # folded, not appended
        assert '// Pin' not in sub_text                          # no fresh block
        assert ctx['bumped_sections'] == ['libs/opensaml/build.gradle (force, llm)']

    def test_core_var_llm_single_quote_rejected_falls_back(self, tmp_path):
        # LLM emits a single-quoted GString (wouldn't interpolate) -> verify rejects
        # -> deterministic append with correct double quotes.
        maven, _ = _load_maven()
        origin_files = self._security_opensaml_tree(tmp_path)
        maven._core_managed_version = lambda coord: '2.22.2'
        bad = {
            "old_string": '    force "org.apache.commons:commons-lang3:3.18.0"',
            "new_string": '    force "org.apache.commons:commons-lang3:3.18.0"\n'
                          "    force 'com.fasterxml.jackson.core:jackson-databind:"
                          "${versions.jackson_databind}'",   # single quotes -> invalid
        }
        ctx = _ctx(maven, package='com.fasterxml.jackson.core/jackson-databind',
                   patched='2.22.0', declaration_class='transitive', origin_files=origin_files)
        with patch.object(llm_planner, 'write_force_edit', return_value=bad):
            maven.apply_fix(str(tmp_path), ctx)
        sub_text = (tmp_path / 'libs' / 'opensaml' / 'build.gradle').read_text()
        assert '// Pin' in sub_text                              # fell back to append
        assert ('force "com.fasterxml.jackson.core:jackson-databind:'
                '${versions.jackson_databind}"') in sub_text     # double-quoted append
        assert ctx['bumped_sections'] == ['libs/opensaml/build.gradle (force)']

    def test_core_vulnerable_declines_fix_in_core(self, tmp_path):
        # core itself is below patched -> the fix belongs in core; decline with a
        # concrete message naming core's vulnerable version.
        maven, rem = _load_maven()
        origin_files = self._security_opensaml_tree(tmp_path)
        maven._core_managed_version = lambda coord: '2.21.4'   # core still vulnerable
        ctx = _ctx(maven, package='com.fasterxml.jackson.core/jackson-databind',
                   patched='2.22.0', declaration_class='transitive', origin_files=origin_files)
        with pytest.raises(rem.RemediationUnsupported) as exc:
            maven.apply_fix(str(tmp_path), ctx)
        assert '2.21.4' in str(exc.value) and 'core' in str(exc.value).lower()
        # nothing forced in the submodule
        assert 'jackson-databind' not in \
            (tmp_path / 'libs' / 'opensaml' / 'build.gradle').read_text()

    def test_core_var_lookup_unavailable_falls_back_to_literal(self, tmp_path):
        # core lookup unavailable (network stubbed off in _load_maven) -> literal
        # patched force in libs/opensaml (always fixes the CVE), never a wrong decline.
        maven, _ = _load_maven()
        origin_files = self._security_opensaml_tree(tmp_path)
        ctx = _ctx(maven, package='com.fasterxml.jackson.core/jackson-databind',
                   patched='2.22.0', declaration_class='transitive', origin_files=origin_files)
        maven.apply_fix(str(tmp_path), ctx)
        sub_text = (tmp_path / 'libs' / 'opensaml' / 'build.gradle').read_text()
        assert 'com.fasterxml.jackson.core:jackson-databind:2.22.0' in sub_text  # literal
        assert '${versions.jackson_databind}' not in sub_text.split('commons-lang3')[-1]
        assert ctx['bumped_sections'] == ['libs/opensaml/build.gradle (force)']

    def test_transitive_absent_origin_file_falls_back_to_root(self, tmp_path):
        # origin names a module not in this (fork's) tree -> ignored -> root fallback
        # (allprojects cascade), preserving the pre-origin behavior.
        maven, _ = _load_maven()
        (tmp_path / 'build.gradle').write_text("plugins { id 'java' }\n")
        ctx = _ctx(maven, package='com.x/y', patched='2.0.0',
                   declaration_class='transitive',
                   origin_files=['libs/ghost/build.gradle'])
        maven.apply_fix(str(tmp_path), ctx)
        text = (tmp_path / 'build.gradle').read_text()
        assert 'allprojects {' in text                  # root fallback cascades
        assert 'com.x:y:2.0.0' in text
        assert ctx['bumped_sections'] == ['build.gradle (force)']

    def test_no_build_gradle_unsupported(self, tmp_path):
        maven, rem = _load_maven()
        with pytest.raises(rem.RemediationUnsupported):
            maven.apply_fix(str(tmp_path), _ctx(maven))

    def test_transitive_bare_core_var_forces_literal(self, tmp_path):
        # transitive dep referenced via a bare ${var} not defined in-repo (core-
        # inherited) -> recorded as a core_force_var; force falls back to literal
        # (core lookup stubbed unavailable). Exercises the bare-var force_var path.
        maven, _ = _load_maven()
        _gradle(tmp_path, 'dependencies {\n  force "com.x:y:${some_core_var}"\n}\n')
        ctx = _ctx(maven, package='com.x/y', patched='2.0.0',
                   declaration_class='transitive', origin_files=['build.gradle'])
        maven.apply_fix(str(tmp_path), ctx)
        text = _read(tmp_path)
        assert 'com.x:y:2.0.0' in text                     # literal force appended
        assert ctx['bumped_sections'] == ['build.gradle (force)']

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

    def test_variable_assigned_twice_in_one_file_all_edited(self, tmp_path):
        # Review: a var set more than once in the SAME file must be bumped at every
        # occurrence, not just the first.
        maven, _ = _load_maven()
        _gradle(tmp_path,
                "ext { log4j_version = '2.20.0' }\n"
                "subprojects { ext { log4j_version = '2.20.0' } }\n"
                'dependencies {\n'
                '  force "org.apache.logging.log4j:log4j-core:${log4j_version}"\n}\n')
        maven.apply_fix(str(tmp_path), _ctx(maven))
        text = _read(tmp_path)
        assert text.count("log4j_version = '2.25.4'") == 2   # both assignments bumped
        assert "2.20.0" not in text

    def test_versions_map_key_defined_twice_in_one_file_all_edited(self, tmp_path):
        # Same multi-occurrence fix for the module-local `versions` map form.
        maven, _ = _load_maven()
        _gradle(tmp_path,
                "versions << ['log4j': '2.20.0']\n"
                "subprojects { versions << ['log4j': '2.20.0'] }\n"
                'dependencies {\n'
                '  force "org.apache.logging.log4j:log4j-core:${versions.log4j}"\n}\n')
        maven.apply_fix(str(tmp_path), _ctx(maven))
        text = _read(tmp_path)
        assert text.count("'log4j': '2.25.4'") == 2   # both map entries bumped
        assert "2.20.0" not in text

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

    def test_resolving_build_files_distinct_present_only(self, tmp_path):
        maven, _ = _load_maven()
        (tmp_path / 'build.gradle').write_text('x')
        sub = tmp_path / 'libs' / 'opensaml'
        sub.mkdir(parents=True)
        (sub / 'build.gradle').write_text('x')
        origin_files = [
            'build.gradle',
            'build.gradle',                     # dup -> de-duped
            'libs/opensaml/build.gradle',
            'libs/ghost/build.gradle',          # absent in clone -> dropped
            'io.netty-netty-bom@4.2.18.Final',  # not a build.gradle path -> ignored
        ]
        assert maven._resolving_build_files(str(tmp_path), origin_files) == [
            'build.gradle', 'libs/opensaml/build.gradle']

    def test_resolving_build_files_empty_or_absent_origin(self, tmp_path):
        maven, _ = _load_maven()
        assert maven._resolving_build_files(str(tmp_path), []) == []
        assert maven._resolving_build_files(str(tmp_path), None) == []

    def test_force_block_root_uses_allprojects(self):
        maven, _ = _load_maven()
        ctx = _ctx(maven, package='com.x/y', patched='2.0.0')
        block = maven._force_block(ctx, 'com.x:y:2.0.0', 'build.gradle')
        assert 'allprojects {' in block and "force 'com.x:y:2.0.0'" in block

    def test_force_block_submodule_omits_allprojects(self):
        maven, _ = _load_maven()
        ctx = _ctx(maven, package='com.x/y', patched='2.0.0')
        block = maven._force_block(ctx, 'com.x:y:2.0.0', 'libs/opensaml/build.gradle')
        assert 'allprojects {' not in block
        assert 'configurations.all {' in block and "force 'com.x:y:2.0.0'" in block

    def test_gradle_sources_reads_each_file_once(self, tmp_path, monkeypatch):
        # Regression guard: files were previously read twice (once for the sort
        # key, once in the loop body). They must now be read exactly once.
        maven, _ = _load_maven()
        _gradle(tmp_path, 'force "org.apache.logging.log4j:log4j-core:2.20.0"\n')
        sub = tmp_path / 'plugins' / 'p'
        sub.mkdir(parents=True)
        _gradle(sub, 'implementation "com.other:thing:1.0"\n')
        reads = []
        real_read = maven._read

        def counting_read(path):
            reads.append(path)
            return real_read(path)

        monkeypatch.setattr(maven, '_read', counting_read)
        maven._gradle_sources(str(tmp_path), 'org.apache.logging.log4j:log4j-core')
        assert len(reads) == len(set(reads)) == 2  # each file once, no re-reads

    def test_gradle_sources_ranks_artifact_file_first(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, 'implementation "com.other:thing:1.0"\n')  # no mention
        sub = tmp_path / 'plugins' / 'p'
        sub.mkdir(parents=True)
        _gradle(sub, 'force "org.apache.logging.log4j:log4j-core:2.20.0"\n')
        out = maven._gradle_sources(str(tmp_path),
                                    'org.apache.logging.log4j:log4j-core')
        assert out.index('log4j-core') < out.index('com.other')


class TestLlmPlan:
    """LLM planner path: verified edit plans are applied; everything else defers to
    the deterministic scanner, so the LLM can only cause a *verified* edit — never
    a wrong abstain or wrong no-change."""

    def test_edit_literal_plan_applied(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, 'resolutionStrategy {\n'
                '  force "org.apache.logging.log4j:log4j-core:2.20.0"\n}\n')
        plan = {'action': 'edit_literal', 'file': 'build.gradle',
                'target': '2.20.0', 'reason': 'r'}
        with patch.object(llm_planner, 'plan_edit', return_value=plan):
            maven.apply_fix(str(tmp_path), _ctx(maven))
        assert 'log4j-core:2.25.4' in _read(tmp_path)

    def test_truncated_output_warns_and_falls_back(self, caplog):
        # stop_reason=max_tokens -> the JSON is cut off, so _validate fails and
        # plan_edit returns None (scanner fallback). We must log it as a WARNING
        # naming max_tokens rather than fail silently like any other parse error.
        import io
        import json as _json
        payload = {
            'stop_reason': 'max_tokens',
            'usage': {'input_tokens': 5789, 'output_tokens': llm_planner.MAX_TOKENS},
            'content': [{'type': 'text', 'text': '{"action": "cata'}],  # truncated
        }
        fake = type('C', (), {'invoke_model': lambda self, **kw: {
            'body': io.BytesIO(_json.dumps(payload).encode())}})()
        ctx = {'coordinate': 'g:a', 'patched_version': '2.0', 'installed_version': '1.0'}
        with patch.object(llm_planner, '_runtime', return_value=fake), \
                caplog.at_level('WARNING'):
            assert _ORIG_PLAN_EDIT(ctx, 'sources', mode='catalog') is None
        assert any('max_tokens' in r.message and r.levelname == 'WARNING'
                   for r in caplog.records)

    def test_edit_ext_var_plan_applied(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, "ext {\n  log4j_version = '2.20.0'\n}\n"
                'dependencies {\n'
                '  force "org.apache.logging.log4j:log4j-core:${log4j_version}"\n}\n')
        plan = {'action': 'edit_ext_var', 'file': 'build.gradle',
                'target': 'log4j_version', 'reason': 'r'}
        with patch.object(llm_planner, 'plan_edit', return_value=plan):
            maven.apply_fix(str(tmp_path), _ctx(maven))
        assert "log4j_version = '2.25.4'" in _read(tmp_path)

    def test_out_of_scope_plan_defers_to_scanner(self, tmp_path):
        # LLM says out_of_scope, but the coordinate IS an editable literal — the
        # scanner still edits it, so a wrong out_of_scope can't cause a bad abstain.
        maven, _ = _load_maven()
        _gradle(tmp_path, 'resolutionStrategy {\n'
                '  force "org.apache.logging.log4j:log4j-core:2.20.0"\n}\n')
        plan = {'action': 'out_of_scope', 'file': '', 'target': '', 'reason': 'x'}
        with patch.object(llm_planner, 'plan_edit', return_value=plan):
            maven.apply_fix(str(tmp_path), _ctx(maven))
        assert 'log4j-core:2.25.4' in _read(tmp_path)

    def test_unverifiable_edit_literal_defers_to_scanner(self, tmp_path):
        # Plan claims edit_literal but the coordinate isn't declared -> fall back ->
        # the scanner authoritatively reports out-of-scope (not declared).
        maven, rem = _load_maven()
        _gradle(tmp_path, "dependencies {\n  implementation 'other:thing:1.0'\n}\n")
        plan = {'action': 'edit_literal', 'file': 'build.gradle',
                'target': '2.20.0', 'reason': 'r'}
        with patch.object(llm_planner, 'plan_edit', return_value=plan):
            with pytest.raises(rem.RemediationUnsupported):
                maven.apply_fix(str(tmp_path), _ctx(maven))


class TestCoreCatalog:
    """Core (version-catalog) path: a gradle/libs.versions.toml routes apply_fix to
    the catalog editor, and regenerate runs ./gradlew updateShas to rewrite the
    .jar.sha1 checksums. The deterministic [libraries]->version.ref lookup is
    authoritative; the LLM only supplies a verified [versions] key."""

    def test_catalog_presence_marks_core_and_bumps_version_ref(self, tmp_path):
        maven, _ = _load_maven()
        _catalog(tmp_path)  # log4j = 2.20.0, log4jcore -> version.ref log4j
        ctx = _ctx(maven)   # log4j-core, patched 2.25.4
        maven.apply_fix(str(tmp_path), ctx)
        assert ctx['is_core'] is True
        assert 'log4j = "2.25.4"' in _catalog_text(tmp_path)
        assert ctx['bumped_sections'] == ['log4j (catalog)']

    def test_catalog_already_at_or_above_is_no_change(self, tmp_path):
        maven, _ = _load_maven()
        _catalog(tmp_path, versions='log4j = "2.25.4"\n')
        ctx = _ctx(maven)
        maven.apply_fix(str(tmp_path), ctx)  # no raise
        assert ctx['bumped_sections'] == []           # shared flow -> no_change
        assert 'log4j = "2.25.4"' in _catalog_text(tmp_path)

    def test_coordinate_absent_from_catalog_falls_back_to_scanner(self, tmp_path):
        # Not in the catalog -> fall back to the build.gradle scanner. Here the
        # coordinate is declared as a literal in a submodule, so it's editable.
        maven, _ = _load_maven()
        _catalog(tmp_path,  # only a guava entry; log4j-core has no [libraries] row
                 libraries='guava = { group = "com.google.guava", name = "guava", '
                           'version.ref = "guava" }\n',
                 versions='guava = "31.1-jre"\n')
        sub = tmp_path / 'plugins' / 'p'
        sub.mkdir(parents=True)
        _gradle(sub, 'force "org.apache.logging.log4j:log4j-core:2.20.0"\n')
        ctx = _ctx(maven)  # log4j-core, patched 2.25.4
        maven.apply_fix(str(tmp_path), ctx)
        assert ctx['is_core'] is True
        assert 'log4j-core:2.25.4' in _read(sub, 'build.gradle')

    def test_llm_catalog_plan_applied(self, tmp_path):
        maven, _ = _load_maven()
        _catalog(tmp_path)
        plan = {'action': 'catalog', 'file': 'gradle/libs.versions.toml',
                'target': 'log4j', 'reason': 'r'}
        with patch.object(llm_planner, 'plan_edit', return_value=plan):
            maven.apply_fix(str(tmp_path), _ctx(maven))
        assert 'log4j = "2.25.4"' in _catalog_text(tmp_path)

    def test_llm_catalog_plan_with_bogus_key_defers_to_lookup(self, tmp_path):
        # LLM names a [versions] key that doesn't exist -> not verified -> the
        # deterministic [libraries] lookup still finds the right key and bumps it.
        maven, _ = _load_maven()
        _catalog(tmp_path)
        plan = {'action': 'catalog', 'file': 'gradle/libs.versions.toml',
                'target': 'not_a_real_key', 'reason': 'r'}
        with patch.object(llm_planner, 'plan_edit', return_value=plan):
            maven.apply_fix(str(tmp_path), _ctx(maven))
        assert 'log4j = "2.25.4"' in _catalog_text(tmp_path)

    def test_regenerate_runs_gradlew_updateshas_for_core(self, tmp_path):
        maven, _ = _load_maven()
        _catalog(tmp_path, gradlew=True)
        ctx = _ctx(maven)
        ctx['is_core'] = True
        ctx['bumped_sections'] = ['log4j (catalog)']
        with patch.object(maven.subprocess, 'run') as run:
            run.return_value = type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
            maven.regenerate(str(tmp_path), ctx)
        args = run.call_args[0][0]
        assert args[0] == './gradlew' and 'updateShas' in args

    def test_regenerate_raises_when_gradlew_fails(self, tmp_path):
        maven, rem = _load_maven()
        _catalog(tmp_path, gradlew=True)
        ctx = _ctx(maven)
        ctx['is_core'] = True
        ctx['bumped_sections'] = ['log4j (catalog)']
        with patch.object(maven.subprocess, 'run') as run:
            run.return_value = type('R', (), {'returncode': 1, 'stdout': '',
                                              'stderr': 'boom'})()
            with pytest.raises(rem.RemediationError):
                maven.regenerate(str(tmp_path), ctx)

    def test_regenerate_skipped_for_plugin_and_on_no_change(self, tmp_path):
        maven, _ = _load_maven()
        with patch.object(maven.subprocess, 'run') as run:
            maven.regenerate(str(tmp_path), {'is_core': False,
                                             'bumped_sections': ['build.gradle']})
            maven.regenerate(str(tmp_path), {'is_core': True,
                                             'bumped_sections': []})
            run.assert_not_called()

    def test_regenerate_core_without_wrapper_raises(self, tmp_path):
        maven, rem = _load_maven()
        _catalog(tmp_path)  # no gradlew
        with pytest.raises(rem.RemediationError) as exc:
            maven.regenerate(str(tmp_path),
                             {'is_core': True, 'repo_name': 'OpenSearch',
                              'bumped_sections': ['log4j (catalog)']})
        assert 'gradlew' in str(exc.value)


class TestCoreSubmodule:
    """Core repos declare some deps outside the catalog, in a submodule build.gradle
    (often a module-local ``versions << ['X': '...']`` map used as ${versions.X}).
    A catalog miss falls back to the LLM-first build.gradle path; regenerate still
    runs updateShas because it's a core repo."""

    def _hive(self, tmp_path):
        _catalog(tmp_path, gradlew=True)   # core marker; libthrift NOT in catalog
        sub = tmp_path / 'plugins' / 'ingestion-hive'
        sub.mkdir(parents=True)
        _gradle(sub, "versions << [\n  'thrift': '0.23.0',\n]\n"
                "dependencies {\n"
                '  api "org.apache.thrift:libthrift:${versions.thrift}"\n}\n')
        return sub

    def test_submodule_versions_map_bumped_via_scanner(self, tmp_path):
        # LLM off (autouse) -> deterministic scanner locates + bumps the map entry.
        maven, _ = _load_maven()
        sub = self._hive(tmp_path)
        ctx = _ctx(maven, package='org.apache.thrift/libthrift', patched='0.24.0')
        maven.apply_fix(str(tmp_path), ctx)
        assert ctx['is_core'] is True
        assert "'thrift': '0.24.0'" in _read(sub, 'build.gradle')
        assert ctx['bumped_sections'] == ['versions.thrift (variable)']

    def test_llm_edit_ext_var_plan_bumps_versions_map(self, tmp_path):
        # LLM routes ${versions.thrift} as edit_ext_var target=thrift; _apply_plan
        # now resolves it via the versions-map (not just plain `thrift = ...`).
        maven, _ = _load_maven()
        _gradle(tmp_path, "versions << [ 'thrift': '0.23.0' ]\n"
                'api "org.apache.thrift:libthrift:${versions.thrift}"\n')
        plan = {'action': 'edit_ext_var', 'file': 'build.gradle',
                'target': 'thrift', 'reason': 'r'}
        ctx = _ctx(maven, package='org.apache.thrift/libthrift', patched='0.24.0')
        with patch.object(llm_planner, 'plan_edit', return_value=plan):
            maven.apply_fix(str(tmp_path), ctx)
        assert "'thrift': '0.24.0'" in _read(tmp_path)
        assert ctx['bumped_sections'] == ['versions.thrift (variable)']

    def test_core_inherited_versions_key_still_unsupported(self, tmp_path):
        # ${versions.X} with NO in-repo definition = inherited from core -> unsupported.
        maven, rem = _load_maven()
        _catalog(tmp_path)
        sub = tmp_path / 'plugins' / 'x'
        sub.mkdir(parents=True)
        _gradle(sub, 'api "org.apache.httpcomponents.core5:httpcore5:'
                '${versions.httpcore5}"\n')
        ctx = _ctx(maven, package='org.apache.httpcomponents.core5/httpcore5',
                   patched='5.4.3')
        with pytest.raises(rem.RemediationUnsupported) as exc:
            maven.apply_fix(str(tmp_path), ctx)
        assert 'versions.httpcore5' in str(exc.value)

    def test_core_coordinate_undeclared_anywhere_unsupported(self, tmp_path):
        maven, rem = _load_maven()
        _catalog(tmp_path)  # libthrift not in catalog...
        _gradle(tmp_path, "dependencies { api 'other:thing:1.0' }\n")  # ...nor here
        ctx = _ctx(maven, package='org.apache.thrift/libthrift', patched='0.24.0')
        with pytest.raises(rem.RemediationUnsupported):
            maven.apply_fix(str(tmp_path), ctx)


class TestCoreHelpers:
    def test_core_managed_version_resolves_via_catalog(self):
        # fetch core catalog (stubbed) -> [libraries] group+name -> version.ref ->
        # [versions] value. Exercises the real parsing without touching the network.
        maven, _ = _load_maven()
        catalog = ('[versions]\njackson_databind = "2.22.2"\nother = "1.0"\n'
                   '[libraries]\njackson-databind = { group = "com.fasterxml.jackson.core", '
                   'name = "jackson-databind", version.ref = "jackson_databind" }\n')
        maven._http_get = lambda *a, **k: catalog
        assert maven._core_managed_version(
            'com.fasterxml.jackson.core:jackson-databind') == '2.22.2'
        # coordinate core doesn't manage -> None
        assert maven._core_managed_version('com.example:absent') is None

    def test_core_managed_version_network_failure_returns_none(self):
        maven, _ = _load_maven()  # _http_get already stubbed to raise in _load_maven
        assert maven._core_managed_version(
            'com.fasterxml.jackson.core:jackson-databind') is None

    def test_http_get_reads_and_decodes(self):
        # the real _http_get (network shim) reads the response body and decodes it.
        maven, _ = _load_maven()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"catalog-bytes"

        with patch("urllib.request.urlopen", return_value=_Resp()):
            assert maven._real_http_get("https://example.test/catalog") == "catalog-bytes"

    def test_core_catalog_fetched_once_across_coords(self):
        # memoized: many coordinate lookups in one run share a single catalog fetch
        # (matters for batched runs resolving many CVEs).
        maven, _ = _load_maven()
        catalog = ('[versions]\njackson_databind = "2.22.2"\nnetty = "4.2.0"\n'
                   '[libraries]\n'
                   'jackson-databind = { group = "com.fasterxml.jackson.core", '
                   'name = "jackson-databind", version.ref = "jackson_databind" }\n'
                   'netty-common = { group = "io.netty", name = "netty-common", '
                   'version.ref = "netty" }\n')
        calls = []
        maven._http_get = lambda *a, **k: (calls.append(1), catalog)[1]
        assert maven._core_managed_version(
            'com.fasterxml.jackson.core:jackson-databind') == '2.22.2'
        assert maven._core_managed_version('io.netty:netty-common') == '4.2.0'
        assert maven._core_managed_version('com.example:absent') is None
        assert len(calls) == 1   # one fetch for all three lookups

    def test_versions_map_key(self):
        maven, _ = _load_maven()
        assert maven._versions_map_key('${versions.thrift}') == 'thrift'
        assert maven._versions_map_key('$versions.thrift') == 'thrift'
        assert maven._versions_map_key('${versions.httpcore5}') == 'httpcore5'
        assert maven._versions_map_key('${foo}') is None       # bare var, not versions.X
        assert maven._versions_map_key('1.2.3') is None

    def test_bump_versions_map_literal_and_forms(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, "versions << [\n  'thrift': '0.23.0',\n]\n")
        assert maven._bump_versions_map(str(tmp_path), 'thrift', '0.24.0') is True
        assert "'thrift': '0.24.0'" in _read(tmp_path)
        # already at/above -> False (no change); absent key -> None
        assert maven._bump_versions_map(str(tmp_path), 'thrift', '0.24.0') is False
        assert maven._bump_versions_map(str(tmp_path), 'nope', '1.0') is None

    def test_bump_versions_map_assignment_form(self, tmp_path):
        maven, _ = _load_maven()
        _gradle(tmp_path, "versions.thrift = '0.23.0'\n")
        assert maven._bump_versions_map(str(tmp_path), 'thrift', '0.24.0') is True
        assert "versions.thrift = '0.24.0'" in _read(tmp_path)

    def test_version_ref_for_coordinate(self):
        maven, _ = _load_maven()
        text = ('[libraries]\n'
                'log4jcore = { group = "org.apache.logging.log4j", '
                'name = "log4j-core", version.ref = "log4j" }\n')
        assert maven._version_ref_for_coordinate(
            text, 'org.apache.logging.log4j:log4j-core') == 'log4j'
        assert maven._version_ref_for_coordinate(text, 'com.google.guava:guava') is None

    def test_versions_key_present(self):
        maven, _ = _load_maven()
        text = '[versions]\nlog4j = "2.20.0"\n'
        assert maven._versions_key_present(text, 'log4j') is True
        assert maven._versions_key_present(text, 'nope') is False


class TestMavenPlannerValidate:
    """Schema validation of the maven planner's model output."""

    def test_valid_edit_literal(self):
        plan = llm_planner._validate(
            '{"action":"edit_literal","file":"build.gradle","target":"1.2.3","reason":"r"}')
        assert plan == {'action': 'edit_literal', 'file': 'build.gradle',
                        'target': '1.2.3', 'reason': 'r'}

    def test_unknown_action_returns_none(self):
        assert llm_planner._validate('{"action":"frobnicate","target":""}') is None

    def test_edit_action_missing_target_returns_none(self):
        assert llm_planner._validate('{"action":"edit_ext_var","target":""}') is None

    def test_out_of_scope_with_target_returns_none(self):
        assert llm_planner._validate('{"action":"out_of_scope","target":"x"}') is None

    def test_fenced_json_tolerated(self):
        plan = llm_planner._validate(
            '```json\n{"action":"none","file":"","target":"","reason":"ok"}\n```')
        assert plan['action'] == 'none'

    def test_non_json_returns_none(self):
        assert llm_planner._validate('not json at all') is None

    def test_valid_catalog_action_in_catalog_mode(self):
        plan = llm_planner._validate(
            '{"action":"catalog","file":"gradle/libs.versions.toml",'
            '"target":"log4j","reason":"r"}', mode='catalog')
        assert plan == {'action': 'catalog', 'file': 'gradle/libs.versions.toml',
                        'target': 'log4j', 'reason': 'r'}

    def test_catalog_action_rejected_in_plugin_mode(self):
        assert llm_planner._validate(
            '{"action":"catalog","target":"log4j"}', mode='plugin') is None

    def test_edit_literal_rejected_in_catalog_mode(self):
        assert llm_planner._validate(
            '{"action":"edit_literal","target":"1.2.3"}', mode='catalog') is None

    def test_catalog_action_missing_target_returns_none(self):
        assert llm_planner._validate(
            '{"action":"catalog","target":""}', mode='catalog') is None


# ---------------------------------------------------------------------------
# llm_planner internals — direct coverage for write_force_edit, the plan_edit
# Bedrock-failure path, the _validate non-dict edge, _strip_fences, and _runtime.
# These call the captured originals (the autouse fixture patches the module attrs).
# ---------------------------------------------------------------------------


def _fake_bedrock(payload=None, raise_exc=None):
    """Stand-in Bedrock client: invoke_model returns *payload* wrapped like the real
    API body, or raises *raise_exc*."""
    def invoke_model(self, **kw):
        if raise_exc is not None:
            raise raise_exc
        return {'body': io.BytesIO(json.dumps(payload).encode())}
    return type('FakeBedrock', (), {'invoke_model': invoke_model})()


def _text_payload(text, stop_reason='end_turn'):
    return {'stop_reason': stop_reason, 'usage': {},
            'content': [{'type': 'text', 'text': text}]}


class TestWriteForceEdit:
    """write_force_edit relaxes classify-only for the transitive pin: it must return a
    usable {old_string,new_string} on clean output and None on every failure mode, so
    the caller falls back to the deterministic appended block."""

    _CTX = {'coordinate': 'org.jsoup:jsoup', 'patched_version': '1.23.1'}

    def _run(self, payload=None, raise_exc=None, caplog=None):
        with patch.object(llm_planner, '_runtime',
                          return_value=_fake_bedrock(payload, raise_exc)):
            return _ORIG_WRITE_FORCE_EDIT(self._CTX, 'build.gradle', 'force "a:b:1.0"')

    def test_valid_edit_returned(self):
        edit = {'old_string': 'force "a:b:1.0"',
                'new_string': 'force "a:b:1.0"\n  force "org.jsoup:jsoup:1.23.1"'}
        assert self._run(_text_payload(json.dumps(edit))) == edit

    def test_bedrock_error_returns_none(self):
        assert self._run(raise_exc=RuntimeError('boom')) is None

    def test_max_tokens_returns_none_and_warns(self, caplog):
        edit = json.dumps({'old_string': 'a', 'new_string': 'ab'})
        with caplog.at_level('WARNING'):
            assert self._run(_text_payload(edit, stop_reason='max_tokens')) is None
        assert any('max_tokens' in r.message for r in caplog.records)

    def test_non_json_returns_none(self):
        assert self._run(_text_payload('not json at all')) is None

    def test_non_dict_json_returns_none(self):
        assert self._run(_text_payload('[1, 2, 3]')) is None

    def test_old_equals_new_returns_none(self):
        assert self._run(_text_payload(
            json.dumps({'old_string': 'same', 'new_string': 'same'}))) is None

    def test_empty_old_string_returns_none(self):
        assert self._run(_text_payload(
            json.dumps({'old_string': '', 'new_string': 'x'}))) is None

    def test_non_string_fields_return_none(self):
        assert self._run(_text_payload(
            json.dumps({'old_string': 1, 'new_string': 2}))) is None

    def test_fenced_json_is_stripped(self):
        edit = {'old_string': 'a', 'new_string': 'ab'}
        text = '```json\n' + json.dumps(edit) + '\n```'
        assert self._run(_text_payload(text)) == edit


class TestPlanEditBedrockFailure:
    """plan_edit swallows any Bedrock/parse error and returns None (scanner fallback)."""

    def test_bedrock_error_returns_none(self):
        ctx = {'coordinate': 'g:a', 'patched_version': '2.0', 'installed_version': '1.0'}
        with patch.object(llm_planner, '_runtime',
                          return_value=_fake_bedrock(raise_exc=RuntimeError('boom'))):
            assert _ORIG_PLAN_EDIT(ctx, 'sources') is None


class TestValidateAndStripFencesEdges:
    def test_validate_non_dict_json_returns_none(self):
        # valid JSON, but a bare int -> not a dict -> None
        assert llm_planner._validate('123') is None

    def test_strip_fences_plain_json_object(self):
        assert llm_planner._strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strip_fences_language_tag_without_separator(self):
        # Defensive branch: when the language tag survives the first-line split, the
        # leading "json" is stripped too.
        assert llm_planner._strip_fences('```\njson{"a": 1}') == '{"a": 1}'


class TestRuntimeClientLazyInit:
    def test_lazily_constructs_and_caches_client(self):
        llm_planner._client = None
        sentinel = object()
        with patch.object(llm_planner.boto3, 'client', return_value=sentinel) as mk:
            first = llm_planner._runtime()
            second = llm_planner._runtime()
        assert first is sentinel and second is sentinel
        assert mk.call_count == 1  # constructed once, then cached
        llm_planner._client = None  # reset so other tests re-init cleanly


# ---------------------------------------------------------------------------
# shared/remediation.py — the maven-new "unsupported" path (an out-of-scope
# declaration is a real CVE that just isn't auto-fixable → manual review, not
# an error). Covers _execute's RemediationUnsupported handler + its Slack text.
# ---------------------------------------------------------------------------


class TestRemediationUnsupportedPath:
    def test_execute_returns_unsupported_when_apply_fix_raises(self):
        _, rem = _load_maven()
        ctx = {'base_owner': 'v-e-e-m-a', 'repo_name': 'reporting',
               'base_branch': 'main', 'cve_id': 'CVE-2026-0001'}

        class _Strategy:
            sparse_paths = None

            def build_context(self, event, write_owner, base_owner):
                return ctx

            def apply_fix(self, work_dir, c):
                raise rem.RemediationUnsupported('inherited from core; needs review')

            def regenerate(self, work_dir, c):  # not reached
                pass

        with patch.object(rem, '_resolve_token', return_value='tok'), \
                patch.object(rem, 'WRITE_OWNER', 'v-e-e-m-a'), \
                patch.object(rem, 'BASE_OWNER', 'v-e-e-m-a'), \
                patch.object(rem, '_clone', return_value=None):
            result = rem._execute({'cve_id': 'CVE-2026-0001'}, _Strategy())

        assert result['status'] == 'unsupported'
        assert result['cve_id'] == 'CVE-2026-0001'
        assert 'needs review' in result['message']

    def test_slack_message_for_unsupported(self):
        _, rem = _load_maven()
        msg = rem._format_slack_message({
            'status': 'unsupported', 'cve_id': 'CVE-2026-0001',
            'message': 'inherited from core.',
        })
        assert 'CVE-2026-0001' in msg
        assert 'inherited from core.' in msg
        assert 'Manual review' in msg
