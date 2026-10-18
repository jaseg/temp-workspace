using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace LiveViewer.Server.Live
{
    /// <summary>The files of the map being played, as far as viewers may read them.</summary>
    public interface IMapFileSource
    {
        /// <summary>Opens a file by its exact name. Returns false for anything that isn't an allowed map file.</summary>
        bool TryOpen(string fileName, out Stream stream);
    }

    /// <summary>
    /// A map folder with an explicit allow-list of file names (taken from the map's info.dat by the caller).
    /// Names are matched exactly; anything containing path syntax is refused even if listed, and the resolved
    /// path must stay inside the folder.
    /// </summary>
    public sealed class MapDirectory : IMapFileSource
    {
        public const long MaxFileBytes = 64L * 1024 * 1024;

        private readonly string _root;
        private readonly HashSet<string> _allowed;

        public MapDirectory(string directory, IEnumerable<string> allowedFileNames)
        {
            _root = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    + Path.DirectorySeparatorChar;
            _allowed = new HashSet<string>(allowedFileNames.Where(IsPlainFileName), StringComparer.Ordinal);
        }

        public IReadOnlyCollection<string> AllowedFiles => _allowed;

        public bool TryOpen(string fileName, out Stream stream)
        {
            stream = Stream.Null;
            if (!IsPlainFileName(fileName) || !_allowed.Contains(fileName))
            {
                return false;
            }

            var path = Path.GetFullPath(Path.Combine(_root, fileName));
            if (!path.StartsWith(_root, StringComparison.Ordinal))
            {
                return false;
            }

            try
            {
                var info = new FileInfo(path);
                if (!info.Exists || info.Length > MaxFileBytes || (info.Attributes & FileAttributes.ReparsePoint) != 0)
                {
                    return false;
                }

                using (GameFileAccess.Enter())
                {
                    stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 16384, useAsync: true);
                }

                return true;
            }
            catch (IOException)
            {
                return false;
            }
            catch (UnauthorizedAccessException)
            {
                return false;
            }
        }

        internal static bool IsPlainFileName(string name)
        {
            if (string.IsNullOrEmpty(name) || name.Length > 200 || name == "." || name == "..")
            {
                return false;
            }

            foreach (var c in name)
            {
                if (c < 0x20 || c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|')
                {
                    return false;
                }
            }

            return name.Trim() == name && !name.EndsWith(".", StringComparison.Ordinal);
        }
    }
}
