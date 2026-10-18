using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using LiveViewer.Server.Security;
using Xunit;

namespace LiveViewer.Server.Tests
{
    public class WaitingRoomTests
    {
        private DateTime _now = new DateTime(2026, 1, 1, 12, 0, 0, DateTimeKind.Utc);
        private readonly List<Decision> _decisions = new List<Decision>();
        private readonly DeviceStore _devices = new DeviceStore(null);
        private readonly WaitingRoom _room;

        public WaitingRoomTests()
        {
            _room = new WaitingRoom(_devices, () => _now);
            _room.Decided += d => _decisions.Add(d);
        }

        private static IPAddress Ip(int last) => IPAddress.Parse("192.168.1." + last);

        private JoinResult Join(long id, int ip)
        {
            return _room.Join(id, Ip(ip), "Viewer", "Chrome on Android", _ => { });
        }

        [Fact]
        public void TellsTheClientItsNameBeforeAnnouncing()
        {
            var order = new List<string>();
            _room.Changed += () => order.Add("changed");
            _room.Join(1, Ip(1), "Ada", "x", _ => order.Add("name"));
            Assert.Equal(new[] { "name", "changed" }, order);
        }

        [Fact]
        public void ApproveOnceIssuesNoCredential()
        {
            Join(1, 1);
            Assert.True(_room.Approve(1, remember: false));
            var d = Assert.Single(_decisions);
            Assert.Equal(DecisionKind.Approved, d.Kind);
            Assert.Null(d.Credential);
            Assert.Empty(_devices.List());
            Assert.Empty(_room.Pending);
        }

        [Fact]
        public void ApproveAndRememberIssuesWorkingCredential()
        {
            Join(1, 1);
            _room.Approve(1, remember: true);
            var d = Assert.Single(_decisions);
            Assert.NotNull(d.Credential);
            Assert.Equal(32, d.Credential!.Length);
            Assert.NotNull(_devices.Match(d.Credential));
            Assert.Null(_devices.Match(new byte[32]));

            _devices.Remove(d.Device!.Id);
            Assert.Null(_devices.Match(d.Credential));
        }

        [Fact]
        public void DecisionsOnlyApplyOnce()
        {
            Join(1, 1);
            Assert.True(_room.Deny(1));
            Assert.False(_room.Approve(1, true));
            Assert.False(_room.Deny(1));
            Assert.Single(_decisions);
        }

        [Fact]
        public void LimitsPendingDevices()
        {
            for (var i = 0; i < WaitingRoom.MaxPending; i++)
            {
                Assert.Equal(JoinResult.Pending, Join(i, i));
            }

            Assert.Equal(JoinResult.RoomFull, Join(100, 100));
        }

        [Fact]
        public void OnePendingDevicePerAddress()
        {
            Assert.Equal(JoinResult.Pending, Join(1, 1));
            Assert.Equal(JoinResult.AddressBusy, Join(2, 1));
            _room.Leave(1);
            Assert.Equal(JoinResult.Pending, Join(2, 1));
        }

        [Fact]
        public void DenyStartsCooldownForTheAddress()
        {
            Join(1, 1);
            _room.Deny(1);
            Assert.Equal(JoinResult.CoolingDown, Join(2, 1));
            Assert.Equal(JoinResult.Pending, Join(3, 2));
            _now += WaitingRoom.DenyCooldown;
            Assert.Equal(JoinResult.Pending, Join(4, 1));
        }

        [Fact]
        public void RequestsExpire()
        {
            Join(1, 1);
            _now += WaitingRoom.PendingLifetime - TimeSpan.FromSeconds(1);
            _room.Expire();
            Assert.Single(_room.Pending);
            _now += TimeSpan.FromSeconds(1);
            _room.Expire();
            Assert.Empty(_room.Pending);
            Assert.Equal(DecisionKind.Expired, Assert.Single(_decisions).Kind);
        }

        [Fact]
        public void NamesAreMadeUniqueAmongWaitingDevices()
        {
            var names = new List<string>();
            _room.Join(1, Ip(1), "Ada", "x", names.Add);
            _room.Join(2, Ip(2), " ada ", "x", names.Add);
            _room.Join(3, Ip(3), "ADA", "x", names.Add);
            _room.Join(4, Ip(4), new string('b', 40), "x", names.Add);
            Assert.Equal(new[] { "Ada", "ada 2", "ADA 3", new string('b', WaitingRoom.MaxNameLength) }, names);

            // Once the first Ada is gone, the name is free again.
            _room.Leave(1);
            _room.Join(5, Ip(5), "Ada", "x", names.Add);
            Assert.Equal("Ada", names.Last());
        }

        [Fact]
        public void NamesAreCleanedUp()
        {
            Assert.Equal("Ada Lovelace", WaitingRoom.CleanName("  Ada\t\n Lovelace\u0000 ", 7));
            Assert.Equal("Viewer 7", WaitingRoom.CleanName(" \u0001 ", 7));
            Assert.Equal("Ada", WaitingRoom.CleanName("Ada\ud83d\ude00", 7)); // emoji dropped
            Assert.Equal(WaitingRoom.MaxNameLength, WaitingRoom.CleanName(new string('x', 100), 7).Length);
        }

        [Fact]
        public void FindByNameIgnoresCaseAndSpaces()
        {
            _room.Join(1, Ip(1), "Aztec Istanbul", "x", _ => { });
            Assert.Equal(1, _room.FindByName("  aztec   ISTANBUL ")!.ConnectionId);
            Assert.Null(_room.FindByName("Aztec"));
            Assert.Null(_room.FindByName(""));
        }

        [Fact]
        public void LabelsAreSanitized()
        {
            _room.Join(1, Ip(1), "Ada", "evil\u0000\nlabel" + new string('x', 200), _ => { });
            var label = Assert.Single(_room.Pending).Label;
            Assert.DoesNotContain('\n', label);
            Assert.DoesNotContain('\0', label);
            Assert.True(label.Length <= 64);
        }
    }
}
