"""
tests/test_levels_progression.py - 12-Tier Discipline Progression and Level Up Tests
"""
from unittest.mock import MagicMock
from levels import get_level_info, get_all_ranks, check_level_up, RANKS
from ui.embeds import build_profile_embed
from tests.base import WinterArcTestCase


class TestLevelHierarchy(WinterArcTestCase):
    """Verifies the 12-tier discipline rank hierarchy, points thresholds, and mathematical continuity."""

    def test_twelve_tier_ranks_and_threshold_definitions(self):
        """Verifies that all 12 rank tiers exist with correct titles and progression steps."""
        self.assertEqual(len(RANKS), 12)
        all_r = get_all_ranks()
        self.assertEqual(len(all_r), 12)

        # Level 1: Initiate
        l1 = get_level_info(0)
        self.assertEqual(l1["level"], 1)
        self.assertEqual(l1["title"], "Initiate")

        # Level 2: Novice
        l2 = get_level_info(500)
        self.assertEqual(l2["level"], 2)
        self.assertEqual(l2["title"], "Novice")

        # Level 7: Iron
        l7 = get_level_info(5500)
        self.assertEqual(l7["level"], 7)
        self.assertEqual(l7["title"], "Iron")

        # Level 12: Apex
        l12 = get_level_info(12000)
        self.assertEqual(l12["level"], 12)
        self.assertEqual(l12["title"], "Apex")
        self.assertTrue(l12["is_apex"])
        self.assertEqual(l12["tier_pct"], 100)

    def test_detailed_tier_boundaries_and_xp_progress_calculations(self):
        """Verifies boundaries for every single tier and remaining XP calculations."""
        expected_titles = [
            (0, 1, "Initiate"),
            (499, 1, "Initiate"),
            (500, 2, "Novice"),
            (1199, 2, "Novice"),
            (1200, 3, "Challenger"),
            (1999, 3, "Challenger"),
            (2000, 4, "Dedicated"),
            (2999, 4, "Dedicated"),
            (3000, 5, "Disciplined"),
            (4199, 5, "Disciplined"),
            (4200, 6, "Hardened"),
            (5499, 6, "Hardened"),
            (5500, 7, "Iron"),
            (6999, 7, "Iron"),
            (7000, 8, "Vanguard"),
            (8499, 8, "Vanguard"),
            (8500, 9, "Relentless"),
            (9799, 9, "Relentless"),
            (9800, 10, "Veteran"),
            (10799, 10, "Veteran"),
            (10800, 11, "Master"),
            (11999, 11, "Master"),
            (12000, 12, "Apex"),
            (15000, 12, "Apex"),
        ]

        for pts, exp_lvl, exp_title in expected_titles:
            info = get_level_info(pts)
            self.assertEqual(info["level"], exp_lvl, f"Failed level for {pts} pts")
            self.assertEqual(info["title"], exp_title, f"Failed title for {pts} pts")

        # Test next level progress calculations at 180 pts (Level 1: Initiate -> Level 2: Novice at 500)
        info180 = get_level_info(180)
        self.assertEqual(info180["pts_to_next"], 320)
        self.assertEqual(info180["points_in_tier"], 180)
        self.assertEqual(info180["next_title"], "Novice")
        self.assertEqual(info180["next_level"], 2)


class TestLevelProgressionTriggers(WinterArcTestCase):
    """Verifies level-up detection triggers, multi-tier leaps, and profile embed visualization."""

    def test_level_up_triggers_and_multi_tier_leaps(self):
        """Verifies trigger detection across tier crossings and multiple-level jumps."""
        # Crossing 499 -> 500 (Level 1 to Level 2)
        lvl_up = check_level_up(499, 500)
        self.assertIsNotNone(lvl_up)
        self.assertEqual(lvl_up["level"], 2)
        self.assertEqual(lvl_up["title"], "Novice")

        # No level up within same tier (500 -> 600)
        no_lvl = check_level_up(500, 600)
        self.assertIsNone(no_lvl)

        # Big leap crossing multiple levels (0 -> 2500, Level 1 to Level 4)
        big_lvl = check_level_up(0, 2500)
        self.assertIsNotNone(big_lvl)
        self.assertEqual(big_lvl["level"], 4)
        self.assertEqual(big_lvl["title"], "Dedicated")

    def test_profile_embed_level_progression_visualization(self):
        """Verifies level progression bar and remaining points in build_profile_embed."""
        mock_user = self.create_mock_member(user_id=1001, display_name="Vishnu")
        mock_user.avatar = None
        user_record = {"joined_at": "2026-09-18 10:00:00", "frost_shields": 1}
        stats_data = {"lifetime_points": 180}

        profile_embed = build_profile_embed(mock_user, user_record, streak=5, stats_data=stats_data)
        self.assertEmbedDescriptionContains(
            profile_embed,
            "Level Progression",
            "Level 2 (Novice)",
            "180 / 500 PTS",
            "320 pts remaining",
            "All-Time Rank",
            "Discipline Rank",
            "Today's Daily Progress",
        )
        self.assertNotIn("90-Day Arc Progress", profile_embed.description)
