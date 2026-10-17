using System;

namespace LiveViewer.Server
{
    public interface ILiveLog
    {
        void Info(string message);

        void Warn(string message);

        void Error(string message, Exception? exception = null);
    }

    public sealed class ConsoleLiveLog : ILiveLog
    {
        public void Info(string message) => Console.WriteLine("[info] " + message);

        public void Warn(string message) => Console.WriteLine("[warn] " + message);

        public void Error(string message, Exception? exception = null) =>
            Console.WriteLine("[error] " + message + (exception != null ? ": " + exception : string.Empty));
    }
}
