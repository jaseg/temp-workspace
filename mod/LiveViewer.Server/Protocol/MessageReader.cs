using System;
using System.Text;

namespace LiveViewer.Server.Protocol
{
    /// <summary>
    /// Bounds-checked little-endian reader for inbound (untrusted) messages.
    /// Every read throws <see cref="ProtocolException"/> instead of reading past the end.
    /// </summary>
    public sealed class MessageReader
    {
        private static readonly UTF8Encoding StrictUtf8 = new UTF8Encoding(false, true);

        private readonly byte[] _data;
        private int _position;

        public MessageReader(byte[] data)
        {
            _data = data ?? throw new ArgumentNullException(nameof(data));
        }

        public int Remaining => _data.Length - _position;

        public byte U8()
        {
            Require(1);
            return _data[_position++];
        }

        public ushort U16()
        {
            Require(2);
            var value = (ushort) (_data[_position] | (_data[_position + 1] << 8));
            _position += 2;
            return value;
        }

        public uint U32()
        {
            Require(4);
            var value = (uint) (_data[_position]
                                | (_data[_position + 1] << 8)
                                | (_data[_position + 2] << 16)
                                | (_data[_position + 3] << 24));
            _position += 4;
            return value;
        }

        public long I64()
        {
            ulong lo = U32();
            ulong hi = U32();
            return unchecked((long) (lo | (hi << 32)));
        }

        public double F64()
        {
            var bits = I64();
            return BitConverter.Int64BitsToDouble(bits);
        }

        public byte[] Bytes(int count)
        {
            if (count < 0)
            {
                throw new ProtocolException("Negative length.");
            }

            Require(count);
            var result = new byte[count];
            Buffer.BlockCopy(_data, _position, result, 0, count);
            _position += count;
            return result;
        }

        public string String(int maxBytes)
        {
            var length = unchecked((int) U32());
            if (length < 0 || length > maxBytes)
            {
                throw new ProtocolException("String too long.");
            }

            Require(length);
            string value;
            try
            {
                value = StrictUtf8.GetString(_data, _position, length);
            }
            catch (ArgumentException)
            {
                throw new ProtocolException("Invalid UTF-8.");
            }

            _position += length;
            return value;
        }

        public void End()
        {
            if (_position != _data.Length)
            {
                throw new ProtocolException("Trailing bytes.");
            }
        }

        private void Require(int count)
        {
            if (count > _data.Length - _position)
            {
                throw new ProtocolException("Message truncated.");
            }
        }
    }

    public sealed class ProtocolException : Exception
    {
        public ProtocolException(string message) : base(message)
        {
        }
    }
}
