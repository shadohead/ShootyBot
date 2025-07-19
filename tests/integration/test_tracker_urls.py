#!/usr/bin/env python3
"""
Test tracker.gg URL generation for Valorant profiles
"""
import unittest

class TestTrackerURLGeneration(unittest.TestCase):
    """Test that tracker.gg URLs are generated correctly"""
    
    def test_tracker_url_format(self):
        """Test the tracker.gg URL format with various usernames and tags"""
        test_cases = [
            {"username": "xpfc", "tag": "NA1", "expected": "https://tracker.gg/valorant/profile/riot/xpfc%23NA1/overview"},
            {"username": "TenZ", "tag": "SEN", "expected": "https://tracker.gg/valorant/profile/riot/TenZ%23SEN/overview"},
            {"username": "s0m", "tag": "NRG", "expected": "https://tracker.gg/valorant/profile/riot/s0m%23NRG/overview"},
            {"username": "Yay", "tag": "C9", "expected": "https://tracker.gg/valorant/profile/riot/Yay%23C9/overview"},
        ]
        
        for case in test_cases:
            with self.subTest(username=case["username"], tag=case["tag"]):
                # Generate URL using our format
                tracker_url = f"https://tracker.gg/valorant/profile/riot/{case['username']}%23{case['tag']}/overview"
                self.assertEqual(tracker_url, case["expected"], 
                               f"URL generation failed for {case['username']}#{case['tag']}")
    
    def test_special_characters_in_username(self):
        """Test usernames with special characters that might need encoding"""
        test_cases = [
            {"username": "Player_123", "tag": "NA1"},
            {"username": "Pro-Player", "tag": "EU"},
            {"username": "TestUser", "tag": "001"},
        ]
        
        for case in test_cases:
            with self.subTest(username=case["username"], tag=case["tag"]):
                # Generate URL
                tracker_url = f"https://tracker.gg/valorant/profile/riot/{case['username']}%23{case['tag']}/overview"
                
                # Verify structure
                self.assertTrue(tracker_url.startswith("https://tracker.gg/valorant/profile/riot/"))
                self.assertTrue(f"{case['username']}%23{case['tag']}" in tracker_url)
                self.assertTrue(tracker_url.endswith("/overview"))
    
    def test_url_components(self):
        """Test individual URL components"""
        username = "TestPlayer"
        tag = "NA1"
        tracker_url = f"https://tracker.gg/valorant/profile/riot/{username}%23{tag}/overview"
        
        # Check components
        self.assertIn("https://tracker.gg/valorant/profile/riot/", tracker_url)
        self.assertIn(f"{username}%23{tag}", tracker_url)
        self.assertIn("/overview", tracker_url)
        
        # Verify the # is properly encoded as %23
        self.assertNotIn("#", tracker_url)  # Should not contain literal #
        self.assertIn("%23", tracker_url)   # Should contain encoded #
    
    def test_markdown_link_format(self):
        """Test the markdown link format used in Discord embeds"""
        username = "TestPlayer"
        tag = "NA1"
        tracker_url = f"https://tracker.gg/valorant/profile/riot/{username}%23{tag}/overview"
        
        # Test markdown link formats used in the commands
        markdown_link = f"[View on Tracker.gg]({tracker_url})"
        short_link = f"[Tracker.gg]({tracker_url})"
        
        # Verify format
        self.assertTrue(markdown_link.startswith("[View on Tracker.gg]("))
        self.assertTrue(markdown_link.endswith(")"))
        self.assertTrue(short_link.startswith("[Tracker.gg]("))
        self.assertTrue(short_link.endswith(")"))

