using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net;

namespace LiveViewer.Server.Security
{
    /// <summary>
    /// Validates the Host and Origin headers. This is the defense against DNS rebinding (a foreign name resolving
    /// to our address) and against cross-site WebSocket connections from pages on other origins.
    /// </summary>
    public sealed class HostPolicy
    {
        private readonly HashSet<string> _names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly int _port;

        public HostPolicy(int port, IEnumerable<string> names)
        {
            _port = port;
            foreach (var name in names)
            {
                _names.Add(name.TrimEnd('.'));
            }
        }

        public void AddName(string name)
        {
            lock (_names)
            {
                _names.Add(name.TrimEnd('.'));
            }
        }

        /// <summary>
        /// The Host header must name us: one of our configured names, or the literal address the client connected
        /// to. The port, if given, must be ours.
        /// </summary>
        public bool IsAllowedHost(string? hostHeader, IPAddress localAddress)
        {
            if (!TrySplitHost(hostHeader, out var host, out var port))
            {
                return false;
            }

            if (port.HasValue && port.Value != _port)
            {
                return false;
            }

            if (IPAddress.TryParse(host, out var literal))
            {
                return Normalize(literal).Equals(Normalize(localAddress));
            }

            lock (_names)
            {
                return _names.Contains(host.TrimEnd('.'));
            }
        }

        /// <summary>The Origin of a WebSocket request must be exactly our own origin for the Host it used.</summary>
        public static bool IsSameOrigin(string? origin, string hostHeader) =>
            origin != null && string.Equals(origin, "https://" + hostHeader, StringComparison.OrdinalIgnoreCase);

        internal static bool TrySplitHost(string? hostHeader, out string host, out int? port)
        {
            host = string.Empty;
            port = null;
            if (string.IsNullOrEmpty(hostHeader) || hostHeader!.Length > 255)
            {
                return false;
            }

            string portText;
            if (hostHeader[0] == '[')
            {
                var close = hostHeader.IndexOf(']');
                if (close < 0)
                {
                    return false;
                }

                host = hostHeader.Substring(1, close - 1);
                var rest = hostHeader.Substring(close + 1);
                if (rest.Length == 0)
                {
                    return host.Length > 0;
                }

                if (rest[0] != ':')
                {
                    return false;
                }

                portText = rest.Substring(1);
            }
            else
            {
                var colon = hostHeader.IndexOf(':');
                if (colon < 0)
                {
                    host = hostHeader;
                    return IsHostName(host);
                }

                host = hostHeader.Substring(0, colon);
                portText = hostHeader.Substring(colon + 1);
                if (!IsHostName(host))
                {
                    return false;
                }
            }

            if (!int.TryParse(portText, NumberStyles.None, CultureInfo.InvariantCulture, out var p) || p <= 0 || p > 65535)
            {
                return false;
            }

            port = p;
            return host.Length > 0;
        }

        private static bool IsHostName(string host)
        {
            if (host.Length == 0)
            {
                return false;
            }

            foreach (var c in host)
            {
                if (!(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z') && !(c >= '0' && c <= '9') && c != '-' && c != '.')
                {
                    return false;
                }
            }

            return true;
        }

        private static IPAddress Normalize(IPAddress address)
        {
            if (address.IsIPv4MappedToIPv6)
            {
                return address.MapToIPv4();
            }

            if (address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetworkV6 && address.ScopeId != 0)
            {
                // Browsers don't put zone ids in Host headers.
                return new IPAddress(address.GetAddressBytes());
            }

            return address;
        }
    }
}
