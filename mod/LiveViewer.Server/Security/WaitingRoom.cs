using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;

namespace LiveViewer.Server.Security
{
    public sealed class PendingDevice
    {
        public long ConnectionId;
        public string MatchCode = "";
        public IPAddress Address = IPAddress.None;
        public string Label = "";
        public DateTime SinceUtc;
    }

    public enum JoinResult
    {
        Pending,
        RoomFull,
        AddressBusy,
        CoolingDown,
    }

    public enum DecisionKind
    {
        Approved,
        Denied,
        Expired,
    }

    public sealed class Decision
    {
        public long ConnectionId;
        public DecisionKind Kind;

        /// <summary>Set when approved with "remember".</summary>
        public ApprovedDevice? Device;

        /// <summary>Set when approved with "remember"; handed to the browser exactly once.</summary>
        public byte[]? Credential;
    }

    /// <summary>
    /// Devices waiting for the player's approval. Thread-safe; events are raised on the calling thread after the
    /// internal lock is released.
    /// </summary>
    public sealed class WaitingRoom
    {
        public const int MaxPending = 4;
        public static readonly TimeSpan PendingLifetime = TimeSpan.FromMinutes(2);
        public static readonly TimeSpan DenyCooldown = TimeSpan.FromMinutes(1);

        private readonly object _lock = new object();
        private readonly List<PendingDevice> _pending = new List<PendingDevice>();
        private readonly Dictionary<IPAddress, DateTime> _cooldownUntil = new Dictionary<IPAddress, DateTime>();
        private readonly DeviceStore _devices;
        private readonly Func<DateTime> _utcNow;

        public WaitingRoom(DeviceStore devices, Func<DateTime>? utcNow = null)
        {
            _devices = devices;
            _utcNow = utcNow ?? (() => DateTime.UtcNow);
        }

        /// <summary>The pending list changed (for the menu UI).</summary>
        public event Action? Changed;

        /// <summary>A pending device was approved, denied or expired (for the connection hub).</summary>
        public event Action<Decision>? Decided;

        public IReadOnlyList<PendingDevice> Pending
        {
            get
            {
                lock (_lock)
                {
                    return _pending.ToList();
                }
            }
        }

        /// <summary>
        /// Puts a connection in the waiting room. <paramref name="onPending"/> runs with the match code before anyone
        /// is notified, so the client is told it's waiting before an approval can possibly be sent to it.
        /// </summary>
        public JoinResult Join(long connectionId, IPAddress address, string label, Action<string> onPending)
        {
            string matchCode;
            var now = _utcNow();
            lock (_lock)
            {
                if (_cooldownUntil.TryGetValue(address, out var until))
                {
                    if (until > now)
                    {
                        return JoinResult.CoolingDown;
                    }

                    _cooldownUntil.Remove(address);
                }

                if (_pending.Any(p => p.Address.Equals(address)))
                {
                    return JoinResult.AddressBusy;
                }

                if (_pending.Count >= MaxPending)
                {
                    return JoinResult.RoomFull;
                }

                matchCode = NewCode();
                _pending.Add(new PendingDevice
                {
                    ConnectionId = connectionId,
                    MatchCode = matchCode,
                    Address = address,
                    Label = DeviceStore.Sanitize(label),
                    SinceUtc = now,
                });
            }

            onPending(matchCode);
            Changed?.Invoke();
            return JoinResult.Pending;
        }

        /// <summary>Approve a pending device. With <paramref name="remember"/> it gets a credential for later visits.</summary>
        public bool Approve(long connectionId, bool remember)
        {
            PendingDevice? device;
            lock (_lock)
            {
                device = Take(connectionId);
            }

            if (device == null)
            {
                return false;
            }

            var decision = new Decision { ConnectionId = connectionId, Kind = DecisionKind.Approved };
            if (remember)
            {
                decision.Device = _devices.Add(device.Label, out var credential);
                decision.Credential = credential;
            }

            Changed?.Invoke();
            Decided?.Invoke(decision);
            return true;
        }

        public bool Deny(long connectionId)
        {
            PendingDevice? device;
            lock (_lock)
            {
                device = Take(connectionId);
                if (device != null)
                {
                    _cooldownUntil[device.Address] = _utcNow() + DenyCooldown;
                }
            }

            if (device == null)
            {
                return false;
            }

            Changed?.Invoke();
            Decided?.Invoke(new Decision { ConnectionId = connectionId, Kind = DecisionKind.Denied });
            return true;
        }

        /// <summary>The connection went away; drop it silently.</summary>
        public void Leave(long connectionId)
        {
            PendingDevice? device;
            lock (_lock)
            {
                device = Take(connectionId);
            }

            if (device != null)
            {
                Changed?.Invoke();
            }
        }

        /// <summary>Expires old requests. Call periodically.</summary>
        public void Expire()
        {
            var now = _utcNow();
            List<PendingDevice> expired;
            lock (_lock)
            {
                expired = _pending.Where(p => now - p.SinceUtc >= PendingLifetime).ToList();
                foreach (var p in expired)
                {
                    _pending.Remove(p);
                }

                foreach (var address in _cooldownUntil.Where(c => c.Value <= now).Select(c => c.Key).ToList())
                {
                    _cooldownUntil.Remove(address);
                }
            }

            if (expired.Count == 0)
            {
                return;
            }

            Changed?.Invoke();
            foreach (var p in expired)
            {
                Decided?.Invoke(new Decision { ConnectionId = p.ConnectionId, Kind = DecisionKind.Expired });
            }
        }

        private PendingDevice? Take(long connectionId)
        {
            var index = _pending.FindIndex(p => p.ConnectionId == connectionId);
            if (index < 0)
            {
                return null;
            }

            var device = _pending[index];
            _pending.RemoveAt(index);
            return device;
        }

        /// <summary>
        /// Three words from the PGP word list (24 random bits), e.g. "Aztec Istanbul Yucatan". The words are read off
        /// a browser and compared in a VR menu, so they are easier to check than letters and digits.
        /// </summary>
        private string NewCode()
        {
            while (true)
            {
                var b = DeviceStore.RandomBytes(3);
                var code = WordList.Even[b[0]] + " " + WordList.Odd[b[1]] + " " + WordList.Even[b[2]];
                if (_pending.All(p => !SameCode(p.MatchCode, code)))
                {
                    return code;
                }
            }
        }

        /// <summary>Finds a pending device by its code, ignoring case and how the words are separated.</summary>
        public PendingDevice? FindByCode(string code)
        {
            var wanted = NormalizeCode(code);
            lock (_lock)
            {
                return _pending.FirstOrDefault(p => NormalizeCode(p.MatchCode) == wanted);
            }
        }

        private static bool SameCode(string a, string b) => NormalizeCode(a) == NormalizeCode(b);

        private static string NormalizeCode(string code) =>
            string.Join(" ", code.ToLowerInvariant().Split(new[] { ' ', '-', '\t' }, StringSplitOptions.RemoveEmptyEntries));
    }
}
