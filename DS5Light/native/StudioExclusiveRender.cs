using System;
using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential, Pack=2)] struct Wave {
    public ushort Tag, Channels; public uint Rate, BytesPerSecond;
    public ushort Align, Bits, Extra, ValidBits; public uint Mask; public Guid SubFormat;
}
[ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface AudioClient {
    [PreserveSig] int Initialize(int mode,uint flags,long duration,long period,ref Wave format,IntPtr session);
    [PreserveSig] int GetBufferSize(out uint size);
    [PreserveSig] int GetStreamLatency(out long value);
    [PreserveSig] int GetCurrentPadding(out uint value);
    [PreserveSig] int IsFormatSupported(int mode,IntPtr format,out IntPtr closest);
    [PreserveSig] int GetMixFormat(out IntPtr format);
    [PreserveSig] int GetDevicePeriod(out long normal,out long minimum);
    [PreserveSig] int Start(); [PreserveSig] int Stop(); [PreserveSig] int Reset();
    [PreserveSig] int SetEventHandle(IntPtr value);
    [PreserveSig] int GetService(ref Guid iid,[MarshalAs(UnmanagedType.IUnknown)] out object service);
}
[ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface Enumerator {
    void EnumAudioEndpoints();
    void GetDefaultAudioEndpoint();
    void GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id, out Endpoint device);
}
[ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface Endpoint {
    void Activate(ref Guid iid, uint context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object audio);
}
[ComImport, Guid("F294ACFC-3146-4483-A7BF-ADDCA7C260E2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface Renderer {
    void GetBuffer(uint count, out IntPtr buffer);
    void ReleaseBuffer(uint count, uint flags);
}
public static class ExclusiveProbe {
    static void Check(int result) { Marshal.ThrowExceptionForHR(result); }
    public static void Run(string id, bool live) {
        var enumerator = (Enumerator)Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")));
        Endpoint device = null;
        object raw = null, service = null;
        AudioClient audio = null;
        bool started = false;
        try {
            enumerator.GetDevice(id, out device);
            var iid = typeof(AudioClient).GUID;
            device.Activate(ref iid, 23, IntPtr.Zero, out raw);
            audio = (AudioClient)raw;
            var format = new Wave { Tag = 0xfffe, Channels = 4, Rate = 48000, BytesPerSecond = 384000,
                Align = 8, Bits = 16, Extra = 22, ValidBits = 16, Mask = 0x33,
                SubFormat = new Guid("00000001-0000-0010-8000-00aa00389b71") };
            var ptr = Marshal.AllocHGlobal(Marshal.SizeOf<Wave>());
            try {
                Marshal.StructureToPtr(format, ptr, false);
                IntPtr closest;
                int result = audio.IsFormatSupported(1, ptr, out closest); if (result != 0) throw new InvalidOperationException($"Exclusive IsFormatSupported HRESULT=0x{result:X8}");
            } finally { Marshal.FreeHGlobal(ptr); }
            Check(audio.GetDevicePeriod(out long normal, out long minimum));
            int init = audio.Initialize(1, 0, Math.Max(normal * 4, minimum), 0, ref format, IntPtr.Zero); if (init < 0) throw new InvalidOperationException($"Exclusive Initialize HRESULT=0x{init:X8}");
            iid = typeof(Renderer).GUID;
            Check(audio.GetService(ref iid, out service));
            var render = (Renderer)service;
            Check(audio.GetBufferSize(out uint capacity));
            render.GetBuffer(capacity, out _);
            render.ReleaseBuffer(capacity, 2);
            Check(audio.Start());
            started = true;
            Console.WriteLine("EXCLUSIVE_STARTED");
            Console.Out.Flush();
            var input = System.Threading.Tasks.Task.Run(() => Console.ReadLine());
            var clock = System.Diagnostics.Stopwatch.StartNew();
            var idle = System.Diagnostics.Stopwatch.StartNew();
            short[] pcm = null;
            int position = 0;
            while (live ? idle.Elapsed.TotalSeconds < 2 : clock.Elapsed.TotalSeconds < 7) {
                if (pcm == null && input.IsCompleted) {
                    string line = input.Result;
                    if (line == null || line == "STOP") break;
                    if (line == "DRAIN") {
                        Check(audio.GetStreamLatency(out long latency));
                        long tailTicks = (long)capacity * 10000000 / 48000 + latency;
                        if (tailTicks > 2000000) throw new InvalidOperationException("Unexpected render latency");
                        var tail = System.Diagnostics.Stopwatch.StartNew();
                        while (tail.Elapsed.Ticks < tailTicks) {
                            Check(audio.GetCurrentPadding(out uint queued));
                            if (queued < capacity) {
                                render.GetBuffer(capacity - queued, out _);
                                render.ReleaseBuffer(capacity - queued, 2);
                            }
                            System.Threading.Thread.Sleep(5);
                        }
                        Console.WriteLine("DRAINED");
                        Console.Out.Flush();
                        break;
                    }
                    idle.Restart();
                    byte[] bytes = Convert.FromBase64String(line);
                    if (bytes.Length == 0 || bytes.Length > 38400 || bytes.Length % 8 != 0)
                        throw new InvalidOperationException("Invalid PCM block");
                    pcm = new short[bytes.Length / 2];
                    Buffer.BlockCopy(bytes, 0, pcm, 0, bytes.Length);
                    position = 0;
                }
                Check(audio.GetCurrentPadding(out uint padding));
                uint available = capacity - padding;
                if (available != 0) {
                    if (pcm == null) {
                        render.GetBuffer(available, out _);
                        render.ReleaseBuffer(available, 2);
                    } else {
                        uint frames = Math.Min(available, (uint)((pcm.Length - position) / 4));
                        render.GetBuffer(frames, out IntPtr writePtr);
                        Marshal.Copy(pcm, position, writePtr, checked((int)frames * 4));
                        render.ReleaseBuffer(frames, 0);
                        position += checked((int)frames * 4);
                        if (position == pcm.Length) {
                            pcm = null;
                            Console.WriteLine("WROTE");
                            Console.Out.Flush();
                            input = System.Threading.Tasks.Task.Run(() => Console.ReadLine());
                        }
                    }
                }
                System.Threading.Thread.Sleep(live ? 2 : 5);
            }
        } finally {
            if (started) audio.Stop();
            if (service != null) Marshal.ReleaseComObject(service);
            if (raw != null) Marshal.ReleaseComObject(raw);
            if (device != null) Marshal.ReleaseComObject(device);
            Marshal.ReleaseComObject(enumerator);
        }
    }
}




