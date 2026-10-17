using System.Net;
using System.Net.Sockets;

namespace LiveViewer.Server.Security
{
    /// <summary>
    /// Which remote addresses may connect at all. Checked right after accept, before TLS.
    /// By default only loopback, private (RFC 1918), link-local and IPv6 unique-local peers are allowed.
    /// </summary>
    public sealed class PeerPolicy
    {
        public bool AllowAnyAddress { get; set; }

        public bool IsAllowed(IPAddress address)
        {
            if (AllowAnyAddress)
            {
                return true;
            }

            if (address.IsIPv4MappedToIPv6)
            {
                address = address.MapToIPv4();
            }

            if (IPAddress.IsLoopback(address))
            {
                return true;
            }

            var b = address.GetAddressBytes();
            if (address.AddressFamily == AddressFamily.InterNetwork)
            {
                return b[0] == 10
                       || (b[0] == 172 && (b[1] & 0xF0) == 16)
                       || (b[0] == 192 && b[1] == 168)
                       || (b[0] == 169 && b[1] == 254);
            }

            if (address.AddressFamily == AddressFamily.InterNetworkV6)
            {
                return address.IsIPv6LinkLocal
                       || (b[0] & 0xFE) == 0xFC; // fc00::/7 unique local
            }

            return false;
        }
    }
}
