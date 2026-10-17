using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using LiveViewer.Server;
using LiveViewer.Server.Levels;

namespace LiveViewer.Host
{
    /// <summary>
    /// Writes what the server would send for the level list and each level's stats, as one JSON file:
    /// <c>{"list": {...}, "stats": {"&lt;hash&gt;": {...}}, "folders": {"&lt;hash&gt;": "&lt;folder&gt;"}}</c>.
    /// The viewer's demo build serves it from its in-page source.
    /// </summary>
    internal static class LevelDump
    {
        public static async Task WriteAsync(string path, IReadOnlyList<string> folders, IBeatLeaderApi? beatLeader, ILiveLog log)
        {
            var snapshot = await new LevelLibrary(folders, log).GetAsync();
            var stats = beatLeader != null ? new BeatLeaderStats(beatLeader, log) : null;
            var sb = new StringBuilder("{\"list\":").Append(Encoding.UTF8.GetString(snapshot.Json)).Append(",\"stats\":{");
            var first = true;
            foreach (var level in snapshot.ByHash.Values)
            {
                if (stats == null)
                {
                    break;
                }

                try
                {
                    var json = Encoding.UTF8.GetString(await stats.GetAsync(level.Hash));
                    sb.Append(first ? "" : ",").Append('"').Append(level.Hash).Append("\":").Append(json);
                    first = false;
                }
                catch
                {
                    // Left out; the page shows the stats as unavailable.
                }
            }

            sb.Append("},\"folders\":{");
            sb.Append(string.Join(",", snapshot.ByHash.Values.Select(l =>
                "\"" + l.Hash + "\":" + Newtonsoft.Json.JsonConvert.ToString(Path.GetFileName(l.Directory)))));
            sb.Append("}}");
            File.WriteAllText(path, sb.ToString());
            log.Info($"Wrote {snapshot.ByHash.Count} levels to {path}.");
        }
    }
}
