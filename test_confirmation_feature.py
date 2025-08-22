#!/usr/bin/env python3
"""
Test script for the confirmation warning reaction feature.
"""

def test_confirmation_detection():
    """Test the confirmation detection logic."""
    
    # Test confirmation marker detection
    test_responses = [
        "[CONFIRMATION_REQUIRED] I've prepared a message to send...",
        "Regular response without confirmation",
        "Here's the job details [CONFIRMATION_REQUIRED] for your review...",
        "Another normal response",
        "I've prepared the message [CONFIRMATION_REQUIRED] please confirm"
    ]
    
    for response in test_responses:
        requires_confirmation = '[CONFIRMATION_REQUIRED]' in response
        cleaned_response = response.replace('[CONFIRMATION_REQUIRED]', '').strip() if requires_confirmation else response
        
        print(f"Original: {response[:60]}...")
        print(f"Requires confirmation: {requires_confirmation}")
        print(f"Cleaned: {cleaned_response[:60]}...")
        print("---")

def test_confirmation_response_detection():
    """Test that we no longer need confirmation response detection."""
    print("Confirmation response detection is no longer needed!")
    print("The warning reaction will remain until the user provides confirmation")
    print("and the agent proceeds with the action (which will be a new conversation turn)")

if __name__ == "__main__":
    print("Testing confirmation detection...")
    test_confirmation_detection()
    print("\nTesting confirmation response detection...")
    test_confirmation_response_detection()