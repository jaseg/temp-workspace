using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Security.Cryptography.X509Certificates;
using EmbedIO;
using LiveViewer.Server.Levels;
using LiveViewer.Server.Live;
using LiveViewer.Server.Security;
using LiveViewer.Server.Web;

namespace LiveViewer.Server
{
    public sealed class LiveServerOptions
    {
        public int Port = 4280;

        /// <summary>Where the certificate and remembered devices are stored.</summary>
        public string DataDirectory = "";

        /// <summary>Host names browsers may use (the mDNS name). IP literals of our own interfaces are always accepted.</summary>
        public List<string> HostNames = new List<string> { "beatsaber.local", "localhost" };

        public string ServerName = "Beat Saber Live";

        /// <summary>How long a WebSocket may remain open without identifying itself.</summary>
        public TimeSpan HelloTimeout = TimeSpan.FromSeconds(10);

        /// <summary>Viewer files to serve; defaults to the embedded test page.</summary>
        public StaticSite? Site;

        /// <summary>Allow peers outside private address ranges. Off by default.</summary>
        public bool AllowAnyAddress;

        /// <summary>Folders whose subfolders are custom levels (e.g. Beat Saber_Data/CustomLevels). Empty: no level list.</summary>
        public List<string> LevelFolders = new List<string>();

        /// <summary>
        /// Where level stats come from. Null: no BeatLeader stats. Set it to <see cref="BeatLeaderHttpApi"/> to fetch
        /// them from BeatLeader, which tells BeatLeader the hashes of the levels viewers look at.
        /// </summary>
        public IBeatLeaderApi? BeatLeader;
    }

    /// <summary>
    /// The web server hosted by the mod: HTTPS for the viewer files, one WSS endpoint for everything else.
    /// Thread-safe. The game feeds it through <see cref="Feed"/> and drives approvals through
    /// <see cref="WaitingRoom"/> and <see cref="Devices"/>.
    /// </summary>
    public sealed class LiveServer : IDisposable
    {
        public const string WebSocketPath = "/ws";

        private readonly LiveServerOptions _options;
        private readonly ILiveLog _log;
        private readonly ClientHub _hub;
        private readonly BeatLeaderStats? _stats;
        private readonly PeerPolicy _peers;
        private readonly HostPolicy _hosts;
        private readonly AudioStreamState _audio;
        private WebServer? _server;
        private System.Threading.CancellationTokenSource? _stop;

        public LiveServer(LiveServerOptions options, ILiveLog log)
        {
            _options = options;
            _log = log;
            Directory.CreateDirectory(options.DataDirectory);

            Devices = new DeviceStore(Path.Combine(options.DataDirectory, "devices.tsv"));
            WaitingRoom = new WaitingRoom(Devices);
            Feed = new LiveFeed();
            _audio = new AudioStreamState();
            _peers = new PeerPolicy { AllowAnyAddress = options.AllowAnyAddress };
            _hosts = new HostPolicy(options.Port, options.HostNames);
            Levels = new LevelLibrary(options.LevelFolders, log);
            Suggestions = new Suggestions(Path.Combine(options.DataDirectory, "suggestions.tsv"));
            _stats = options.BeatLeader != null
                ? new BeatLeaderStats(options.BeatLeader, log, cachePath: Path.Combine(options.DataDirectory, "beatleader-cache.tsv"))
                : null;
            _hub = new ClientHub(Feed, WaitingRoom, Devices, options.ServerName, log, options.HelloTimeout, _audio, Levels, _stats, Suggestions);

            Certificate = CertificateStore.LoadOrCreate(options.DataDirectory, options.HostNames, LocalAddresses(), log.Info);
            CertificateFingerprint = CertificateStore.Fingerprint(Certificate);
        }

        public LiveFeed Feed { get; }

        public WaitingRoom WaitingRoom { get; }

        public DeviceStore Devices { get; }

        public LevelLibrary Levels { get; }

        /// <summary>Levels viewers suggest; the plugin shows them as a level pack in the game.</summary>
        public Suggestions Suggestions { get; }

        public X509Certificate2 Certificate { get; }

        public string CertificateFingerprint { get; }

        public int ConnectedViewers => _hub.ApprovedCount;

        /// <summary>
        /// Set by the game while a song runs. The game turns its garbage collector off then, so anything allocated
        /// stays until the song ends: the level browser's work (scans, covers, song previews, BeatLeader lookups) waits
        /// until then. The live stream and the song audio for viewers joining late are still served.
        /// </summary>
        public bool InGameplay
        {
            get => _hub.InGameplay;
            set => _hub.InGameplay = value;
        }

        /// <summary>URLs to show the player: the configured names first, then each LAN address.</summary>
        public IReadOnlyList<string> Urls =>
            _options.HostNames.Where(n => n != "localhost").Select(n => $"https://{n}:{_options.Port}/")
                .Concat(LocalAddresses().Where(a => !IPAddress.IsLoopback(a)).Select(a =>
                    a.AddressFamily == AddressFamily.InterNetworkV6 ? $"https://[{a}]:{_options.Port}/" : $"https://{a}:{_options.Port}/"))
                .ToList();

        public void AddHostName(string name) => _hosts.AddName(name);

