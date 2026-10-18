using System;

namespace LiveViewer.Server
{
    /// <summary>
    /// Lets the host game permit our reads of level files. SongCore 3.16 blocks direct reads of files it has loaded
    /// (difficulty and audio data) unless a flag is set for the current async flow; the plugin sets
    /// <see cref="Allow"/> to a function that sets that flag and returns a handle that restores it. The server enters
    /// this around every level file open and read. Without a host (dev host, tests) it does nothing.
    /// </summary>
    public static class GameFileAccess
    {
        public static Func<IDisposable>? Allow;

        internal static IDisposable Enter() => Allow?.Invoke() ?? Nothing.Instance;

        private sealed class Nothing : IDisposable
        {
            public static readonly Nothing Instance = new Nothing();

            public void Dispose()
            {
            }
        }
    }
}
