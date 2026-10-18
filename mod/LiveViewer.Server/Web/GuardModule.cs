using System;
using System.Threading.Tasks;
using EmbedIO;
using LiveViewer.Server.Security;

namespace LiveViewer.Server.Web
{
    /// <summary>
    /// First module for every request: checks Host (DNS rebinding), methods, and the WebSocket Origin, and adds
    /// the security headers. Requests it rejects never reach the other modules.
    /// </summary>
    internal sealed class GuardModule : WebModuleBase
    {
        private readonly HostPolicy _hosts;
        private readonly string _webSocketPath;

        public GuardModule(HostPolicy hosts, string webSocketPath) : base("/")
        {
            _hosts = hosts;
            _webSocketPath = webSocketPath;
        }

        public override bool IsFinalHandler => false;

        protected override Task OnRequestAsync(IHttpContext context)
        {
            var host = context.Request.Headers["Host"];
            if (!_hosts.IsAllowedHost(host, context.LocalEndPoint.Address))
            {
                Reject(context, 421);
                return Task.CompletedTask;
            }

            var method = context.Request.HttpVerb;
            if (method != HttpVerbs.Get && method != HttpVerbs.Head)
            {
                Reject(context, 405);
                return Task.CompletedTask;
            }

            if (string.Equals(context.RequestedPath, _webSocketPath, StringComparison.Ordinal)
                && !HostPolicy.IsSameOrigin(context.Request.Headers["Origin"], host!))
            {
                Reject(context, 403);
                return Task.CompletedTask;
            }

            var headers = context.Response.Headers;
            headers["Content-Security-Policy"] =
                "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; " +
                "img-src 'self' data: blob:; media-src 'self' blob:; worker-src 'self' blob:; " +
                $"connect-src 'self' blob: wss://{host}; frame-ancestors 'none'; base-uri 'none'; form-action 'none'";
            headers["X-Content-Type-Options"] = "nosniff";
            headers["Referrer-Policy"] = "no-referrer";
            headers["Cross-Origin-Opener-Policy"] = "same-origin";
            headers["Cross-Origin-Resource-Policy"] = "same-origin";
            headers["Strict-Transport-Security"] = "max-age=31536000";
            return Task.CompletedTask;
        }

        private static void Reject(IHttpContext context, int status)
        {
            context.Response.Headers["Connection"] = "close";
            context.Response.SetEmptyResponse(status);
            context.SetHandled();
        }
    }
}
