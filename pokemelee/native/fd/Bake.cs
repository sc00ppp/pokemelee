// Top-down software rasterizer: bakes flat Colosseum meshes (the Mt. Battle arena floor and its decals) into one
// disc texture, so FD's deck top can be a single CMPR disc on the exact collision radius.
//   bakefloor <rdat> <out.png> <cx> <cz> <radius> <size> <desc:joint[:dobj]>...
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Numerics;
using HSDRaw;
using HSDRaw.Common;
using HSDRaw.GX;

static partial class Program
{
    static float Wrap(float t, GXWrapMode m)
    {
        switch (m)
        {
            case GXWrapMode.REPEAT: return t - MathF.Floor(t);
            case GXWrapMode.MIRROR: { float f = t - 2 * MathF.Floor(t / 2); return f > 1 ? 2 - f : f; }
            default: return Math.Clamp(t, 0, 1);
        }
    }

    // bilinear sample of a BGRA image, returns RGBA 0..1
    static Vector4 Sample(byte[] px, int w, int h, float u, float v, GXWrapMode ws, GXWrapMode wt)
    {
        float x = Wrap(u, ws) * w - 0.5f, y = Wrap(v, wt) * h - 0.5f;
        int x0 = (int)MathF.Floor(x), y0 = (int)MathF.Floor(y); float fx = x - x0, fy = y - y0;
        Vector4 P(int xx, int yy)
        {
            xx = ws == GXWrapMode.CLAMP ? Math.Clamp(xx, 0, w - 1) : ((xx % w) + w) % w;
            yy = wt == GXWrapMode.CLAMP ? Math.Clamp(yy, 0, h - 1) : ((yy % h) + h) % h;
            int i = (yy * w + xx) * 4;
            return new Vector4(px[i + 2], px[i + 1], px[i], px[i + 3]) / 255f;
        }
        return Vector4.Lerp(Vector4.Lerp(P(x0, y0), P(x0 + 1, y0), fx), Vector4.Lerp(P(x0, y0 + 1), P(x0 + 1, y0 + 1), fx), fy);
    }

