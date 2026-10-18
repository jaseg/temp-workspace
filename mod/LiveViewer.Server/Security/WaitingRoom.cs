using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;

namespace LiveViewer.Server.Security
{
    public sealed class PendingDevice
    {
        public long ConnectionId;

        /// <summary>The name the viewer chose, unique among waiting devices. The player approves by this name.</summary>
        public string Name = "";

        public IPAddress Address = IPAddress.None;

        /// <summary>The browser ("Firefox on Linux"), for display.</summary>
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

        public const int MaxNameLength = 32;

        /// <summary>
        /// Puts a connection in the waiting room under <paramref name="name"/> (cleaned up, and numbered if another
        /// waiting device has it). <paramref name="onPending"/> runs with the final name before anyone is notified, so
        /// the client is told it's waiting before an approval can possibly be sent to it.
        /// </summary>
        public JoinResult Join(long connectionId, IPAddress address, string name, string label, Action<string> onPending)
        {
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

                name = UniqueName(CleanName(name, connectionId));
                _pending.Add(new PendingDevice
                {
                    ConnectionId = connectionId,
                    Name = name,
                    Address = address,
                    Label = DeviceStore.Sanitize(label),
                    SinceUtc = now,
                });
            }

            onPending(name);
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
                decision.Device = _devices.Add(device.Name + " · " + device.Label, out var credential);
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
        /// A display name: whitespace runs become one space; control characters and characters outside the basic
        /// plane (emoji, which the game's font can't show) are dropped; at most <see cref="MaxNameLength"/>
        /// characters. Empty names become "Viewer &lt;n&gt;".
        /// </summary>
        public static string CleanName(string? name, long connectionId)
        {
            var sb = new System.Text.StringBuilder();
            foreach (var c in name ?? "")
            {
                if (char.IsWhiteSpace(c))
                {
                    if (sb.Length > 0 && sb[sb.Length - 1] != ' ')
                    {
                        sb.Append(' ');
                    }
                }
                else if (!char.IsControl(c) && !char.IsSurrogate(c) && sb.Length < MaxNameLength)
                {
                    sb.Append(c);
                }
            }

            var clean = sb.ToString().Trim();
            return clean.Length > 0 ? clean : "Viewer " + connectionId;
        }

        /// <summary>Finds a waiting device by name, ignoring case and extra spaces.</summary>
        public PendingDevice? FindByName(string name)
        {
            var wanted = Normalize(name);
            lock (_lock)
            {
                return _pending.FirstOrDefault(p => Normalize(p.Name) == wanted);
            }
        }

        // Called with the lock held. "Alex" becomes "Alex 2" if another waiting device is called "Alex".
        private string UniqueName(string name)
        {
            var candidate = name;
            for (var n = 2; _pending.Any(p => Normalize(p.Name) == Normalize(candidate)); n++)
            {
                var suffix = " " + n;
                candidate = (name.Length + suffix.Length > MaxNameLength ? name.Substring(0, MaxNameLength - suffix.Length) : name) + suffix;
            }

            return candidate;
        }

        private static string Normalize(string name) =>
            string.Join(" ", name.ToLowerInvariant().Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries));
    }
}
