using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using LiveViewer.Server;
using LiveViewer.Server.Levels;
using LiveViewer.Server.Live;
using LiveViewer.Server.Protocol;
using LiveViewer.Server.Web;

namespace LiveViewer.Host
{
    public static class Program
    {
        private const string Usage = @"LiveViewer.Host: runs the live viewer server outside the game, fed by a BeatLeader replay.

Usage: LiveViewer.Host --replay <file.bsor | https://... | scoreId> [options]
       LiveViewer.Host --dump-levels <out.json> [--levels <dir>] [--no-beatleader]

Options:
  --map <dir|zip>      Map folder or zip (default: download by hash from BeatLeader/BeatSaver)
  --port <n>           Port (default 4280)
  --data <dir>         Certificate, devices and map cache (default ./livedata)
  --www <dir>          Serve this directory instead of the embedded test page
  --hostname <name>    Extra accepted host name (repeatable; default beatsaber.local, localhost)
  --speed <x>          Playback speed (default 1)
  --start <seconds>    Start each run at this song time (for testing song ends)
  --loop               Replay forever
  --auto-approve       Approve every waiting device (testing only)
  --any-address        Accept non-private peers (testing only)
  --levels <dir>       Folder of custom levels for the level list (repeatable; default <data>/maps)
  --no-beatleader      Don't fetch BeatLeader stats for the level list
  --dump-levels <file> Write the level list and BeatLeader stats as JSON, then exit (for the demo build)

Console commands while running:
  l                    List waiting and remembered devices
  a <name>             Allow once
  r <name>             Allow and remember
  d <name>             Deny
  revoke <id>          Forget a remembered device
  q                    Quit";

        public static async Task<int> Main(string[] args)
        {
            var options = ParseArgs(args);
            if (options == null)
            {
                Console.WriteLine(Usage);
                return 2;
            }

            Swan.Logging.Logger.NoLogging();
            var log = new ConsoleLiveLog();
            var dataDirectory = Path.GetFullPath(options.GetValueOrDefault("data") ?? "livedata");
            var levelFolders = Multi(args, "--levels").ToList();
            if (levelFolders.Count == 0)
            {
                levelFolders.Add(Path.Combine(dataDirectory, "maps"));
            }

            using var beatLeader = options.ContainsKey("no-beatleader") ? null : new BeatLeaderHttpApi();
            if (options.TryGetValue("dump-levels", out var dumpPath))
            {
                await LevelDump.WriteAsync(dumpPath, levelFolders, beatLeader, log);
                return 0;
            }

            Console.WriteLine("Loading replay...");
            var replay = BsorReplay.Decode(await LoadReplayAsync(options["replay"]));
            var info = replay.Info;
            Console.WriteLine($"Replay: {info.PlayerName} - {info.SongName} ({info.Mode} {info.Difficulty}), {replay.Frames.Count} frames, {replay.Notes.Count} notes.");

            var map = await MapFolder.ResolveAsync(options.GetValueOrDefault("map"), info.Hash, dataDirectory, info.Mode, info.Difficulty);
            var session = new SessionInfo
            {
                Hash = info.Hash,
                SongName = info.SongName,
                SongSubName = map.SongSubName,
                SongAuthor = map.SongAuthor,
                Mapper = info.Mapper,
                Difficulty = info.Difficulty,
                Mode = info.Mode,
                Environment = info.Environment,
                Modifiers = info.Modifiers,
                PlayerName = info.PlayerName,
                LeftHanded = info.LeftHanded,
                PlayerHeight = info.Height,
                JumpDistance = info.JumpDistance,
                NoteJumpSpeed = map.NoteJumpSpeed,
                StartTime = info.StartTime,
                SongSpeed = info.Speed > 0 ? info.Speed : 1,
                GameVersion = info.GameVersion,
                Files = map.Files,
            };
            var mapSource = map.Source;

            var serverOptions = new LiveServerOptions
            {
                Port = int.Parse(options.GetValueOrDefault("port") ?? "4280"),
                DataDirectory = dataDirectory,
                AllowAnyAddress = options.ContainsKey("any-address"),
                Site = options.TryGetValue("www", out var www) ? StaticSite.FromDirectory(www) : null,
                LevelFolders = levelFolders,
                BeatLeader = beatLeader,
            };
            foreach (var name in Multi(args, "--hostname"))
            {
                serverOptions.HostNames.Add(name);
            }

            using var server = new LiveServer(serverOptions, log);
            if (options.ContainsKey("auto-approve"))
            {
                server.WaitingRoom.Changed += () =>
                {
                    foreach (var p in server.WaitingRoom.Pending)
                    {
                        server.WaitingRoom.Approve(p.ConnectionId, false);
                    }
                };
            }
            else
            {
                server.WaitingRoom.Changed += () => PrintPending(server);
            }

            server.Start();
            foreach (var url in server.Urls)
            {
                Console.WriteLine("  " + url);
            }

            using var cts = new CancellationTokenSource();
            Console.CancelKeyPress += (_, e) =>
            {
                e.Cancel = true;
                cts.Cancel();
            };

            var speed = double.Parse(options.GetValueOrDefault("speed") ?? "1", System.Globalization.CultureInfo.InvariantCulture);
            var loop = options.ContainsKey("loop");
            var startAt = float.Parse(options.GetValueOrDefault("start") ?? "0", System.Globalization.CultureInfo.InvariantCulture);
            var player = new Thread(() =>
            {
                do
                {
                    // Give viewers a moment to connect before the song starts.
                    if (cts.Token.WaitHandle.WaitOne(TimeSpan.FromSeconds(3)))
                    {
                        return;
                    }

                    Console.WriteLine("Song starting.");
                    new FakeLive(server.Feed, replay, session, mapSource, speed, startAt).Run(cts.Token);
                    Console.WriteLine("Song ended.");
                }
                while (loop && !cts.IsCancellationRequested);
            }) { IsBackground = true, Name = "Fake live" };
            player.Start();

            // Keep serving after the song ends so the page stays reachable; quit with q or Ctrl+C.
            _ = Task.Run(() => CommandLoop(server, cts));
            try
            {
                await Task.Delay(Timeout.Infinite, cts.Token);
            }
            catch (TaskCanceledException)
            {
            }

            cts.Cancel();
            return 0;
        }

