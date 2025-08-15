#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Channel utilities for Communication Handler.
"""

import logging
import re
from typing import Optional

from communication_handler.constants import CHANNEL_ALLOW_LIST

logger = logging.getLogger(__name__)


class ChannelUtils:
    """Utilities for channel extraction and validation."""
    
    @staticmethod
    def extract_channel_from_query(query: str) -> Optional[str]:
        """Extract channel from user query.
        
        Args:
            query: User's natural language query
            
        Returns:
            Channel ID if found, None otherwise
        """
        # Channel ID pattern (C followed by 10+ alphanumeric characters)
        channel_id_match = re.search(r'\b(C[A-Z0-9]{10,})\b', query)
        if channel_id_match:
            channel_id = channel_id_match.group(1)
            return channel_id if channel_id in CHANNEL_ALLOW_LIST else None
        
        # Channel reference patterns (#channel-name)
        channel_ref_match = re.search(r'#([a-z0-9-]+)', query.lower())
        if channel_ref_match:
            channel_name = channel_ref_match.group(1)
            # Map common channel names to IDs
            channel_mapping = {
                'opensearch-release-manager': 'C096MV7JZ0T',
                'private-oscar-test': 'C09827S7CEB', 
                'opensearch-3-2-0-release': 'C088XMSH4DA',
                'riley-needs-to-lock-in': 'C091EH1JKCL'
            }
            return channel_mapping.get(channel_name)
        
        # Text-based channel mentions
        query_lower = query.lower()
        if 'riley-needs-to-lock-in' in query_lower:
            return 'C096MV7JZ0T'
        elif '3-2-0' in query_lower or '3.2.0' in query_lower or 'release channel' in query_lower:
            return 'C096MV7JZ0T'
        elif 'build channel' in query_lower:
            return 'C09827S7CEB'
        elif 'test channel' in query_lower:
            return 'C091EH1JKCL'
        elif 'dev channel' in query_lower:
            return 'C088XMSH4DA'
        
        return None
    
    @staticmethod
    def validate_channel(channel: str) -> bool:
        """Validate if channel is in allow list.
        
        Args:
            channel: Channel ID to validate
            
        Returns:
            True if channel is allowed, False otherwise
        """
        return channel in CHANNEL_ALLOW_LIST