#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the origin_classifier (direct vs transitive routing signal).

Fixtures mirror real scan ``package.origin`` shapes observed on ``origin/*``
branch scans (rich array-of-arrays) and release-tag scans (lossy flat/scalar).
"""

import os
import sys

_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..',
    'agents', 'SecurityAdvisories', 'lambda',
)
if _LAMBDA_PATH not in sys.path:
    sys.path.insert(0, _LAMBDA_PATH)

from origin_classifier import (CORE_INHERITED, DIRECT,  # noqa: E402
                               TRANSITIVE, UNKNOWN, classify_origin)

# --- direct: coordinate sits right after the configuration -------------------

def test_direct_single_declaration():
    origin = [["build.gradle", "compileOnly", "org.bouncycastle-bcpkix-fips@2.1.9"]]
    assert classify_origin(origin) == DIRECT


def test_direct_named_arg_style_multiple_configs():
    # bcpkix-fips example: many configs, each a length-3 direct path.
    origin = [
        ["build.gradle", "compileClasspath", "org.bouncycastle-bcpkix-fips@2.1.9"],
        ["build.gradle", "testRuntimeClasspath", "org.bouncycastle-bcpkix-fips@2.1.9"],
        ["sample-resource-plugin/build.gradle", "integrationTestImplementation",
         "org.bouncycastle-bcpkix-fips@2.1.9"],
    ]
    assert classify_origin(origin) == DIRECT


def test_mixed_declared_and_transitive_is_direct():
    # Declared directly in one module, pulled transitively in another -> DIRECT,
    # because bumping the declaration is the correct fix.
    origin = [
        ["common/build.gradle", "api", "com.google.guava-guava@31.0.1-jre"],
        ["core/build.gradle", "runtimeClasspath",
         "com.facebook.presto-presto-matching@0.240", "com.google.guava-guava@31.0.1-jre"],
    ]
    assert classify_origin(origin) == DIRECT


# --- transitive: every path routes through a parent coordinate ---------------

def test_transitive_single_parent():
    origin = [["build.gradle", "checkstyle",
               "com.puppycrawl.tools-checkstyle@10.3.2",
               "commons-beanutils-commons-beanutils@1.9.4"]]
    assert classify_origin(origin) == TRANSITIVE


def test_transitive_multi_hop_and_multi_parent():
    origin = [
        ["core/build.gradle", "runtimeClasspath",
         "org.springframework-spring-context@5.3.22",
         "org.springframework-spring-expression@5.3.22"],
        ["legacy/build.gradle", "compileClasspath",
         "com.google.guava-guava@31.0.1-jre",
         "org.springframework-spring-context@5.3.22",
         "org.springframework-spring-aop@5.3.22",
         "org.springframework-spring-expression@5.3.22"],
    ]
    assert classify_origin(origin) == TRANSITIVE


def test_project_reference_parent_is_direct_not_transitive():
    # A Gradle project reference (`project '-plugins@ingestion-kafka'`) has an
    # `@` but followed by a letter, so it is NOT a coordinate; combined with a
    # real direct path, the dep is DIRECT.
    origin = [
        ["build.gradle", "aggregateCodeCoverageReportResults",
         "project '-plugins@ingestion-hive'", "org.xerial.snappy-snappy-java@1.1.10.7"],
        ["plugins/ingestion-hive/build.gradle", "runtimeOnly",
         "org.xerial.snappy-snappy-java@1.1.10.7"],
    ]
    assert classify_origin(origin) == DIRECT


def test_project_reference_only_is_unknown_not_transitive():
    # Only a project-reference path (no real parent coordinate, no direct path):
    # the element before the leaf is not a coordinate, so it's a direct-style
    # path -> DIRECT (declared via the referenced project).
    origin = [
        ["build.gradle", "aggregateTestReportResults",
         "project '-plugins@ingestion-kafka'", "org.xerial.snappy-snappy-java@1.1.10.7"],
    ]
    assert classify_origin(origin) == DIRECT


# --- core_inherited: every immediate parent is an org.opensearch artifact ----

def test_core_inherited_single_opensearch_parent():
    # httpclient5 pulled only via opensearch-rest-client (its immediate parent).
    origin = [["build.gradle", "runtimeClasspath",
               "org.opensearch.client-opensearch-rest-client@3.9.0-SNAPSHOT",
               "org.apache.httpcomponents.client5-httpclient5@5.6.1"]]
    assert classify_origin(origin) == CORE_INHERITED


def test_core_inherited_via_test_framework():
    origin = [["build.gradle", "testRuntimeClasspath",
               "org.opensearch.test-framework@3.9.0-SNAPSHOT",
               "org.opensearch.client-opensearch-rest-client-sniffer@3.9.0-SNAPSHOT",
               "org.apache.httpcomponents.client5-httpclient5@5.6.1"]]
    assert classify_origin(origin) == CORE_INHERITED


def test_core_inherited_ignores_noisy_third_party_root():
    # The Alerting case: a chain root is a third-party lib (kotlinx-coroutines),
    # but the IMMEDIATE parent of the leaf is always an opensearch artifact. The
    # [-2] rule correctly classifies it core_inherited despite the noisy root.
    origin = [
        ["build.gradle", "implementation",
         "org.jetbrains.kotlinx-kotlinx-coroutines-core@1.1.1",
         "org.opensearch.client-opensearch-rest-client@3.9.0-SNAPSHOT",
         "org.apache.httpcomponents.client5-httpclient5@5.6.1"],
        ["build.gradle", "runtimeClasspath",
         "org.opensearch-opensearch-remote-metadata-sdk@3.9.0.0-SNAPSHOT",
         "org.apache.httpcomponents.client5-httpclient5@5.6.1"],
    ]
    assert classify_origin(origin) == CORE_INHERITED


def test_third_party_immediate_parent_is_transitive_not_core():
    # Same leaf, but at least one immediate parent is third-party (xmlresolver) ->
    # forceable in the plugin, not core-inherited.
    origin = [
        ["build.gradle", "runtimeClasspath",
         "org.xmlresolver-xmlresolver@5.1.2",
         "org.apache.httpcomponents.client5-httpclient5@5.6.1"],
        ["build.gradle", "testRuntimeClasspath",
         "org.opensearch.client-opensearch-rest-client@3.9.0-SNAPSHOT",
         "org.apache.httpcomponents.client5-httpclient5@5.6.1"],
    ]
    assert classify_origin(origin) == TRANSITIVE


# --- unknown: lossy or absent origin -----------------------------------------

def test_flat_string_list_is_unknown():
    # Release-tag scans store just the file names, no chain.
    origin = ["core/build.gradle", "sql/build.gradle", "plugin/build.gradle"]
    assert classify_origin(origin) == UNKNOWN


def test_scalar_string_is_unknown():
    assert classify_origin("sql/build.gradle") == UNKNOWN


def test_empty_list_is_unknown():
    assert classify_origin([]) == UNKNOWN


def test_none_is_unknown():
    assert classify_origin(None) == UNKNOWN


def test_short_paths_only_is_unknown():
    # A path with a single element can't be judged (no config+leaf pair).
    assert classify_origin([["build.gradle"]]) == UNKNOWN


def test_dict_is_unknown():
    assert classify_origin({"not": "a list"}) == UNKNOWN
