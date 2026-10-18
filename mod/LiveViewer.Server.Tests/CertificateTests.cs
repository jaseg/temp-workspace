using System;
using System.Linq;
using System.Net;
using LiveViewer.Server.Security;
using Org.BouncyCastle.Asn1;
using Xunit;

namespace LiveViewer.Server.Tests
{
    public class CertificateTests
    {
        [Fact]
        public void GeneratedPfxIsDerSoMonoCanReadIt()
        {
            var pfx = CertificateStore.Generate(new[] { "beatsaber.local" }, new[] { IPAddress.Parse("192.168.1.2") }, DateTime.UtcNow);

            // Mono's PKCS#12 parser fails on BER's indefinite lengths; re-encoding as DER must change nothing.
            Assert.True(Asn1Object.FromByteArray(pfx).GetDerEncoded().SequenceEqual(pfx));
            var certificate = CertificateStore.Load(pfx);
            Assert.True(certificate.HasPrivateKey);
        }
    }
}