        private static void CommandLoop(LiveServer server, CancellationTokenSource cts)
        {
            while (!cts.IsCancellationRequested)
            {
                var line = Console.ReadLine();
                if (line == null)
                {
                    // stdin closed (e.g. running under a test harness): keep serving until cancelled.
                    cts.Token.WaitHandle.WaitOne();
                    return;
                }

                var parts = line.Trim().Split(' ', 2, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length == 0)
                {
                    continue;
                }

                var argument = parts.Length > 1 ? parts[1].Trim() : "";
                var pending = server.WaitingRoom.FindByName(argument);
                switch (parts[0])
                {
                    case "q":
                        cts.Cancel();
                        return;
                    case "l":
                        PrintPending(server);
                        foreach (var d in server.Devices.List())
                        {
                            Console.WriteLine($"  remembered {d.Id}  {d.Label}  last seen {d.LastSeenUtc:u}");
                        }

                        break;
                    case "a":
                    case "r":
                        if (pending == null || !server.WaitingRoom.Approve(pending.ConnectionId, parts[0] == "r"))
                        {
                            Console.WriteLine("No waiting device with that name.");
                        }

                        break;
                    case "d":
                        if (pending == null || !server.WaitingRoom.Deny(pending.ConnectionId))
                        {
                            Console.WriteLine("No waiting device with that name.");
                        }

                        break;
                    case "revoke":
                        Console.WriteLine(server.Devices.Remove(argument) ? "Revoked." : "No such device.");
                        break;
                    default:
                        Console.WriteLine("Commands: l, a <name>, r <name>, d <name>, revoke <id>, q");
                        break;
                }
            }
        }

        private static void PrintPending(LiveServer server)
        {
            var pending = server.WaitingRoom.Pending;
            if (pending.Count == 0)
            {
                Console.WriteLine("No devices waiting.");
                return;
            }

            foreach (var p in pending)
            {
                Console.WriteLine($"  waiting \"{p.Name}\"  {p.Label}  from {p.Address}  (a/r/d {p.Name})");
            }
        }

        private static async Task<byte[]> LoadReplayAsync(string source)
        {
            if (File.Exists(source))
            {
                return await File.ReadAllBytesAsync(source);
            }

            using var http = new HttpClient();
            http.DefaultRequestHeaders.UserAgent.ParseAdd("BeatSaberLiveViewer-DevHost/0.1");
            if (source.All(char.IsDigit))
            {
                using var doc = JsonDocument.Parse(await http.GetStringAsync($"https://api.beatleader.com/score/{source}"));
                source = doc.RootElement.GetProperty("replay").GetString()!;
            }

            return await http.GetByteArrayAsync(source);
        }

        private static Dictionary<string, string>? ParseArgs(string[] args)
        {
            var flags = new HashSet<string> { "loop", "auto-approve", "any-address", "no-beatleader" };
            var result = new Dictionary<string, string>();
            for (var i = 0; i < args.Length; i++)
            {
                if (!args[i].StartsWith("--", StringComparison.Ordinal))
                {
                    return null;
                }

                var key = args[i].Substring(2);
                if (flags.Contains(key))
                {
                    result[key] = "";
                }
                else if (i + 1 < args.Length)
                {
                    result[key] = args[++i];
                }
                else
                {
                    return null;
                }
            }

            return result.ContainsKey("replay") || result.ContainsKey("dump-levels") ? result : null;
        }

        private static IEnumerable<string> Multi(string[] args, string name)
        {
            for (var i = 0; i + 1 < args.Length; i++)
            {
                if (args[i] == name)
                {
                    yield return args[i + 1];
                }
            }
        }
    }
}