        public void Start()
        {
            if (_server != null)
            {
                return;
            }

            var server = new WebServer(o => o
                .WithMode(HttpListenerMode.EmbedIO)
                .WithUrlPrefix($"https://*:{_options.Port}/")
                .WithCertificate(Certificate)
                .WithoutAutoLoadCertificate()
                .WithoutAutoRegisterCertificate());

            var listener = (EmbedIO.Net.HttpListener) server.Listener;
            listener.AcceptFilter = endpoint => _peers.IsAllowed(endpoint.Address);
            listener.NoDelay = true;
            listener.TlsHandshakeTimeout = TimeSpan.FromSeconds(10);
            listener.FirstRequestTimeout = TimeSpan.FromSeconds(10);
            listener.KeepAliveTimeout = TimeSpan.FromSeconds(30);
            listener.MaxRequestHeaderBytes = 8192;
            listener.MaxWebSocketMessageBytes = 1024;

            server
                .WithModule(new GuardModule(_hosts, WebSocketPath))
                .WithModule(new LiveSocketModule(WebSocketPath, _hub))
                .WithModule(new AudioStreamModule(_audio))
                .WithModule(new StaticSiteModule(_options.Site ?? StaticSite.FromEmbeddedTestPage()));
            server.HandleHttpException((context, exception) =>
            {
                context.Response.SetEmptyResponse(exception.StatusCode);
                return System.Threading.Tasks.Task.CompletedTask;
            });
            server.HandleUnhandledException((context, exception) =>
            {
                _log.Error("Unhandled exception in request handler", exception);
                context.Response.SetEmptyResponse(500);
                return System.Threading.Tasks.Task.CompletedTask;
            });

            // Dual-stack where IPv6 works, IPv4 only otherwise (Wine and containers don't always have IPv6).
            EmbedIO.Net.EndPointManager.UseIpv6 = CanBindDualStack();

            _hub.Start();
            _stop = new System.Threading.CancellationTokenSource();
            var run = server.RunAsync(_stop.Token);

            // EmbedIO binds the socket only after reporting "Listening", and a bind failure just ends RunAsync.
            // Wait for that window to pass so failures surface here instead of being swallowed.
            var deadline = DateTime.UtcNow.AddSeconds(5);
            while (server.State < WebServerState.Listening && !run.IsCompleted && DateTime.UtcNow < deadline)
            {
                System.Threading.Thread.Sleep(5);
            }

            System.Threading.Tasks.Task.WhenAny(run, System.Threading.Tasks.Task.Delay(250)).Wait();
            if (run.IsCompleted || server.State != WebServerState.Listening)
            {
                _stop.Cancel();
                server.Dispose();
                throw new InvalidOperationException($"Couldn't listen on port {_options.Port}.", run.Exception?.GetBaseException());
            }

            _ = run.ContinueWith(t =>
            {
                if (!(_stop?.IsCancellationRequested ?? true))
                {
                    _log.Error("Web server stopped unexpectedly", t.Exception?.GetBaseException());
                }
            }, System.Threading.Tasks.TaskScheduler.Default);
            _server = server;
            _log.Info($"Listening on port {_options.Port} ({(EmbedIO.Net.EndPointManager.UseIpv6 ? "IPv4 and IPv6" : "IPv4")}). Certificate SHA-256 {CertificateFingerprint}.");
        }

        public void Dispose()
        {
            _stop?.Cancel();
            _hub.Dispose();
            _stats?.Dispose();
            _server?.Dispose();
            _server = null;
        }

        private static bool CanBindDualStack()
        {
            if (!Socket.OSSupportsIPv6)
            {
                return false;
            }

            try
            {
                using var probe = new Socket(AddressFamily.InterNetworkV6, SocketType.Stream, ProtocolType.Tcp);
                probe.SetSocketOption(SocketOptionLevel.IPv6, SocketOptionName.IPv6Only, false);
                probe.Bind(new IPEndPoint(IPAddress.IPv6Any, 0));
                return true;
            }
            catch (SocketException)
            {
                return false;
            }
        }

        internal static IEnumerable<IPAddress> LocalAddresses()
        {
            NetworkInterface[] interfaces;
            try
            {
                interfaces = NetworkInterface.GetAllNetworkInterfaces();
            }
            catch (NetworkInformationException)
            {
                yield break;
            }

            // Interfaces with a gateway (the network people are on) first; on the Frame, its own access point
            // for the streaming link comes without one.
            foreach (var nic in interfaces.OrderBy(n => HasGateway(n) ? 0 : 1))
            {
                if (nic.OperationalStatus != OperationalStatus.Up)
                {
                    continue;
                }

                foreach (var unicast in nic.GetIPProperties().UnicastAddresses)
                {
                    var address = unicast.Address;
                    if (address.AddressFamily == AddressFamily.InterNetwork
                        || (address.AddressFamily == AddressFamily.InterNetworkV6 && !address.IsIPv6LinkLocal))
                    {
                        yield return address;
                    }
                }
            }
        }

        private static bool HasGateway(NetworkInterface nic)
        {
            try
            {
                return nic.GetIPProperties().GatewayAddresses.Any(g => !g.Address.Equals(IPAddress.Any) && !g.Address.Equals(IPAddress.IPv6Any));
            }
            catch (NetworkInformationException)
            {
                return false;
            }
        }
    }
}
