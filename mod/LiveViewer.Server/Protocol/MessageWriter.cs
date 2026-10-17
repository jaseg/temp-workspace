using System;
using System.Runtime.InteropServices;
using System.Text;

namespace LiveViewer.Server.Protocol
{
    /// <summary>
    /// Little-endian binary writer for outbound messages, using BSOR's encodings
    /// (strings are an int32 byte length followed by UTF-8).
    /// </summary>
    public sealed class MessageWriter
    {
        private byte[] _buffer;
        private int _length;

        public MessageWriter(int capacity = 128)
        {
            _buffer = new byte[capacity];
        }

        public int Length => _length;

        public MessageWriter Reset()
        {
            _length = 0;
            return this;
        }

        public byte[] ToArray()
        {
            var result = new byte[_length];
            Buffer.BlockCopy(_buffer, 0, result, 0, _length);
            return result;
        }

        public MessageWriter U8(byte value)
        {
            Ensure(1);
            _buffer[_length++] = value;
            return this;
        }

        public MessageWriter Bool(bool value) => U8(value ? (byte) 1 : (byte) 0);

        public MessageWriter U16(ushort value)
        {
            Ensure(2);
            _buffer[_length++] = (byte) value;
            _buffer[_length++] = (byte) (value >> 8);
            return this;
        }

        public MessageWriter I32(int value) => U32(unchecked((uint) value));

        public MessageWriter U32(uint value)
        {
            Ensure(4);
            _buffer[_length++] = (byte) value;
            _buffer[_length++] = (byte) (value >> 8);
            _buffer[_length++] = (byte) (value >> 16);
            _buffer[_length++] = (byte) (value >> 24);
            return this;
        }

        public MessageWriter I64(long value)
        {
            var v = unchecked((ulong) value);
            U32((uint) v);
            return U32((uint) (v >> 32));
        }

        public MessageWriter F32(float value) => U32(new FloatBits { Float = value }.Bits);

        public MessageWriter F64(double value) => I64(BitConverter.DoubleToInt64Bits(value));

        public MessageWriter Bytes(byte[] value, int offset, int count)
        {
            Ensure(count);
            Buffer.BlockCopy(value, offset, _buffer, _length, count);
            _length += count;
            return this;
        }

        public MessageWriter Bytes(byte[] value) => Bytes(value, 0, value.Length);

        public MessageWriter String(string value)
        {
            var bytes = Encoding.UTF8.GetBytes(value ?? string.Empty);
            I32(bytes.Length);
            return Bytes(bytes);
        }

        public MessageWriter Vec3(in Vec3 v) => F32(v.X).F32(v.Y).F32(v.Z);

        public MessageWriter Quat(in Quat q) => F32(q.X).F32(q.Y).F32(q.Z).F32(q.W);

        public MessageWriter Pose(in Pose p) => Vec3(p.Position).Quat(p.Rotation);

        private void Ensure(int extra)
        {
            if (_length + extra <= _buffer.Length)
            {
                return;
            }

            var size = _buffer.Length * 2;
            while (size < _length + extra)
            {
                size *= 2;
            }

            Array.Resize(ref _buffer, size);
        }
    }

    [StructLayout(LayoutKind.Explicit)]
    internal struct FloatBits
    {
        [FieldOffset(0)] public float Float;
        [FieldOffset(0)] public uint Bits;
    }
}
