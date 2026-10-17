import asyncio
import socket
import unittest
from unittest.mock import patch
from bot import ResilientResolver, DISCORD_GATEWAY_DEFAULT_IPS, DISCORD_API_DEFAULT_IPS


class TestResilientResolver(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.resolver = ResilientResolver()

    async def test_successful_resolution_populates_stale_cache(self):
        """Verifies that normal resolution succeeds and caches the IP records."""
        res = await self.resolver.resolve("gateway.discord.gg", 443)
        self.assertIsInstance(res, list)
        self.assertGreater(len(res), 0)
        cache_key = ("gateway.discord.gg", 443, socket.AddressFamily.AF_UNSPEC)
        self.assertIn(cache_key, self.resolver._stale_cache)

    @patch("asyncio.sleep", return_value=None)
    async def test_stale_cache_fallback_on_dns_failure(self, _mock_sleep):
        """Verifies that when DNS lookup fails with Errno -3, the resolver returns the stale cache."""
        mock_records = [
            {
                "hostname": "gateway-us-east1-c.discord.gg",
                "host": "162.159.130.234",
                "port": 443,
                "family": socket.AF_INET,
                "proto": 6,
                "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
            }
        ]
        self.resolver._stale_cache[("gateway-us-east1-c.discord.gg", 443, socket.AddressFamily.AF_UNSPEC)] = mock_records

        # Simulate host resolver failure via getaddrinfo
        with patch.object(
            self.resolver._loop,
            "getaddrinfo",
            side_effect=socket.gaierror(-3, "Temporary failure in name resolution"),
        ):
            res = await self.resolver.resolve("gateway-us-east1-c.discord.gg", 443)
            self.assertEqual(res, mock_records)
            self.assertEqual(res[0]["host"], "162.159.130.234")

    @patch("asyncio.sleep", return_value=None)
    async def test_emergency_anycast_fallback_for_uncached_discord_gateway(self, _mock_sleep):
        """Verifies that an un-cached Discord gateway endpoint falls back to Anycast gateway IPs."""
        self.resolver._stale_cache.clear()

        with patch.object(
            self.resolver._loop,
            "getaddrinfo",
            side_effect=socket.gaierror(-3, "Temporary failure in name resolution"),
        ):
            res = await self.resolver.resolve("gateway-us-east1-c.discord.gg", 443)
            self.assertEqual(len(res), len(DISCORD_GATEWAY_DEFAULT_IPS))
            self.assertEqual(res[0]["hostname"], "gateway-us-east1-c.discord.gg")
            self.assertIn(res[0]["host"], DISCORD_GATEWAY_DEFAULT_IPS)

    @patch("asyncio.sleep", return_value=None)
    async def test_emergency_anycast_fallback_for_uncached_discord_api(self, _mock_sleep):
        """Verifies that discord.com falls back to Discord API Anycast IPs on DNS failure."""
        self.resolver._stale_cache.clear()

        with patch.object(
            self.resolver._loop,
            "getaddrinfo",
            side_effect=socket.gaierror(-3, "Temporary failure in name resolution"),
        ):
            res = await self.resolver.resolve("discord.com", 443)
            self.assertEqual(len(res), len(DISCORD_API_DEFAULT_IPS))
            self.assertEqual(res[0]["hostname"], "discord.com")
            self.assertIn(res[0]["host"], DISCORD_API_DEFAULT_IPS)

    @patch("asyncio.sleep", return_value=None)
    async def test_unknown_host_without_fallback_raises_error(self, _mock_sleep):
        """Verifies that non-discord hosts without prior cache still raise socket.gaierror."""
        self.resolver._stale_cache.clear()

        with patch.object(
            self.resolver._loop,
            "getaddrinfo",
            side_effect=socket.gaierror(-3, "Temporary failure in name resolution"),
        ):
            with self.assertRaises(socket.gaierror):
                await self.resolver.resolve("random-nonexistent-domain-123456.org", 443)


if __name__ == "__main__":
    unittest.main()
