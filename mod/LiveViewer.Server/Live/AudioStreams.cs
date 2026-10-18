using System;
using System.IO;
using System.Security.Cryptography;

namespace LiveViewer.Server.Live
{
    /// <summary>A song file which can be opened independently for each HTTP request.</summary>
    public interface IAudioFileSource
    {
        bool TryOpen(out Stream stream, out string contentType);
    }

    public sealed class MapAudioFile : IAudioFileSource
    {
        private readonly IMapFileSource _map;
        private readonly string _fileName;

        public MapAudioFile(IMapFileSource map, string fileName)
        {
            _map = map;
            _fileName = fileName;
        }

        public bool TryOpen(out Stream stream, out string contentType)
        {
            contentType = ContentType(_fileName);
            return _map.TryOpen(_fileName, out stream);
        }

        private static string ContentType(string name)
        {
            var extension = Path.GetExtension(name).ToLowerInvariant();
            if (extension == ".mp3") return "audio/mpeg";
            if (extension == ".wav") return "audio/wav";
            if (extension == ".m4a" || extension == ".mp4") return "audio/mp4";
            return "audio/ogg";
        }
    }

    public sealed class SongSelection
    {
        public string Hash = "";
        public string SongName = "";
        public string SongSubName = "";
        public string SongAuthor = "";
        public float BeatsPerMinute;
        public IAudioFileSource Audio = null!;
    }

    internal sealed class AudioStreamState
    {
        private readonly object _lock = new object();
        private string _token = "";
        private IAudioFileSource? _source;

        public string Select(IAudioFileSource source)
        {
            var bytes = new byte[24];
            using (var random = RandomNumberGenerator.Create()) random.GetBytes(bytes);
            var token = Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
            lock (_lock)
            {
                _source = source;
                _token = token;
            }
            return "/audio/" + token;
        }

        public bool TryOpen(string token, out Stream stream, out string contentType)
        {
            IAudioFileSource? source;
            lock (_lock) source = token == _token ? _source : null;
            if (source != null) return source.TryOpen(out stream, out contentType);
            stream = Stream.Null;
            contentType = "application/octet-stream";
            return false;
        }
    }
}