    // items: (desc, joint, dobj or -1). Returns BGRA size x size; pixel (i, j) covers world x = cx + (i+0.5)/size*2r - r, z likewise.
    static byte[] BakeTop(HSDRawFile f, List<(int d, int j, int o)> items, float cx, float cz, float r, int size, int ss = 2)
    {
        int N = size * ss;
        var acc = new Vector4[N * N];
        var descs = Scene(f).JOBJDescs.Array;
        foreach (var (di, ji, oi) in items)
        {
            var root = descs[di].RootJoint;
            var worlds = new Dictionary<HSD_JOBJ, Matrix4x4>();
            Worlds(root, Matrix4x4.Identity, worlds);
            var jo = root.TreeList[ji];
            var dl = jo.Dobj.List;
            for (int o = 0; o < dl.Count; o++)
            {
                if (oi >= 0 && o != oi) continue;
                var d = dl[o];
                var tex = d.Mobj?.Textures;
                byte[] tpx = null; int tw = 0, th = 0;
                if (tex?.ImageData != null) { tpx = tex.GetDecodedImageData(); tw = tex.ImageData.Width; th = tex.ImageData.Height; }
                bool blend = d.Mobj != null && (d.Mobj.RenderFlags.HasFlag(RENDER_MODE.XLU) || jo.Flags.HasFlag(JOBJ_FLAG.TEXEDGE) || jo.Flags.HasFlag(JOBJ_FLAG.XLU));
                foreach (var p in d.Pobj.List)
                {
                    var tris = Triangles(p.ToDisplayList());
                    for (int t = 0; t + 2 < tris.Count; t += 3)
                    {
                        var P = new Vector2[3]; var V = new GX_Vertex[3];
                        for (int k = 0; k < 3; k++)
                        {
                            V[k] = tris[t + k];
                            var q = Vector3.Transform(new Vector3(V[k].POS.X, V[k].POS.Y, V[k].POS.Z), worlds[jo]);
                            P[k] = new Vector2((q.X - cx + r) / (2 * r) * N, (q.Z - cz + r) / (2 * r) * N);
                        }
                        float area = (P[1].X - P[0].X) * (P[2].Y - P[0].Y) - (P[2].X - P[0].X) * (P[1].Y - P[0].Y);
                        if (MathF.Abs(area) < 1e-6f) continue;
                        int minx = Math.Max(0, (int)MathF.Floor(P.Min(q => q.X))), maxx = Math.Min(N - 1, (int)MathF.Ceiling(P.Max(q => q.X)));
                        int miny = Math.Max(0, (int)MathF.Floor(P.Min(q => q.Y))), maxy = Math.Min(N - 1, (int)MathF.Ceiling(P.Max(q => q.Y)));
                        for (int y = miny; y <= maxy; y++)
                            for (int x = minx; x <= maxx; x++)
                            {
                                var c = new Vector2(x + 0.5f, y + 0.5f);
                                float w0 = ((P[1].X - c.X) * (P[2].Y - c.Y) - (P[2].X - c.X) * (P[1].Y - c.Y)) / area;
                                float w1 = ((P[2].X - c.X) * (P[0].Y - c.Y) - (P[0].X - c.X) * (P[2].Y - c.Y)) / area;
                                float w2 = 1 - w0 - w1;
                                if (w0 < -1e-4f || w1 < -1e-4f || w2 < -1e-4f) continue;
                                float u = w0 * V[0].TEX0.X + w1 * V[1].TEX0.X + w2 * V[2].TEX0.X;
                                float v = w0 * V[0].TEX0.Y + w1 * V[1].TEX0.Y + w2 * V[2].TEX0.Y;
                                var col = new Vector4(w0 * V[0].CLR0.R + w1 * V[1].CLR0.R + w2 * V[2].CLR0.R, w0 * V[0].CLR0.G + w1 * V[1].CLR0.G + w2 * V[2].CLR0.G,
                                                      w0 * V[0].CLR0.B + w1 * V[1].CLR0.B + w2 * V[2].CLR0.B, w0 * V[0].CLR0.A + w1 * V[1].CLR0.A + w2 * V[2].CLR0.A);
                                if (!d.Mobj.RenderFlags.HasFlag(RENDER_MODE.VERTEX)) col = Vector4.One;
                                var s = tpx != null ? Sample(tpx, tw, th, u, v, tex.WrapS, tex.WrapT) : Vector4.One;
                                var o4 = col * s;
                                ref var a = ref acc[y * N + x];
                                float al = blend ? o4.W : 1f;
                                if (jo.Flags.HasFlag(JOBJ_FLAG.TEXEDGE) && !d.Mobj.RenderFlags.HasFlag(RENDER_MODE.XLU)) al = o4.W >= 0.5f ? 1f : 0f;
                                a = new Vector4(a.X * (1 - al) + o4.X * al, a.Y * (1 - al) + o4.Y * al, a.Z * (1 - al) + o4.Z * al, Math.Max(a.W, al));
                            }
                    }
                }
            }
        }
        var outp = new byte[size * size * 4];
        for (int y = 0; y < size; y++)
            for (int x = 0; x < size; x++)
            {
                var s = Vector4.Zero;
                for (int yy = 0; yy < ss; yy++) for (int xx = 0; xx < ss; xx++) s += acc[(y * ss + yy) * N + x * ss + xx];
                s /= ss * ss;
                int i = (y * size + x) * 4;
                outp[i + 2] = (byte)Math.Clamp(s.X * 255, 0, 255); outp[i + 1] = (byte)Math.Clamp(s.Y * 255, 0, 255);
                outp[i] = (byte)Math.Clamp(s.Z * 255, 0, 255); outp[i + 3] = (byte)Math.Clamp(s.W * 255, 0, 255);
            }
        return outp;
    }

    static List<(int, int, int)> ParseItems(IEnumerable<string> a) => a.Select(s => { var p = s.Split(':').Select(int.Parse).ToArray(); return (p[0], p[1], p.Length > 2 ? p[2] : -1); }).ToList();


}
