using System;
using System.Reflection;
using System.Threading;
using IPALogger = IPA.Logging.Logger;

namespace LiveViewer.Plugin
{
    /// <summary>
    /// SongCore 3.16 refuses direct reads of level files it has loaded (difficulty and audio data) with an assert,
    /// unless its <c>AllowIO</c> flag is set for the current async flow; SongCore sets it around its own hashing.
    /// The server reads those files to send them to viewers, so it sets the flag around its reads too
    /// (<see cref="Server.GameFileAccess"/>). The class is internal, and named IOBlacklistHooks in 3.16 but
    /// IOBlacklistHook in SongCore's newer source, so it's found by name.
    /// </summary>
    internal static class SongCoreFileAccess
    {
        private static readonly string[] TypeNames =
        {
            "SongCore.Hooks.BeatmapLevelCache.IOBlacklistHooks",
            "SongCore.Hooks.BeatmapLevelCache.IOBlacklistHook",
        };

        public static void Install(IPALogger logger)
        {
            var assembly = typeof(SongCore.Loader).Assembly;
            foreach (var name in TypeNames)
            {
                var property = assembly.GetType(name)?.GetProperty("AllowIO", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
                if (property?.GetValue(null) is AsyncLocal<bool> flag)
                {
                    Server.GameFileAccess.Allow = () => new Scope(flag);
                    logger.Info($"Reading level files with SongCore's permission ({name}.AllowIO).");
                    return;
                }
            }

            logger.Info("This SongCore doesn't guard level files.");
        }

        private sealed class Scope : IDisposable
        {
            private readonly AsyncLocal<bool> _flag;
            private readonly bool _before;

            public Scope(AsyncLocal<bool> flag)
            {
                _flag = flag;
                _before = flag.Value;
                flag.Value = true;
            }

            public void Dispose() => _flag.Value = _before;
        }
    }
}
