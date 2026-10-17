using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Security.Cryptography.X509Certificates;
using EmbedIO;
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

        /// <summary>Viewer files to serve; defaults to the embedded test page.</summary>
        public StaticSite? Site;

        /// <summary>Allow peers outside private address ranges. Off by default.</summary>
        public bool AllowAnyAddress;
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
        private readonly PeerPolicy _peers;
        private readonly HostPolicy _hosts;
        private WebServer? _server;

        public LiveServer(LiveServerOptions options, ILiveLog log)
        {
            _options = options;
            _log = log;
            Directory.CreateDirectory(options.DataDirectory);

            Devices = new DeviceStore(Path.Combine(options.DataDirectory, "devices.tsv"));
            WaitingRoom = new WaitingRoom(Devices);
            Feed = new LiveFeed();
            _peers = new PeerPolicy { AllowAnyAddress = options.AllowAnyAddress };
            _hosts = new HostPolicy(options.Port, options.HostNames);
            _hub = new ClientHub(Feed, WaitingRoom, Devices, options.ServerName, log);

            Certificate = CertificateStore.LoadOrCreate(options.DataDirectory, options.HostNames, LocalAddresses(), log.Info);
            CertificateFingerprint = CertificateStore.Fingerprint(Certificate);
        }

        public LiveFeed Feed { get; }

        public WaitingRoom WaitingRoom { get; }

        public DeviceStore Devices { get; }

        public X509Certificate2 Certificate { get; }

        public string CertificateFingerprint { get; }

        public int ConnectedViewers => _hub.ApprovedCount;

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

            _hub.Start();
            server.Start();
            _server = server;
            _log.Info($"Listening on port {_options.Port}. Certificate SHA-256 {CertificateFingerprint}.");
        }

        public void Dispose()
        {
            _hub.Dispose();
            _server?.Dispose();
            _server = null;
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

            foreach (var nic in interfaces)
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
    }
}
