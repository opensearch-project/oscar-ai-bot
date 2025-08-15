#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Constants for Communication Handler.
"""

# Channel allow list for message sending
CHANNEL_ALLOW_LIST = ['C096MV7JZ0T', 'C09827S7CEB', 'C091EH1JKCL', 'C088XMSH4DA']

# Context TTL (7 days in seconds)
CONTEXT_TTL = 7 * 24 * 60 * 60

# Hardcoded message templates from the templates directory
MESSAGE_TEMPLATES = {
    "missing_release_notes": {
        "template": "Hi, </br>\n\nThis component is missing release notes at {branch} ref. Please add them on priority in order to meet the entrance criteria for the release. </br>\nPlease check out the [guidelines](https://github.com/opensearch-project/opensearch-plugins/blob/main/RELEASE_NOTES.md) for the release notes. </br>\n\nThank you!",
        "default_channel": "C096MV7JZ0T"
    },
    "criteria_not_met": {
        "template": "Hi @{release_owner}, </br>\n\nThe below {type_of_criteria} criteria for your component has not been met. </br>\nPlease review the issue and address it with high priority. </br>\n\n{criteria}\n\nThanks!",
        "default_channel": "C096MV7JZ0T"
    },
    "documentation_issues": {
        "template": "Hi @{owner}, </br>\n\nAs part of the [entrance criteria](https://github.com/opensearch-project/.github/blob/main/RELEASING.md#entrance-criteria-to-start-release-window), all the documentation pull requests need to be drafted and in technical review. </br>\n**Since there is no pull request linked to this issue, please take one of the following actions:** </br>\n* Create the pull request and [link it](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) to this issue. </br>\n* If you already have a pull request created, please [link it](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) to this issue. </br>\n* If this feature is not targeted for the currently labeled release version, please update the issue with the correct release version. </br>\n\nPlease note: Missing documentation can block the release and cause delays in the overall process. </br>\nThank you!",
        "default_channel": "C096MV7JZ0T"
    },
    "missing_code_coverage": {
        "template": "Hi, </br>\n\n{component_name} is not reporting code-coverage for branch [{branch}]({codecov_url}). </br>\nPlease fix the issue by checking your CI workflow responsible for reporting code coverage. See the details on [code coverage reporting](https://github.com/opensearch-project/opensearch-plugins/blob/main/TESTING.md#code-coverage-reporting) </br>\n\nThank you!",
        "default_channel": "C09827S7CEB"
    },
    "release_announcement": {
        "template": "We're excited to announce the release of OpenSearch {release_version}! :tada:! </br>\n\n• Download: https://opensearch.org/downloads.html </br>\n• Release Notes: https://github.com/opensearch-project/opensearch-build/blob/main/release-notes/opensearch-release-notes-{release_version}.md </br>\n• Documentation: https://opensearch.org/docs/latest/about/ </br>\nFor detailed information about what's new, check out our blog post: https://www.opensearch.org/blog/explore-OpenSearch-2-19/ </br>\n\nThanks everyone for the help to release OpenSearch and OpenSearch Dashboards {release_version}. </br>\nComponent repo owners please create a github release based on the tags of {release_version}.0. </br>\n\nHere is the retrospective issue {release_retro_issue_link} for the release. Please feel free to share your valuable feedback to help us make improvements for the upcoming releases.",
        "default_channel": "C096MV7JZ0T"
    }
}