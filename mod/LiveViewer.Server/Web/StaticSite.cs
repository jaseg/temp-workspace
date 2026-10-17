using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading.Tasks;
using EmbedIO;

namespace LiveViewer.Server.Web
{
    /// <summary>
    /// The viewer's static files, loaded into memory once. Requests are answered from this fixed table only:
    /// request paths never touch the filesystem.
    /// </summary>
    public sealed class StaticSite
    {
        public const long MaxTotalBytes = 64L * 1024 * 1024;

        private static readonly Dictionary<string, string> MimeTypes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            [".html"] = "text/html; charset=utf-8",
            [".js"] = "text/javascript; charset=utf-8",
            [".mjs"] = "text/javascript; charset=utf-8",
            [".css"] = "text/css; charset=utf-8",
            [".json"] = "application/json",
            [".map"] = "application/json",
            [".svg"] = "image/svg+xml",
            [".png"] = "image/png",
            [".jpg"] = "image/jpeg",
            [".jpeg"] = "image/jpeg",
            [".webp"] = "image/webp",
            [".gif"] = "image/gif",
            [".ico"] = "image/x-icon",
            [".woff"] = "font/woff",
            [".woff2"] = "font/woff2",
            [".ttf"] = "font/ttf",
            [".ogg"] = "audio/ogg",
            [".mp3"] = "audio/mpeg",
            [".wav"] = "audio/wav",
            [".glb"] = "model/gltf-binary",
            [".gltf"] = "model/gltf+json",
            [".wasm"] = "application/wasm",
            [".txt"] = "text/plain; charset=utf-8",
        };

        private readonly Dictionary<string, Entry> _files = new Dictionary<string, Entry>(StringComparer.Ordinal);

        private StaticSite()
        {
        }

        public int Count => _files.Count;

        /// <summary>The test page embedded in this assembly.</summary>
        public static StaticSite FromEmbeddedTestPage()
        {
            var site = new StaticSite();
            var assembly = typeof(StaticSite).GetTypeInfo().Assembly;
            foreach (var name in assembly.GetManifestResourceNames().Where(n => n.StartsWith("www/", StringComparison.Ordinal)))
            {
                using var stream = assembly.GetManifestResourceStream(name)!;
                site.Add("/" + name.Substring(4).Replace('\\', '/'), ReadAll(stream));
            }

            return site;
        }

        /// <summary>Loads every file below a directory (for development builds of the viewer).</summary>
        public static StaticSite FromDirectory(string directory)
        {
            var site = new StaticSite();
            var root = Path.GetFullPath(directory);
            foreach (var path in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
            {
                var relative = path.Substring(root.Length).Replace('\\', '/');
                site.Add(relative.StartsWith("/", StringComparison.Ordinal) ? relative : "/" + relative, File.ReadAllBytes(path));
            }

            return site;
        }

        /// <summary>Loads a zip of the viewer bundle (how the plugin ships it).</summary>
        public static StaticSite FromZip(Stream zip)
        {
            var site = new StaticSite();
            using var archive = new ZipArchive(zip, ZipArchiveMode.Read);
            foreach (var entry in archive.Entries.Where(e => !e.FullName.EndsWith("/", StringComparison.Ordinal)))
            {
                using var stream = entry.Open();
                site.Add("/" + entry.FullName.Replace('\\', '/').TrimStart('/'), ReadAll(stream));
            }

            return site;
        }

        internal bool TryGet(string path, out Entry entry)
        {
            if (path.EndsWith("/", StringComparison.Ordinal))
            {
                path += "index.html";
            }

            return _files.TryGetValue(path, out entry!);
        }

        private void Add(string path, byte[] content)
        {
            if (path.Split('/').Any(segment => segment == ".." || segment == "."))
            {
                return;
            }

            var total = _files.Values.Sum(f => (long) f.Content.Length) + content.Length;
            if (total > MaxTotalBytes)
            {
                throw new InvalidOperationException("Static site is too large.");
            }

            MimeTypes.TryGetValue(Path.GetExtension(path), out var mime);
            using var sha = SHA256.Create();
            var etag = "\"" + Convert.ToBase64String(sha.ComputeHash(content), 0, 12) + "\"";
            _files[path] = new Entry(content, mime ?? "application/octet-stream", etag);
        }

        private static byte[] ReadAll(Stream stream)
        {
            using var ms = new MemoryStream();
            stream.CopyTo(ms);
            return ms.ToArray();
        }

        internal sealed class Entry
        {
            public Entry(byte[] content, string contentType, string etag)
            {
                Content = content;
                ContentType = contentType;
                ETag = etag;
            }

            public byte[] Content { get; }

            public string ContentType { get; }

            public string ETag { get; }
        }
    }

    internal sealed class StaticSiteModule : WebModuleBase
    {
        private readonly StaticSite _site;

        public StaticSiteModule(StaticSite site) : base("/")
        {
            _site = site;
        }

        public override bool IsFinalHandler => true;

        protected override async Task OnRequestAsync(IHttpContext context)
        {
            if (!_site.TryGet(context.RequestedPath, out var entry))
            {
                context.Response.SetEmptyResponse(404);
                return;
            }

            var response = context.Response;
            response.Headers["ETag"] = entry.ETag;
            response.Headers["Cache-Control"] = "no-cache";
            if (context.Request.Headers["If-None-Match"] == entry.ETag)
            {
                response.SetEmptyResponse(304);
                return;
            }

            response.ContentType = entry.ContentType;
            response.ContentLength64 = entry.Content.Length;
            if (context.Request.HttpVerb == HttpVerbs.Head)
            {
                return;
            }

            await response.OutputStream.WriteAsync(entry.Content, 0, entry.Content.Length).ConfigureAwait(false);
        }
    }
}
