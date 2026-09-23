# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for resolving a release manager's GitHub handle to a Slack mention.

The mention is a convenience, so these tests pin hard that no failure mode here can cost
the release manager the notification itself - an unreadable table, an unlinked account or a
deployment without identity mapping must all degrade to naming them instead.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def table():
    return MagicMock()


@pytest.fixture
def dynamodb(identity, table, monkeypatch):
    monkeypatch.setenv('IDENTITY_TABLE_NAME', 'oscar-identity-T123-prod')
    resource = MagicMock()
    resource.Table.return_value = table
    with patch.object(identity.boto3, 'resource', return_value=resource):
        yield resource


def item(handle, slack_user_id, status='active'):
    return {'github_handle': handle, 'slack_user_id': slack_user_id, 'status': status}


class TestNormalizeHandle:
    """The handle is a free-text Jenkins parameter, so it arrives in several shapes."""

    @pytest.mark.parametrize('raw', [
        'gaiksaya',
        '@gaiksaya',
        '  gaiksaya  ',
        'https://github.com/gaiksaya',
        'https://github.com/gaiksaya/',
        'github.com/gaiksaya',
    ])
    def test_reduces_to_bare_handle(self, identity, raw):
        assert identity.normalize_handle(raw) == 'gaiksaya'

    @pytest.mark.parametrize('raw', [
        'https://github.com/gaiksaya?tab=repositories',
        'https://github.com/gaiksaya?tab=repositories&q=build',
        'https://github.com/gaiksaya#readme',
        'https://github.com/gaiksaya/?tab=stars',
    ])
    def test_url_query_and_fragment_are_discarded(self, identity, raw):
        """A profile URL copied from a browser carries these, and they are not the handle."""
        assert identity.normalize_handle(raw) == 'gaiksaya'

    @pytest.mark.parametrize('raw', [None, '', '   '])
    def test_empty_input_yields_empty_handle(self, identity, raw):
        assert identity.normalize_handle(raw) == ''

    def test_casing_is_preserved(self, identity):
        """Only lookups are case-insensitive - the rendered link keeps what was registered."""
        assert identity.normalize_handle('@Gaiksaya') == 'Gaiksaya'


class TestLoadHandleMap:

    def test_maps_active_handles_to_slack_users(self, identity, dynamodb, table):
        table.scan.return_value = {'Items': [item('gaiksaya', 'U111'), item('someone', 'U222')]}
        assert identity.load_handle_map() == {'gaiksaya': 'U111', 'someone': 'U222'}

    def test_handles_are_lowercased_for_lookup(self, identity, dynamodb, table):
        table.scan.return_value = {'Items': [item('GaikSaya', 'U111')]}
        assert identity.load_handle_map() == {'gaiksaya': 'U111'}

    def test_expired_mappings_are_ignored(self, identity, dynamodb, table):
        """An expired mapping's Slack user may have left the workspace."""
        table.scan.return_value = {'Items': [item('gone', 'U999', status='expired')]}
        assert identity.load_handle_map() == {}

    def test_incomplete_items_are_skipped(self, identity, dynamodb, table):
        table.scan.return_value = {'Items': [
            {'github_handle': 'nolink', 'status': 'active'},
            {'slack_user_id': 'U333', 'status': 'active'},
            item('good', 'U444'),
        ]}
        assert identity.load_handle_map() == {'good': 'U444'}

    def test_pagination_is_followed(self, identity, dynamodb, table):
        table.scan.side_effect = [
            {'Items': [item('first', 'U111')], 'LastEvaluatedKey': {'github_id': 1}},
            {'Items': [item('second', 'U222')]},
        ]
        assert identity.load_handle_map() == {'first': 'U111', 'second': 'U222'}
        assert table.scan.call_args_list[1].kwargs['ExclusiveStartKey'] == {'github_id': 1}

    def test_scan_projects_only_the_fields_needed(self, identity, dynamodb, table):
        table.scan.return_value = {'Items': []}
        identity.load_handle_map()
        kwargs = table.scan.call_args.kwargs
        assert kwargs['ProjectionExpression'] == 'github_handle, slack_user_id, #s'
        assert kwargs['ExpressionAttributeNames'] == {'#s': 'status'}

    def test_scan_asks_dynamodb_to_drop_expired_mappings(self, identity, dynamodb, table):
        """Filtering server-side keeps the response and the page count proportional to
        the people who can actually be mentioned, however large the table grows."""
        table.scan.return_value = {'Items': []}
        identity.load_handle_map()
        kwargs = table.scan.call_args.kwargs
        assert kwargs['FilterExpression'] == '#s = :active'
        assert kwargs['ExpressionAttributeValues'] == {':active': 'active'}

    def test_pagination_survives_a_page_filtered_down_to_nothing(self, identity, dynamodb, table):
        # A filtered scan can return an empty page and still have more to walk.
        table.scan.side_effect = [
            {'Items': [], 'LastEvaluatedKey': {'github_id': 1}},
            {'Items': [item('later', 'U111')]},
        ]
        assert identity.load_handle_map() == {'later': 'U111'}

    def test_a_handle_claimed_by_two_people_is_not_mentioned(self, identity, dynamodb, table, caplog):
        """GitHub handles are reusable, and this table is keyed on the numeric id.

        Rename an account, let someone else take the old handle, and two active rows claim it.
        Tagging the wrong person on a release-blocking alert is worse than tagging nobody, so
        the handle is dropped and the message falls back to a profile link.
        """
        table.scan.return_value = {'Items': [item('gaiksaya', 'U111'), item('GaikSaya', 'U222')]}
        with caplog.at_level(logging.WARNING):
            assert identity.load_handle_map() == {}
        assert 'RELEASE_NOTIFY_IDENTITY_COLLISION' in caplog.text

    def test_a_duplicate_row_for_the_same_person_is_not_a_collision(self, identity, dynamodb, table, caplog):
        table.scan.return_value = {'Items': [item('gaiksaya', 'U111'), item('gaiksaya', 'U111')]}
        with caplog.at_level(logging.WARNING):
            assert identity.load_handle_map() == {'gaiksaya': 'U111'}
        assert 'COLLISION' not in caplog.text

    def test_a_collision_does_not_cost_the_other_handles(self, identity, dynamodb, table):
        table.scan.return_value = {'Items': [
            item('contested', 'U111'), item('contested', 'U222'), item('fine', 'U333'),
        ]}
        assert identity.load_handle_map() == {'fine': 'U333'}

    def test_a_malformed_item_is_skipped_without_losing_the_map(self, identity, dynamodb, table, caplog):
        """.lower() on a non-string would raise, and the handler around the scan turns any
        exception into an empty map - so one hand-edited row would cost everyone a mention."""
        table.scan.return_value = {'Items': [
            {'github_handle': 12345, 'slack_user_id': 'U111', 'status': 'active'},
            item('fine', 'U222'),
        ]}
        with caplog.at_level(logging.WARNING):
            assert identity.load_handle_map() == {'fine': 'U222'}
        assert 'RELEASE_NOTIFY_IDENTITY_MALFORMED' in caplog.text

    def test_no_table_configured_returns_empty_without_calling_dynamodb(self, identity, monkeypatch):
        """A deployment with no identity table must not pay for a lookup it cannot do."""
        monkeypatch.delenv('IDENTITY_TABLE_NAME', raising=False)
        with patch.object(identity.boto3, 'resource') as resource:
            assert identity.load_handle_map() == {}
        resource.assert_not_called()

    def test_unreadable_table_returns_empty(self, identity, dynamodb, table):
        table.scan.side_effect = RuntimeError('AccessDeniedException')
        assert identity.load_handle_map() == {}


