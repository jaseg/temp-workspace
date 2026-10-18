namespace LiveViewer.Server.Protocol
{
    /// <summary>
    /// First byte of every WebSocket binary message. See PROTOCOL.md for the payload layouts.
    /// Server-to-client types are below 0x80, client-to-server types are 0x80 and above.
    /// </summary>
    public static class MessageType
    {
        public const ushort ProtocolVersion = 3;

        // Connection and waiting room.
        public const byte Welcome = 0x01;
        public const byte Waiting = 0x02;
        public const byte Approved = 0x03;
        public const byte Denied = 0x04;
        public const byte Revoked = 0x05;
        public const byte Pong = 0x06;
        public const byte Name = 0x07;

        // Session lifecycle.
        public const byte SessionStart = 0x10;
        public const byte SessionEnd = 0x11;
        public const byte Idle = 0x12;
        public const byte SongSelected = 0x13;

        // Live data.
        public const byte Pose = 0x20;
        public const byte NoteCut = 0x21;
        public const byte NoteFinal = 0x22;
        public const byte Wall = 0x23;
        public const byte Height = 0x24;
        public const byte Pause = 0x25;
        public const byte Resume = 0x26;
        public const byte NoteSpawn = 0x27;
        public const byte WallSpawn = 0x28;
        public const byte SliderSpawn = 0x29;

        // File transfer (map files, level library).
        public const byte MapChunk = 0x30;
        public const byte MapError = 0x31;

        // Level suggestions.
        public const byte Suggestions = 0x40;

        // Client to server.
        public const byte Hello = 0x81;
        public const byte Ping = 0x82;
        public const byte LevelListRequest = 0x84;
        public const byte LevelFileRequest = 0x85;
        public const byte LevelStatsRequest = 0x86;
        public const byte SuggestionAdd = 0x87;
        public const byte SuggestionRemove = 0x88;
        public const byte SuggestionMove = 0x89;
        public const byte Rename = 0x8A;
    }

    public enum MapErrorCode : byte
    {
        NotAvailable = 1,
        ReadFailed = 3,
        TooManyRequests = 4,
    }

    public enum SessionEndReason : byte
    {
        Cleared = 1,
        Failed = 2,
        Quit = 3,
        Restarted = 4,
    }
}
