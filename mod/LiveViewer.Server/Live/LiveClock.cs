using System.Diagnostics;

namespace LiveViewer.Server.Live
{
    /// <summary>Monotonic server clock in microseconds, shared by capture timestamps and clock-sync pongs.</summary>
    public static class LiveClock
    {
        private static readonly double MicrosPerTick = 1_000_000.0 / Stopwatch.Frequency;

        public static long NowUs() => (long) (Stopwatch.GetTimestamp() * MicrosPerTick);
    }
}
