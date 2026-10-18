using System.IO;
using System.Net;
using LiveViewer.Server.Live;
using LiveViewer.Server.Protocol;
using LiveViewer.Server.Security;
using Xunit;

namespace LiveViewer.Server.Tests
{
    public class PeerPolicyTests
    {
        [Theory]
        [InlineData("127.0.0.1", true)]
        [InlineData("10.1.2.3", true)]
        [InlineData("172.16.0.1", true)]
        [InlineData("172.31.255.255", true)]
        [InlineData("172.32.0.1", false)]
        [InlineData("192.168.1.20", true)]
        [InlineData("169.254.3.4", true)]
        [InlineData("8.8.8.8", false)]
        [InlineData("100.64.0.1", false)]
        [InlineData("::1", true)]
        [InlineData("fe80::1", true)]
        [InlineData("fd12:3456::1", true)]
        [InlineData("2001:db8::1", false)]
        [InlineData("::ffff:192.168.1.5", true)]
        [InlineData("::ffff:8.8.8.8", false)]
        public void AllowsOnlyLocalNetworks(string address, bool allowed)
        {
            Assert.Equal(allowed, new PeerPolicy().IsAllowed(IPAddress.Parse(address)));
        }
    }

    public class HostPolicyTests
    {
        private static readonly HostPolicy Policy = new HostPolicy(4280, new[] { "beatsaber.local", "localhost" });
        private static readonly IPAddress Local = IPAddress.Parse("192.168.1.20");

        [Theory]
        [InlineData("beatsaber.local:4280", true)]
        [InlineData("BeatSaber.Local:4280", true)]
        [InlineData("beatsaber.local.:4280", true)]
        [InlineData("beatsaber.local", true)]
        [InlineData("192.168.1.20:4280", true)]
        [InlineData("192.168.1.21:4280", false)]
        [InlineData("beatsaber.local:443", false)]
        [InlineData("evil.example:4280", false)]
        [InlineData("beatsaber.local.evil.example:4280", false)]
        [InlineData("", false)]
        [InlineData(null, false)]
        [InlineData("beatsaber.local:4280:1", false)]
        [InlineData("beatsaber.local:+4280", false)]
        [InlineData("user@beatsaber.local:4280", false)]
        [InlineData("[::1]:4280", false)]
        public void ChecksHostHeader(string? host, bool allowed)
        {
            Assert.Equal(allowed, Policy.IsAllowedHost(host, Local));
        }

        [Fact]
        public void AcceptsIpv6LiteralOfLocalEndpoint()
        {
            Assert.True(Policy.IsAllowedHost("[fd00::5]:4280", IPAddress.Parse("fd00::5")));
            Assert.True(Policy.IsAllowedHost("192.168.1.20:4280", IPAddress.Parse("::ffff:192.168.1.20")));
        }

        [Theory]
        [InlineData("https://beatsaber.local:4280", "beatsaber.local:4280", true)]
        [InlineData("http://beatsaber.local:4280", "beatsaber.local:4280", false)]
        [InlineData("https://evil.example", "beatsaber.local:4280", false)]
        [InlineData("null", "beatsaber.local:4280", false)]
        [InlineData(null, "beatsaber.local:4280", false)]
        public void ChecksOrigin(string? origin, string host, bool allowed)
        {
            Assert.Equal(allowed, HostPolicy.IsSameOrigin(origin, host));
        }
    }

    public class MapDirectoryTests
    {
        [Fact]
        public void ServesOnlyListedPlainFileNames()
        {
            var dir = Directory.CreateTempSubdirectory().FullName;
            File.WriteAllText(Path.Combine(dir, "Info.dat"), "{}");
            File.WriteAllText(Path.Combine(dir, "secret.txt"), "no");
            File.WriteAllText(Path.Combine(dir, "song.egg"), "ogg");
            var outside = Path.Combine(Path.GetDirectoryName(dir)!, "outside.txt");
            File.WriteAllText(outside, "no");

            var map = new MapDirectory(dir, new[] { "Info.dat", "song.egg", "../outside.txt", "missing.dat" });

            Assert.True(map.TryOpen("Info.dat", out var s1));
            s1.Dispose();
            Assert.True(map.TryOpen("song.egg", out var s2));
            s2.Dispose();
            Assert.False(map.TryOpen("info.dat", out _)); // exact names only
            Assert.False(map.TryOpen("secret.txt", out _));
            Assert.False(map.TryOpen("../outside.txt", out _));
            Assert.False(map.TryOpen("missing.dat", out _));
            Assert.False(map.TryOpen("", out _));
            Assert.False(map.TryOpen("..", out _));
            Assert.False(map.TryOpen(dir + "/Info.dat", out _));
        }
    }

    public class MessageReaderTests
    {
        [Fact]
        public void ParsesHello()
        {
            var bytes = new MessageWriter().U16(2).U8(1).Bytes(new byte[32]).String("Ada").ToArray();
            var hello = ClientMessages.ParseHello(new MessageReader(bytes));
            Assert.Equal(2, hello.ProtocolVersion);
            Assert.NotNull(hello.Credential);
            Assert.Equal("Ada", hello.Name);
        }

        [Fact]
        public void RejectsMalformedMessages()
        {
            Assert.Throws<ProtocolException>(() => ClientMessages.ParseHello(new MessageReader(new byte[] { 1, 0 })));
            Assert.Throws<ProtocolException>(() => ClientMessages.ParseHello(new MessageReader(new byte[] { 1, 0, 2 })));
            Assert.Throws<ProtocolException>(() => ClientMessages.ParseHello(new MessageReader(new byte[] { 1, 0, 0, 9 })));
            Assert.Throws<ProtocolException>(() => ClientMessages.ParseHello(new MessageReader(new byte[] { 1, 0, 1, 1, 2 })));
            Assert.Throws<ProtocolException>(() => ClientMessages.ParsePing(new MessageReader(new MessageWriter().F64(double.NaN).ToArray())));
        }

        [Fact]
        public void RandomInputNeverEscapesAsAnythingButProtocolException()
        {
            var random = new System.Random(1234);
            for (var i = 0; i < 20000; i++)
            {
                var data = new byte[random.Next(0, 64)];
                random.NextBytes(data);
                foreach (var parse in new System.Action<MessageReader>[]
                         {
                             r => ClientMessages.ParseHello(r),
                             r => ClientMessages.ParsePing(r),
                         })
                {
                    try
                    {
                        parse(new MessageReader(data));
                    }
                    catch (ProtocolException)
                    {
                    }
                }
            }
        }
    }
}
