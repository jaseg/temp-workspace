using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using BeatSaberMarkupLanguage.Attributes;
using BeatSaberMarkupLanguage.Components;
using BeatSaberMarkupLanguage.ViewControllers;
using LiveViewer.Server.Security;
using Zenject;

namespace LiveViewer.Plugin.UI
{
    /// <summary>
    /// The Live Viewer menu screen: where to watch, the waiting room and remembered devices. Everything here runs on
    /// the game thread; <see cref="MenuButtonManager"/> calls <see cref="Refresh"/> when the server reports changes.
    /// </summary>
    [ViewDefinition("LiveViewer.Plugin.UI.LiveViewController.bsml")]
    internal sealed class LiveViewController : BSMLAutomaticViewController
    {
        [Inject]
        private readonly LiveService _service = null!;

        [UIComponent("pending-list")]
        private readonly CustomCellListTableData _pendingList = null!;

        [UIComponent("devices-list")]
        private readonly CustomCellListTableData _devicesList = null!;

        [UIValue("pending")]
        private readonly List<object> _pending = new List<object>();

        [UIValue("devices")]
        private readonly List<object> _devices = new List<object>();

        [UIValue("status-text")]
        private string StatusText
        {
            get
            {
                var server = _service.Server;
                if (server == null)
                {
                    return _service.Problem != null
                        ? "<color=#ff8080>The server isn't running:</color> " + _service.Problem
                        : "Starting…";
                }

                var urls = server.Urls;
                return "Watch in a browser on this network:\n<size=130%><color=#80d0ff>" + urls.FirstOrDefault() + "</color></size>"
                       + (urls.Count > 1 ? "\nor " + string.Join("  ", urls.Skip(1).Take(2)) : "");
            }
        }

        [UIValue("fingerprint-text")]
        private string FingerprintText
        {
            get
            {
                var server = _service.Server;
                if (server == null)
                {
                    return "";
                }

                var viewers = server.ConnectedViewers;
                return $"Certificate {server.CertificateFingerprint.Substring(0, Math.Min(23, server.CertificateFingerprint.Length))}…   "
                       + (viewers == 1 ? "1 viewer" : $"{viewers} viewers");
            }
        }

        [UIValue("has-pending")]
        private bool HasPending => _pending.Count > 0;

        [UIValue("no-pending")]
        private bool NoPending => _pending.Count == 0 && _service.Server != null;

        [UIValue("has-devices")]
        private bool HasDevices => _devices.Count > 0;

        [UIValue("devices-text")]
        private string DevicesText => _devices.Count == 0 ? "No remembered devices"
            : _devices.Count == 1 ? "1 remembered device" : $"{_devices.Count} remembered devices";

        [UIValue("beatleader")]
        private bool BeatLeader
        {
            get => _service.Config.BeatLeaderStats;
            set => _service.Config.BeatLeaderStats = value;
        }

        public void Refresh()
        {
            var server = _service.Server;
            _pending.Clear();
            _devices.Clear();
            if (server != null)
            {
                _pending.AddRange(server.WaitingRoom.Pending.Select(p => (object) new PendingCell(this, p)));
                _devices.AddRange(server.Devices.List().OrderByDescending(d => d.LastSeenUtc).Select(d => (object) new DeviceCell(this, d)));
            }

            if (!isActivated)
            {
                return;
            }

            _pendingList?.TableView.ReloadData();
            _devicesList?.TableView.ReloadData();
            foreach (var name in new[] { "status-text", "fingerprint-text", "has-pending", "no-pending", "has-devices", "devices-text" })
            {
                NotifyPropertyChanged(name);
            }
        }

        protected override void DidActivate(bool firstActivation, bool addedToHierarchy, bool screenSystemEnabling)
        {
            base.DidActivate(firstActivation, addedToHierarchy, screenSystemEnabling);
            Refresh();
        }

        private void Approve(PendingDevice device, bool remember)
        {
            _service.Server?.WaitingRoom.Approve(device.ConnectionId, remember);
            Refresh();
        }

        private void Deny(PendingDevice device)
        {
            _service.Server?.WaitingRoom.Deny(device.ConnectionId);
            Refresh();
        }

        private void Revoke(ApprovedDevice device)
        {
            _service.Server?.Devices.Remove(device.Id);
            Refresh();
        }

        private static string Ago(DateTime utc)
        {
            var span = DateTime.UtcNow - utc;
            return span.TotalMinutes < 1 ? "just now"
                : span.TotalHours < 1 ? $"{(int) span.TotalMinutes} min ago"
                : span.TotalDays < 1 ? $"{(int) span.TotalHours} h ago"
                : $"{(int) span.TotalDays} days ago";
        }

        private static string Escape(string text) => text.Replace("<", "<​");

        private sealed class PendingCell
        {
            private readonly LiveViewController _owner;
            private readonly PendingDevice _device;

            public PendingCell(LiveViewController owner, PendingDevice device)
            {
                _owner = owner;
                _device = device;
            }

            [UIValue("code")]
            private string Code => "<b>" + Escape(_device.MatchCode) + "</b>";

            [UIValue("detail")]
            private string Detail => Escape(_device.Label) + "  ·  " + _device.Address + "  ·  " + Ago(_device.SinceUtc);

            [UIAction("allow-once")]
            private void AllowOnce() => _owner.Approve(_device, false);

            [UIAction("allow-always")]
            private void AllowAlways() => _owner.Approve(_device, true);

            [UIAction("deny")]
            private void DenyDevice() => _owner.Deny(_device);
        }

        private sealed class DeviceCell
        {
            private readonly LiveViewController _owner;
            private readonly ApprovedDevice _device;

            public DeviceCell(LiveViewController owner, ApprovedDevice device)
            {
                _owner = owner;
                _device = device;
            }

            [UIValue("label")]
            private string Label => Escape(_device.Label);

            [UIValue("seen")]
            private string Seen => "Last seen " + Ago(_device.LastSeenUtc) + ", added " + _device.CreatedUtc.ToLocalTime().ToString("yyyy-MM-dd");

            [UIAction("revoke")]
            private void Revoke() => _owner.Revoke(_device);
        }
    }
}
