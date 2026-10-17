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
            return _room.Join(id, Ip(ip), "Chrome on Android", _ => { });
        }

        [Fact]
        public void TellsTheClientItsCodeBeforeAnnouncing()
        {
            var order = new List<string>();
            _room.Changed += () => order.Add("changed");
            _room.Join(1, Ip(1), "x", _ => order.Add("code"));
            Assert.Equal(new[] { "code", "changed" }, order);
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
        public void CodesAreUniqueAndReadable()
        {
            var codes = new HashSet<string>();
            for (var i = 0; i < WaitingRoom.MaxPending; i++)
            {
                _room.Join(i, Ip(i), "x", code => codes.Add(code));
            }

            Assert.Equal(WaitingRoom.MaxPending, codes.Count);
            foreach (var code in codes)
            {
                Assert.Matches("^[A-Za-z]+ [A-Za-z]+ [A-Za-z]+$", code);
                Assert.Equal(code, _room.FindByCode(code)!.MatchCode);
            }
        }

        [Fact]
        public void CodesAlternateTheTwoWordLists()
        {
            string? code = null;
            _room.Join(1, Ip(1), "x", c => code = c);
            var words = code!.Split(' ');
            Assert.Contains(words[0], WordList.Even);
            Assert.Contains(words[1], WordList.Odd);
            Assert.Contains(words[2], WordList.Even);
        }

        [Fact]
        public void FindByCodeIgnoresCaseAndSeparators()
        {
            string? code = null;
            _room.Join(1, Ip(1), "x", c => code = c);
            var sloppy = "  " + code!.ToUpperInvariant().Replace(" ", " - ") + " ";
            Assert.Equal(1, _room.FindByCode(sloppy)!.ConnectionId);
            Assert.Null(_room.FindByCode(code.Split(' ')[0]));
            Assert.Null(_room.FindByCode(""));
        }

        [Fact]
        public void WordListsAreComplete()
        {
            Assert.Equal(256, WordList.Even.Distinct(StringComparer.OrdinalIgnoreCase).Count());
            Assert.Equal(256, WordList.Odd.Distinct(StringComparer.OrdinalIgnoreCase).Count());
            Assert.Empty(WordList.Even.Intersect(WordList.Odd, StringComparer.OrdinalIgnoreCase));
        }

        [Fact]
        public void LabelsAreSanitized()
        {
            _room.Join(1, Ip(1), "evil\u0000\nlabel" + new string('x', 200), _ => { });
            var label = Assert.Single(_room.Pending).Label;
            Assert.DoesNotContain('\n', label);
            Assert.DoesNotContain('\0', label);
            Assert.True(label.Length <= 64);
        }
    }
}
