using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using Org.BouncyCastle.Asn1.X509;
using Org.BouncyCastle.Crypto;
using Org.BouncyCastle.Crypto.Generators;
using Org.BouncyCastle.Crypto.Operators;
using Org.BouncyCastle.Math;
using Org.BouncyCastle.Pkcs;
using Org.BouncyCastle.Security;
using Org.BouncyCastle.Utilities;
using Org.BouncyCastle.X509;
using X509Certificate2 = System.Security.Cryptography.X509Certificates.X509Certificate2;

namespace LiveViewer.Server.Security
{
    /// <summary>
    /// Loads the server's self-signed TLS certificate, generating it on first start.
    /// Generation uses BouncyCastle so it doesn't depend on what the game's Mono runtime implements.
    /// RSA rather than ECDSA because Mono's X509Certificate2 only handles RSA/DSA private keys.
    /// </summary>
    public static class CertificateStore
    {
        private const string FileName = "server.pfx";

        // The file sits next to the mod's config and isn't a secret store; the password only satisfies PKCS#12.
        private const string Password = "beat-saber-live-viewer";

        // Browsers reject server certificates valid for more than 398 days, even self-signed ones in some cases.
        private static readonly TimeSpan Validity = TimeSpan.FromDays(397);
        private static readonly TimeSpan RenewBefore = TimeSpan.FromDays(14);

        public static X509Certificate2 LoadOrCreate(string directory, IEnumerable<string> dnsNames, IEnumerable<IPAddress> addresses, Action<string>? log = null)
        {
            Directory.CreateDirectory(directory);
            var path = Path.Combine(directory, FileName);
            if (File.Exists(path))
            {
                try
                {
                    var existing = Load(File.ReadAllBytes(path));
                    if (existing.NotAfter.ToUniversalTime() - DateTime.UtcNow > RenewBefore)
                    {
                        return existing;
                    }

                    log?.Invoke("TLS certificate is about to expire; generating a new one.");
                }
                catch (CryptographicException e)
                {
                    log?.Invoke("Stored TLS certificate is unreadable (" + e.Message + "); generating a new one.");
                }
            }

            var pfx = Generate(dnsNames, addresses, DateTime.UtcNow);
            var tmp = path + ".tmp";
            File.WriteAllBytes(tmp, pfx);
            if (File.Exists(path))
            {
                File.Delete(path);
            }

            File.Move(tmp, path);
            log?.Invoke("Generated a new TLS certificate.");
            return Load(pfx);
        }

        public static void Delete(string directory)
        {
            var path = Path.Combine(directory, FileName);
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }

        /// <summary>SHA-256 over the DER certificate, as browsers display it ("AB:CD:...").</summary>
        public static string Fingerprint(X509Certificate2 certificate)
        {
            using var sha = SHA256.Create();
            var hash = sha.ComputeHash(certificate.RawData);
            return string.Join(":", hash.Select(b => b.ToString("X2")));
        }

        internal static X509Certificate2 Load(byte[] pfx) =>
            new X509Certificate2(pfx, Password, X509KeyStorageFlags.Exportable);

        internal static byte[] Generate(IEnumerable<string> dnsNames, IEnumerable<IPAddress> addresses, DateTime now)
        {
            var random = new SecureRandom();
            var keyGenerator = new RsaKeyPairGenerator();
            keyGenerator.Init(new KeyGenerationParameters(random, 2048));
            var keyPair = keyGenerator.GenerateKeyPair();

            var name = new X509Name("CN=Beat Saber Live Viewer");
            var generator = new X509V3CertificateGenerator();
            generator.SetSerialNumber(BigIntegers.CreateRandomInRange(BigInteger.One, BigInteger.One.ShiftLeft(127), random));
            generator.SetIssuerDN(name);
            generator.SetSubjectDN(name);
            generator.SetNotBefore(now.AddDays(-1));
            generator.SetNotAfter(now.Add(Validity));
            generator.SetPublicKey(keyPair.Public);

            var altNames = dnsNames.Distinct(StringComparer.OrdinalIgnoreCase)
                .Select(n => new GeneralName(GeneralName.DnsName, n))
                .Concat(addresses.Distinct().Select(a => new GeneralName(GeneralName.IPAddress, a.ToString())))
                .ToArray();
            generator.AddExtension(X509Extensions.BasicConstraints, true, new BasicConstraints(false));
            generator.AddExtension(X509Extensions.KeyUsage, true, new KeyUsage(KeyUsage.DigitalSignature | KeyUsage.KeyEncipherment));
            generator.AddExtension(X509Extensions.ExtendedKeyUsage, false, new ExtendedKeyUsage(KeyPurposeID.id_kp_serverAuth));
            if (altNames.Length > 0)
            {
                generator.AddExtension(X509Extensions.SubjectAlternativeName, false, new GeneralNames(altNames));
            }

            var certificate = generator.Generate(new Asn1SignatureFactory("SHA256WITHRSA", keyPair.Private, random));

            var store = new Pkcs12StoreBuilder().Build();
            store.SetKeyEntry("server", new AsymmetricKeyEntry(keyPair.Private), new[] { new X509CertificateEntry(certificate) });
            using var stream = new MemoryStream();
            store.Save(stream, Password.ToCharArray(), random);
            return stream.ToArray();
        }
    }
}
