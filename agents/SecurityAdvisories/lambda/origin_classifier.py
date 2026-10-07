#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Classify a **maven** scan vulnerability's ``package.origin`` as direct vs transitive.

This module encodes maven/Gradle-specific assumptions — ``build.gradle`` resolution
chains, ``org.opensearch`` group ownership, and ``resolutionStrategy.force``-style
remediation. The maven remediation worker is its sole consumer.

The scans cluster records, per vulnerable package, an ``origin`` block: the
dependency-resolution paths cdxgen found for it. In the rich form (present for
every ``origin/*`` branch scan) each path is an array:

    [ "<module>/build.gradle", "<configuration>", ...parent coordinates..., "<leaf>" ]

- element 0 is the build.gradle file,
- element 1 is the Gradle configuration,
- the middle elements are the parent libraries the dep is pulled through,
- the last element is the vulnerable coordinate itself.

A dependency is **directly declared** in a path when the coordinate sits
immediately after the configuration (``[file, config, coord]``) — i.e. the
element before the leaf is the configuration, not another library. It is
**transitive** in a path when a parent coordinate sits between the configuration
and the leaf (``[file, config, parent@x, ..., coord]``).

``classify_origin`` reduces the whole ``origin`` block to one routing signal the
remediation worker consumes:

- ``"direct"``    — declared directly in at least one path (the worker's normal
  build.gradle edit path applies; a mixed dep that is *also* transitive is still
  ``direct`` because bumping the declaration is the right fix).
- ``"transitive"`` — every path routes through a parent, and at least one path's
  immediate parent is a THIRD-PARTY library the plugin can pin. The coordinate is
  not declared anywhere, so the fix is a ``resolutionStrategy.force`` block.
- ``"core_inherited"`` — every path routes through a parent AND every path's
  immediate parent is an ``org.opensearch*`` artifact. The vulnerable version is
  declared by an OpenSearch component (e.g. ``opensearch-rest-client`` via
  ``test-framework``), so it is owned by core and must be fixed upstream, not
  force-pinned in the plugin. The worker treats this as out of scope (manual
  review), mirroring the direct-declaration ``${versions.X}`` core-inherited case.
- ``"unknown"``   — ``origin`` is absent, empty, or in the lossy flat/scalar form
  (release-tag scans store just a list of file names, no chain). The worker keeps
  its default behaviour and never forces on a guess.

Detection keys off the element before the leaf (``path[-2]`` — whatever directly
pulls the vulnerable coordinate), NOT path length and NOT the chain root: the
immediate parent is the artifact that declares the vulnerable version, so it is the
robust owner signal, whereas the chain root can be polluted by cdxgen graph
flattening (an unrelated top-level dep strung ahead of the real puller). The
coordinate-vs-config marker and the OpenSearch-owner prefix are defined at the
constants below.
"""

import re

DIRECT = "direct"
TRANSITIVE = "transitive"
CORE_INHERITED = "core_inherited"
UNKNOWN = "unknown"

# An OpenSearch-owned artifact's group starts with ``org.opensearch`` (covers
# ``org.opensearch``, ``org.opensearch.client``, ``org.opensearch.test``,
# ``org.opensearch.plugin``). In an origin coordinate ``group-artifact@version``
# the group is the leading segment, so a prefix check identifies core ownership.
_OPENSEARCH_PREFIX = "org.opensearch"

# A resolved coordinate token embeds the version as ``name@<version>`` where the
# version starts with a digit (e.g. ``org.springframework-spring-context@5.3.22``).
# Configuration names (``runtimeClasspath``) and Gradle project references
# (``project '-plugins@ingestion-kafka'``) never have a digit right after ``@``,
# so this cleanly distinguishes a parent library from a config/project element.
_COORDINATE = re.compile(r"@\d")


def _is_coordinate(element) -> bool:
    """True if an ``origin`` path element is a resolved dependency coordinate."""
    return isinstance(element, str) and _COORDINATE.search(element) is not None


def _is_opensearch(coordinate) -> bool:
    """True if a coordinate is an OpenSearch-owned artifact (group ``org.opensearch*``)."""
    return isinstance(coordinate, str) and coordinate.startswith(_OPENSEARCH_PREFIX)


def classify_origin(origin) -> str:
    """Return the routing verdict for ``origin`` (see the module docstring for the model).

    DIRECT if any path is a direct declaration (``path[-2]`` is the configuration);
    else CORE_INHERITED if every transitive path's immediate parent is
    ``org.opensearch*``, TRANSITIVE otherwise; UNKNOWN if ``origin`` is missing/empty
    or has no usable array paths.
    """
    if not isinstance(origin, list) or not origin:
        return UNKNOWN

    # Only the rich array-of-arrays form is classifiable. Paths shorter than two
    # elements can't be judged (no config+leaf pair) and are ignored.
    paths = [p for p in origin if isinstance(p, list) and len(p) >= 2]
    if not paths:
        return UNKNOWN

    parents = []  # immediate parent (path[-2]) of the leaf, per transitive path
    for path in paths:
        parent = path[-2]
        if not _is_coordinate(parent):
            return DIRECT              # config sits right before the leaf
        parents.append(parent)

    # Every path is transitive: all-OpenSearch parents => core owns the version.
    if all(_is_opensearch(p) for p in parents):
        return CORE_INHERITED
    return TRANSITIVE
