using System.Threading.Tasks;
using EmbedIO.WebSockets;
using LiveViewer.Server.Live;

namespace LiveViewer.Server.Web
{
    /// <summary>The single WebSocket endpoint. All protocol logic lives in <see cref="ClientHub"/>.</summary>
    internal sealed class LiveSocketModule : WebSocketModule
    {
        private readonly ClientHub _hub;

        public LiveSocketModule(string path, ClientHub hub) : base(path, true)
        {
            _hub = hub;
            AddProtocol("bslive.v1");
        }

        protected override Task OnClientConnectedAsync(IWebSocketContext context)
        {
            _hub.OnConnected(context, context.Headers["User-Agent"] ?? string.Empty);
            return Task.CompletedTask;
        }

        protected override Task OnMessageReceivedAsync(IWebSocketContext context, byte[] buffer, IWebSocketReceiveResult result)
        {
            // Same values as System.Net.WebSockets.WebSocketMessageType: 0 is text, 1 is binary.
            _hub.OnMessage(context, buffer, result.MessageType != 1);
            return Task.CompletedTask;
        }

        protected override Task OnClientDisconnectedAsync(IWebSocketContext context)
        {
            _hub.OnDisconnected(context);
            return Task.CompletedTask;
        }
    }
}
