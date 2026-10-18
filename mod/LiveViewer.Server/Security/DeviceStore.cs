using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

namespace LiveViewer.Server.Security
{
    public sealed class ApprovedDevice
    {
        public string Id = "";
        public string Label = "";
        public DateTime CreatedUtc;
        public DateTime LastSeenUtc;
        internal string CredentialHash = "";
    }

    /// <summary>
    /// Devices the player chose to remember. Only SHA-256 hashes of the credentials are kept; the credentials are
    /// 256-bit random values, so a plain hash is sufficient.
    /// </summary>
    public sealed class DeviceStore
    {
        public const int MaxDevices = 64;

        private readonly object _lock = new object();
        private readonly string? _path;
        private readonly List<ApprovedDevice> _devices = new List<ApprovedDevice>();

        /// <param name="path">File to persist to, or <c>null</c> to keep devices in memory only.</param>
        public DeviceStore(string? path)
        {
            _path = path;
            if (path != null && File.Exists(path))
            {
                Load(path);
            }
        }

        /// <summary>Raised after a device is added or removed (on the calling thread).</summary>
        public event Action? Changed;

        /// <summary>Raised when a device is removed, with its id, so live connections can be dropped.</summary>
        public event Action<string>? Revoked;

        public IReadOnlyList<ApprovedDevice> List()
        {
            lock (_lock)
            {
                return _devices.ToList();
            }
        }

        /// <summary>Creates a remembered device and returns the credential to hand to the browser.</summary>
        public ApprovedDevice Add(string label, out byte[] credential)
        {
            credential = RandomBytes(32);
            var device = new ApprovedDevice
            {
                Id = ToHex(RandomBytes(6)),
                Label = Sanitize(label),
                CreatedUtc = DateTime.UtcNow,
                LastSeenUtc = DateTime.UtcNow,
                CredentialHash = Hash(credential),
            };

            lock (_lock)
            {
                if (_devices.Count >= MaxDevices)
                {
                    // Forget the device that hasn't been seen for the longest time.
                    _devices.Remove(_devices.OrderBy(d => d.LastSeenUtc).First());
                }

                _devices.Add(device);
                Save();
            }

            Changed?.Invoke();
            return device;
        }

        public ApprovedDevice? Match(byte[] credential)
        {
            TryAuthenticate(credential, _ => true, out var device);
            return device;
        }

        /// <summary>
        /// Matches a credential and registers the live connection while removal is excluded. The callback must not
        /// call back into this store. This closes the gap in which a device could be revoked after matching but before
        /// its connection became visible to the revocation handler.
        /// </summary>
        internal bool TryAuthenticate(byte[] credential, Func<ApprovedDevice, bool> register, out ApprovedDevice? device)
        {
            var hash = Hash(credential);
            lock (_lock)
            {
                device = _devices.FirstOrDefault(d => FixedTimeEquals(d.CredentialHash, hash));
                if (device == null || !register(device))
                {
                    return false;
                }

                device.LastSeenUtc = DateTime.UtcNow;
                Save();
                return true;
            }
        }

        public bool Remove(string id)
        {
            lock (_lock)
            {
                if (_devices.RemoveAll(d => d.Id == id) == 0)
                {
                    return false;
                }

                Save();
            }

            Revoked?.Invoke(id);
            Changed?.Invoke();
            return true;
        }

        internal static string Hash(byte[] credential)
        {
            using var sha = SHA256.Create();
            return ToHex(sha.ComputeHash(credential));
        }

        private static bool FixedTimeEquals(string a, string b)
        {
            if (a.Length != b.Length)
            {
                return false;
            }

            var diff = 0;
            for (var i = 0; i < a.Length; i++)
            {
                diff |= a[i] ^ b[i];
            }

            return diff == 0;
        }

        private void Load(string path)
        {
            foreach (var line in File.ReadAllLines(path, Encoding.UTF8))
            {
                var parts = line.Split('\t');
                if (parts.Length != 5)
                {
                    continue;
                }

                try
                {
                    _devices.Add(new ApprovedDevice
                    {
                        Id = parts[0],
                        CredentialHash = parts[1],
                        CreatedUtc = DateTime.Parse(parts[2], CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind),
                        LastSeenUtc = DateTime.Parse(parts[3], CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind),
                        Label = Encoding.UTF8.GetString(Convert.FromBase64String(parts[4])),
                    });
                }
                catch (FormatException)
                {
                    // Skip damaged lines rather than refusing to start.
                }
            }
        }

        private void Save()
        {
            if (_path == null)
            {
                return;
            }

            var lines = _devices.Select(d => string.Join("\t",
                d.Id,
                d.CredentialHash,
                d.CreatedUtc.ToString("o", CultureInfo.InvariantCulture),
                d.LastSeenUtc.ToString("o", CultureInfo.InvariantCulture),
                Convert.ToBase64String(Encoding.UTF8.GetBytes(d.Label))));
            var tmp = _path + ".tmp";
            File.WriteAllLines(tmp, lines, new UTF8Encoding(false));
            if (File.Exists(_path))
            {
                File.Delete(_path);
            }

            File.Move(tmp, _path);
        }

        internal static string Sanitize(string label)
        {
            var sb = new StringBuilder();
            foreach (var c in label ?? string.Empty)
            {
                if (!char.IsControl(c))
                {
                    sb.Append(c);
                }

                if (sb.Length >= 64)
                {
                    break;
                }
            }

            return sb.ToString();
        }

        internal static byte[] RandomBytes(int count)
        {
            var bytes = new byte[count];
            using var rng = RandomNumberGenerator.Create();
            rng.GetBytes(bytes);
            return bytes;
        }

        private static string ToHex(byte[] bytes) => string.Concat(bytes.Select(b => b.ToString("x2")));
    }
}