class TestRenderReleaseManager:

    def test_linked_manager_is_mentioned(self, identity):
        assert identity.render_release_manager(
            ['Foo Bar'], {'foo': 'U111'}, ['foo'],
        ) == '<@U111>'

    def test_lookup_ignores_casing(self, identity):
        assert identity.render_release_manager(['Foo Bar'], {'foo': 'U111'}, ['@Foo']) == '<@U111>'

    def test_unlinked_manager_falls_back_to_their_name(self, identity):
        """A handle is an identifier - a reader should never have to translate one."""
        assert identity.render_release_manager(['Foo Bar'], {'other': 'U111'}, ['foo']) == 'Foo Bar'

    def test_missing_map_falls_back_to_their_name(self, identity):
        assert identity.render_release_manager(['Foo Bar'], None, ['foo']) == 'Foo Bar'

    def test_schedule_doc_without_handles_falls_back_to_names(self, identity):
        """Schedule docs indexed before the handle was scraped carry names only."""
        assert identity.render_release_manager(['Foo Bar'], {'foo': 'U111'}) == 'Foo Bar'

    def test_every_manager_is_resolved_independently(self, identity):
        """One manager who has not linked their account must not cost the others their mention."""
        assert identity.render_release_manager(
            ['Foo Bar', 'Baz Qux'], {'foo': 'U222'}, ['foo', 'baz'],
        ) == '<@U222>, Baz Qux'

    def test_all_managers_mentioned_when_all_linked(self, identity):
        assert identity.render_release_manager(
            ['Foo Bar', 'Baz Qux'], {'foo': 'U222', 'baz': 'U333'}, ['foo', 'baz'],
        ) == '<@U222>, <@U333>'

    def test_mismatched_handles_name_everyone_rather_than_guess(self, identity):
        """Pairing is positional, so an unusable length must not tag the wrong person."""
        assert identity.render_release_manager(
            ['Foo Bar', 'Baz Qux'], {'baz': 'U333'}, ['baz'],
        ) == 'Foo Bar, Baz Qux'

    def test_a_repeated_manager_is_rendered_once(self, identity):
        assert identity.render_release_manager(
            ['Foo Bar', 'Foo Bar'], {'foo': 'U111'}, ['foo', 'foo'],
        ) == '<@U111>'

    def test_a_scalar_manager_is_accepted(self, identity):
        """Manual registrations pass a single name rather than a list."""
        assert identity.render_release_manager('Foo Bar', {}, 'foo') == 'Foo Bar'

    @pytest.mark.parametrize('raw', [None, '', '  ', []])
    def test_no_manager_renders_nothing(self, identity, raw):
        assert identity.render_release_manager(raw, {'foo': 'U111'}) == ''
