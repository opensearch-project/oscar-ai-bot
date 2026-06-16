# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the neglected page URL builder.

**Property 2: Neglected page URL round-trip**
For any combination of optional filter parameters, build_neglected_page_url SHALL
produce a URL that:
- Starts with the neglected page base URL
- Always contains all five query parameters (age, severe, releases, critical, tag)
- Uses defaults for any parameter not explicitly provided:
  age=60d, severe=false, releases=false, critical=false, tag=origin/main
- When the URL's query string is parsed back, the parameter values match the original inputs

_Validates: Requirements 3.1, 3.2_
"""

import os
import sys
from urllib.parse import parse_qs, urlparse

import pytest

# Add the lambda source path
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)
if _LAMBDA_PATH not in sys.path:
    sys.path.insert(0, _LAMBDA_PATH)

from response_filter import NEGLECTED_PAGE_BASE  # noqa: E402
from response_filter import VALID_AGE_VALUES  # noqa: E402
from response_filter import build_neglected_page_url  # noqa: E402
from response_filter import (_DEFAULT_AGE, _DEFAULT_CRITICAL,  # noqa: E402
                             _DEFAULT_RELEASES, _DEFAULT_SEVERE, _DEFAULT_TAG)

# ---------------------------------------------------------------------------
# Property 2: Neglected page URL round-trip
# ---------------------------------------------------------------------------


class TestNeglectedPageUrlRoundTrip:
    """Property 2: Neglected page URL round-trip.

    For any combination of optional filter parameters, the URL produced by
    build_neglected_page_url can be parsed back to recover the original inputs.
    Parameters not provided fall back to defaults.

    **Validates: Requirements 3.1, 3.2**
    """

    @pytest.mark.parametrize('age', sorted(VALID_AGE_VALUES))
    def test_round_trip_valid_age(self, age):
        """Valid age values appear in the URL and can be parsed back."""
        url = build_neglected_page_url(age=age)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert url.startswith(NEGLECTED_PAGE_BASE)
        assert 'age' in params
        assert params['age'] == [age]

    @pytest.mark.parametrize('age', ['5d', '99d', '100d', '', 'abc', '0'])
    def test_invalid_age_falls_back_to_default(self, age):
        """Invalid age values fall back to the default age."""
        url = build_neglected_page_url(age=age)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params['age'] == [_DEFAULT_AGE]

    @pytest.mark.parametrize('severe', [True, False])
    def test_round_trip_severe(self, severe):
        """severe boolean appears in the URL as 'true' or 'false'."""
        url = build_neglected_page_url(severe=severe)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert 'severe' in params
        assert params['severe'] == [str(severe).lower()]

    def test_severe_none_uses_default(self):
        """severe=None uses the default value."""
        url = build_neglected_page_url(severe=None)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params['severe'] == [str(_DEFAULT_SEVERE).lower()]

    @pytest.mark.parametrize('releases', [True, False])
    def test_round_trip_releases(self, releases):
        """releases boolean appears in the URL as 'true' or 'false'."""
        url = build_neglected_page_url(releases=releases)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert 'releases' in params
        assert params['releases'] == [str(releases).lower()]

    def test_releases_none_uses_default(self):
        """releases=None uses the default value."""
        url = build_neglected_page_url(releases=None)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params['releases'] == [str(_DEFAULT_RELEASES).lower()]

    @pytest.mark.parametrize('critical', [True, False])
    def test_round_trip_critical(self, critical):
        """critical boolean appears in the URL as 'true' or 'false'."""
        url = build_neglected_page_url(critical=critical)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert 'critical' in params
        assert params['critical'] == [str(critical).lower()]

    def test_critical_none_uses_default(self):
        """critical=None uses the default value."""
        url = build_neglected_page_url(critical=None)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params['critical'] == [str(_DEFAULT_CRITICAL).lower()]

    @pytest.mark.parametrize('tag', ['2.19.6', 'origin/main', '1.2.0.1', '2.x'])
    def test_round_trip_tag(self, tag):
        """tag string appears in the URL query string."""
        url = build_neglected_page_url(tag=tag)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert 'tag' in params
        assert params['tag'] == [tag]

    @pytest.mark.parametrize('tag', ['', None])
    def test_empty_or_none_tag_uses_default(self, tag):
        """Empty or None tag uses the default tag value."""
        url = build_neglected_page_url(tag=tag)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params['tag'] == [_DEFAULT_TAG]

    def test_all_params_round_trip(self):
        """All parameters provided can be parsed back from the URL."""
        url = build_neglected_page_url(
            age='30d', severe=True, releases=True, critical=False, tag='2.19.6',
        )
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params['age'] == ['30d']
        assert params['severe'] == ['true']
        assert params['releases'] == ['true']
        assert params['critical'] == ['false']
        assert params['tag'] == ['2.19.6']

    def test_no_extra_params_when_all_provided(self):
        """URL contains exactly the expected parameters and no extras."""
        url = build_neglected_page_url(
            age='45d', severe=False, releases=True, critical=True, tag='main',
        )
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert set(params.keys()) == {'age', 'severe', 'releases', 'critical', 'tag'}

    def test_always_has_all_params(self):
        """URL always contains all five parameters even with no explicit input."""
        url = build_neglected_page_url(age='15d', tag='2.x')
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert set(params.keys()) == {'age', 'severe', 'releases', 'critical', 'tag'}


# ---------------------------------------------------------------------------
# Unit tests for specific cases
# ---------------------------------------------------------------------------


class TestNeglectedPageUrlUnitTests:
    """Unit tests for specific edge cases and examples."""

    def test_no_params_returns_url_with_defaults(self):
        """No parameters returns a URL with all defaults applied."""
        url = build_neglected_page_url()
        expected = (
            f"{NEGLECTED_PAGE_BASE}?age=30d&critical=false"
            f"&releases=false&severe=true&tag=origin%2Fmain"
        )
        assert url == expected

    def test_all_none_returns_url_with_defaults(self):
        """All None parameters returns a URL with all defaults applied."""
        url = build_neglected_page_url(
            age=None, severe=None, releases=None, critical=None, tag=None,
        )
        expected = (
            f"{NEGLECTED_PAGE_BASE}?age=30d&critical=false"
            f"&releases=false&severe=true&tag=origin%2Fmain"
        )
        assert url == expected

    def test_url_always_starts_with_base(self):
        """URL always starts with the neglected page base."""
        url = build_neglected_page_url(age='30d', severe=True)
        assert url.startswith(NEGLECTED_PAGE_BASE)

    def test_params_are_sorted(self):
        """Query parameters are sorted alphabetically for deterministic output."""
        url = build_neglected_page_url(
            age='30d', severe=True, releases=True, critical=True, tag='main',
        )
        query = url.split('?')[1]
        param_names = [p.split('=')[0] for p in query.split('&')]
        assert param_names == sorted(param_names)

    def test_severe_false_included(self):
        """severe=False is included as 'false' (not omitted)."""
        url = build_neglected_page_url(severe=False)
        assert 'severe=false' in url

    def test_releases_false_included(self):
        """releases=False is included as 'false' (not omitted)."""
        url = build_neglected_page_url(releases=False)
        assert 'releases=false' in url

    def test_critical_false_included(self):
        """critical=False is included as 'false' (not omitted)."""
        url = build_neglected_page_url(critical=False)
        assert 'critical=false' in url

    def test_example_from_design_doc(self):
        """Matches the example URL from the design document."""
        url = build_neglected_page_url(
            age='30d', severe=True, releases=True, critical=False, tag='2.19.6',
        )
        # Verify all expected params are present
        assert 'age=30d' in url
        assert 'severe=true' in url
        assert 'releases=true' in url
        assert 'critical=false' in url
        assert 'tag=2.19.6' in url

    def test_default_url_matches_expected(self):
        """Default URL matches the expected defaults: age=30d&severe=true&releases=false&critical=false&tag=origin/main."""
        url = build_neglected_page_url()
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params['age'] == ['30d']
        assert params['severe'] == ['true']
        assert params['releases'] == ['false']
        assert params['critical'] == ['false']
        assert params['tag'] == ['origin/main']
