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

        // No 0/O, 1/I/L, 2/Z, 5/S, 8/B: codes are read off a browser and compared in a VR menu.
        private const string CodeAlphabet = "ACDEFGHJKMNPQRTUVWXY34679";

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

        public JoinResult Join(long connectionId, IPAddress address, string label, out string matchCode)
        {
            matchCode = "";
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

        private string NewCode()
        {
            while (true)
            {
                var bytes = DeviceStore.RandomBytes(4);
                var chars = bytes.Select(b => CodeAlphabet[b % CodeAlphabet.Length]).ToArray();
                var code = new string(chars, 0, 2) + "-" + new string(chars, 2, 2);
                if (_pending.All(p => p.MatchCode != code))
                {
                    return code;
                }
            }
        }
    }
}
