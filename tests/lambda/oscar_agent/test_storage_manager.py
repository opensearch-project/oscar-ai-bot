# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for StorageManager using moto DynamoDB."""

import time
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def storage():
    """Create a StorageManager backed by a moto DynamoDB table."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        dynamodb.create_table(
            TableName='test-context',
            KeySchema=[{'AttributeName': 'thread_key', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'thread_key', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST',
        )

        mock_config = patch('context_storage.config')
        cfg = mock_config.start()
        cfg.region = 'us-east-1'
        cfg.context_table_name = 'test-context'
        cfg.context_ttl = 604800

        from context_storage import StorageManager
        sm = StorageManager(region='us-east-1')

        yield sm
        mock_config.stop()


class TestStoreContext:

    def test_store_and_retrieve(self, storage):
        ctx = {'session_id': 's1', 'history': [{'query': 'q', 'response': 'r'}]}
        assert storage.store_context('key1', ctx) is True
        result = storage.get_context('key1')
        assert result['session_id'] == 's1'
        assert len(result['history']) == 1

    def test_store_adds_missing_history(self, storage):
        ctx = {'session_id': 's1'}
        storage.store_context('key1', ctx)
        result = storage.get_context('key1')
        assert result['history'] == []

    def test_store_adds_missing_session_id(self, storage):
        ctx = {'history': []}
        storage.store_context('key1', ctx)
        result = storage.get_context('key1')
        assert result['session_id'] is None

    def test_store_non_dict_returns_false(self, storage):
        assert storage.store_context('key1', 'not a dict') is False

    def test_ttl_set_correctly(self, storage):
        storage.store_context('key1', {'history': [], 'session_id': None})
        item = storage.context_table.get_item(Key={'thread_key': 'key1'})['Item']
        now = int(time.time())
        assert item['ttl'] >= now + 604700  # within ~100s tolerance


class TestGetContext:

    def test_returns_none_for_missing_key(self, storage):
        assert storage.get_context('nonexistent') is None

    def test_returns_none_for_expired_ttl(self, storage):
        # Directly insert an expired item
        storage.context_table.put_item(Item={
            'thread_key': 'expired',
            'context': {'session_id': None, 'history': []},
            'ttl': int(time.time()) - 100,
            'updated_at': int(time.time()),
        })
        assert storage.get_context('expired') is None


class TestGetContextForQuery:

    def test_formats_as_conversation(self, storage):
        ctx = {'session_id': 's1', 'history': [
            {'query': 'what is opensearch?', 'response': 'A search engine.'},
        ]}
        storage.store_context('key1', ctx)
        result = storage.get_context_for_query('key1')
        assert 'User: what is opensearch?' in result
        assert 'Assistant: A search engine.' in result

    def test_no_context_returns_empty_string(self, storage):
        assert storage.get_context_for_query('nonexistent') == ''

    def test_empty_history_returns_empty_string(self, storage):
        storage.store_context('key1', {'session_id': None, 'history': []})
        assert storage.get_context_for_query('key1') == ''


class TestUpdateContext:

    def test_creates_new_when_none_exists(self, storage):
        result = storage.update_context('key1', 'q1', 'r1', None, 'sess-new')
        assert result['session_id'] == 'sess-new'
        assert len(result['history']) == 1
        assert result['history'][0]['query'] == 'q1'

    def test_appends_to_existing(self, storage):
        storage.update_context('key1', 'q1', 'r1', None, 'sess1')
        result = storage.update_context('key1', 'q2', 'r2', 'sess1', 'sess1')
        assert len(result['history']) == 2

    def test_new_session_id_takes_precedence(self, storage):
        result = storage.update_context('key1', 'q', 'r', 'old-sess', 'new-sess')
        assert result['session_id'] == 'new-sess'


class TestStoreBotMessageContext:

    def test_with_user_query(self, storage):
        storage.store_bot_message_context('C123', 'ts1', 'bot reply',
                                          session_id='s1', user_query='user asked')
        ctx = storage.get_context('C123_ts1')
        assert ctx['history'][0]['query'] == 'user asked'
        assert ctx['history'][0]['response'] == 'bot reply'

    def test_without_user_query(self, storage):
        storage.store_bot_message_context('C123', 'ts1', 'bot message')
        ctx = storage.get_context('C123_ts1')
        assert 'Bot initiated' in ctx['history'][0]['query']


class TestStoreCrossChannelContext:

    def test_stores_with_redacted_query(self, storage):
        storage.store_cross_channel_context('C999', 'ts1', 'original', 'sent msg')
        ctx = storage.get_context('C999_ts1')
        assert 'privacy' in ctx['history'][0]['query'].lower()
        assert ctx['history'][0]['response'] == 'sent msg'
