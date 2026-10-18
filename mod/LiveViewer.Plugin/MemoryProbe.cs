using System;
using System.Diagnostics;
using System.Threading;
using IPALogger = IPA.Logging.Logger;

namespace LiveViewer.Plugin
{
    /// <summary>
    /// Diagnostics for the out-of-memory kills seen on the Frame: logs the managed heap and the process's memory every
    /// 15 s, so a log shows whether growth is managed (Mono) or native, and when it starts. Runs on a timer thread.
    /// Temporary; remove once the cause is found.
    /// </summary>
    internal sealed class MemoryProbe : IDisposable
    {
        private readonly IPALogger _logger;
        private readonly Timer _timer;

        public MemoryProbe(IPALogger logger)
        {
            _logger = logger;
            _timer = new Timer(_ => Sample(), null, TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(15));
        }

        private void Sample()
        {
            try
            {
                const double mb = 1024 * 1024;
                using var process = Process.GetCurrentProcess();
                _logger.Info($"Memory: managed {GC.GetTotalMemory(false) / mb:F0} MB, private {process.PrivateMemorySize64 / mb:F0} MB, "
                             + $"working set {process.WorkingSet64 / mb:F0} MB, GCs {GC.CollectionCount(0)}");
            }
            catch (Exception e)
            {
                _logger.Info("Memory: " + e.Message);
            }
        }

        public void Dispose() => _timer.Dispose();
    }
}
