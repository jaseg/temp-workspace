using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace LiveViewer.Server.Protocol
{
    /// <summary>Minimal JSON writer for the few server-generated documents (no JSON dependency on net48).</summary>
    public sealed class JsonObjectWriter
    {
        private readonly StringBuilder _sb = new StringBuilder("{");
        private bool _first = true;

        public JsonObjectWriter Field(string name, string value)
        {
            Name(name);
            Quote(_sb, value);
            return this;
        }

        public JsonObjectWriter Field(string name, double value)
        {
            Name(name);
            _sb.Append(double.IsNaN(value) || double.IsInfinity(value)
                ? "null"
                : value.ToString("R", CultureInfo.InvariantCulture));
            return this;
        }

        public JsonObjectWriter Field(string name, bool value)
        {
            Name(name);
            _sb.Append(value ? "true" : "false");
            return this;
        }

        public JsonObjectWriter Field(string name, IDictionary<string, string> value)
        {
            Name(name);
            _sb.Append('{');
            var first = true;
            foreach (var pair in value)
            {
                if (!first)
                {
                    _sb.Append(',');
                }

                first = false;
                Quote(_sb, pair.Key);
                _sb.Append(':');
                Quote(_sb, pair.Value);
            }

            _sb.Append('}');
            return this;
        }

        public override string ToString() => _sb.ToString() + "}";

        private void Name(string name)
        {
            if (!_first)
            {
                _sb.Append(',');
            }

            _first = false;
            Quote(_sb, name);
            _sb.Append(':');
        }

        private static void Quote(StringBuilder sb, string value)
        {
            sb.Append('"');
            foreach (var c in value ?? string.Empty)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        // Escape all control characters and the HTML-significant ones, so the JSON is inert anywhere.
                        if (c < 0x20 || c == '<' || c == '>' || c == '&' || c == '\u2028' || c == '\u2029')
                        {
                            sb.Append("\\u").Append(((int) c).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            sb.Append(c);
                        }

                        break;
                }
            }

            sb.Append('"');
        }
    }
}
