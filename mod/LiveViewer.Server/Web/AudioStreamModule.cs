using System;
using System.IO;
using System.Net;
using System.Threading.Tasks;
using EmbedIO;
using LiveViewer.Server.Live;

namespace LiveViewer.Server.Web
{
    /// <summary>Streams the currently selected song. The random URL is disclosed only to approved viewers.</summary>
    internal sealed class AudioStreamModule : WebModuleBase
    {
        private static readonly DateTime ValidatorDate = new DateTime(2020, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        private readonly AudioStreamState _state;

        public AudioStreamModule(AudioStreamState state) : base("/audio") => _state = state;

        public override bool IsFinalHandler => true;

        protected override async Task OnRequestAsync(IHttpContext context)
        {
            // RequestedPath is relative to this module's /audio base route.
            var token = context.RequestedPath.TrimStart('/');
            if (token.Length != 32 || !_state.TryOpen(token, out var source, out var contentType))
            {
                context.Response.SetEmptyResponse(404);
                return;
            }

            using (source)
            using (GameFileAccess.Enter())
            {
                if (!source.CanSeek)
                {
                    context.Response.SetEmptyResponse(500);
                    return;
                }

                var length = source.Length;
                var etag = "\"" + token + "\"";
                var start = 0L;
                var end = length - 1;
                var partial = context.Request.IsRangeRequest(length, etag, ValidatorDate, out start, out end);
                var count = end - start + 1;
                var response = context.Response;
                response.ContentType = contentType;
                response.ContentLength64 = count;
                response.Headers[HttpHeaderNames.AcceptRanges] = "bytes";
                response.Headers[HttpHeaderNames.CacheControl] = "private, no-store";
                response.Headers[HttpHeaderNames.ETag] = etag;
                if (partial)
                {
                    response.StatusCode = (int) HttpStatusCode.PartialContent;
                    response.Headers[HttpHeaderNames.ContentRange] = $"bytes {start}-{end}/{length}";
                }

                if (context.Request.HttpVerb == HttpVerbs.Head) return;
                source.Position = start;
                var buffer = new byte[64 * 1024];
                while (count > 0)
                {
                    var read = await source.ReadAsync(buffer, 0, (int) Math.Min(buffer.Length, count), context.CancellationToken)
                        .ConfigureAwait(false);
                    if (read == 0) break;
                    await response.OutputStream.WriteAsync(buffer, 0, read, context.CancellationToken).ConfigureAwait(false);
                    count -= read;
                }
            }
        }
    }
}
