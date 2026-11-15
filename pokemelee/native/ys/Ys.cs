// Yoshi's Story rebuilt as the outside of Mt. Battle:
//   group 3: a garden-topped rock pillar on YS's exact collision (slopes, notched walls = Randall's slots), metal platforms
//   group 1: the cliff face the Mt. Battle canyon opens into (covers the cut canyon walls), with a grass lip at the plateau edge
//   group 2: Randall's card replaced by a Colosseum model riding the same PATH joint (j1)
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Text.Json;
using HSDRaw;
using HSDRaw.Common;
using HSDRaw.Common.Animation;
using HSDRaw.GX;
using HSDRaw.Melee.Gr;
using HSDRaw.Tools;

static partial class Program
{
    // YS collision walls (file units), |x| of the wall at height y, top to bottom
    static readonly (float x, float y)[] ysRight = { (80f, -5f), (80f, -9.5f), (78.5f, -11f), (76.75f, -15f), (75.25f, -17.5f), (75.25f, -38.5f), (76.75f, -40f), (76.75f, -42.5f), (75.25f, -44f), (75.25f, -66f), (76.75f, -67.5f), (76.75f, -195f), (76.75f, -340f) };
    static readonly (float x, float y)[] ysLeft = { (80f, -5f), (80f, -9.5f), (78.5f, -11f), (76.75f, -15f), (75.25f, -17.5f), (75.25f, -38.5f), (76.75f, -40f), (76.75f, -42.5f), (75.25f, -44f), (75.25f, -64.75f), (78f, -67.5f), (78f, -195f), (78f, -340f) };

    static float WallX((float x, float y)[] p, float y)
    {
        if (y >= p[0].y) return p[0].x;
        for (int i = 0; i + 1 < p.Length; i++)
            if (y <= p[i].y && y >= p[i + 1].y)
            {
                float t = (p[i].y - y) / Math.Max(1e-5f, p[i].y - p[i + 1].y);
                return p[i].x + (p[i + 1].x - p[i].x) * t;
            }
        return p[^1].x;
    }

    static float YsTop(float x) { x = Math.Abs(x); return x <= 56f ? 0f : -5f * Math.Min(1f, (x - 56f) / 24f); }

    static void BuildYs(JsonElement ys, SBM_Map_Head head, SBM_Map_GOBJ[] groups, HSD_JOBJ groot,
        Dictionary<string, HSDRawFile> donorFiles, Dictionary<string, Dictionary<HSDStruct, HSDStruct>> memos)
    {
        var path = ys.GetProperty("file").GetString();
        if (!donorFiles.TryGetValue(path, out var df)) { df = new HSDRawFile(path); donorFiles[path] = df; memos[path] = new Dictionary<HSDStruct, HSDStruct>(); }
        var descs = Scene(df).JOBJDescs.Array;
        HSD_TOBJ SrcT(JsonElement e) => descs[e[0].GetInt32()].RootJoint.TreeList[e[1].GetInt32()].Dobj.List[e[2].GetInt32()].Mobj.Textures.List[e[3].GetInt32()];
        HSD_MOBJ SrcM(JsonElement e) => descs[e[0].GetInt32()].RootJoint.TreeList[e[1].GetInt32()].Dobj.List[e[2].GetInt32()].Mobj;
        var pxCache = new Dictionary<HSDStruct, (byte[], int, int)>();
        byte[] Px(JsonElement e, out int w, out int h)
        {
            var t = SrcT(e);
            if (!pxCache.TryGetValue(t.ImageData._s, out var c)) { c = (t.GetDecodedImageData(), t.ImageData.Width, t.ImageData.Height); pxCache[t.ImageData._s] = c; }
            w = c.Item2; h = c.Item3; return c.Item1;
        }
        byte[] Crop(JsonElement e, int dw, int dh)
        {
            var px = Px(e, out int w, out int h);
            int x0 = e.GetArrayLength() > 4 ? e[4].GetInt32() : 0, y0 = e.GetArrayLength() > 4 ? e[5].GetInt32() : 0;
            int x1 = e.GetArrayLength() > 4 ? e[6].GetInt32() : w, y1 = e.GetArrayLength() > 4 ? e[7].GetInt32() : h;
            return CropResize(px, w, x0, y0, x1 - x0, y1 - y0, dw, dh);
        }
        byte[] FlipV(byte[] s, int w, int h) { var o = new byte[s.Length]; for (int y = 0; y < h; y++) Array.Copy(s, (h - 1 - y) * w * 4, o, y * w * 4, w * 4); return o; }
        bool brightenCustom = ys.TryGetProperty("brighten_custom", out var bcv) && bcv.GetBoolean();
        var tmplM = Copy(SrcM(ys.GetProperty("material")), memos[path]);
        HSD_MOBJ Mat(byte[] px, int w, int h, GXWrapMode ws, GXWrapMode wt)
        {
            var t = NewTobj(tmplM.Textures, px, w, h, ws, wt);
            t.Flags = TOBJ_FLAGS.LIGHTMAP_DIFFUSE | TOBJ_FLAGS.COLORMAP_MODULATE;
            t.Blending = 1; t.TEV = null;
            t.GXTexGenSrc = GXTexGenSrc.GX_TG_TEX0; t.TexMapID = GXTexMapID.GX_TEXMAP0;
            var m = MobjWith(tmplM, t);
            m.RenderFlags = RENDER_MODE.VERTEX | RENDER_MODE.TEX0;
            if (!brightenCustom) noBrighten.Add(m._s);
            return m;
        }
        const GXWrapMode REP = GXWrapMode.REPEAT, CLA = GXWrapMode.CLAMP, MIR = GXWrapMode.MIRROR;
        var T = ys.GetProperty("tex");
        var mGrass = Mat(Seamless(Crop(T.GetProperty("grass"), 256, 256), 256, 256, true, true), 256, 256, REP, REP);
        var mSand = Mat(Seamless(Crop(T.GetProperty("sand"), 128, 128), 128, 128, true, true), 128, 128, REP, REP);
        var mRock = Mat(Seamless(Crop(T.GetProperty("rock"), 256, 256), 256, 256, true, true), 256, 256, REP, REP);
        var lipPx = Crop(T.GetProperty("lip"), 256, 128);
        if (T.TryGetProperty("lip_flip", out var lf) && lf.GetBoolean()) lipPx = FlipV(lipPx, 256, 128);
        var mLip = Mat(lipPx, 256, 128, MIR, CLA);
        var mKerb = Mat(Crop(T.GetProperty("kerb"), 128, 32), 128, 32, REP, CLA);
        var mMetal = Mat(Crop(T.GetProperty("metal"), 128, 128), 128, 128, MIR, MIR);
        var mSlot = Mat(Crop(T.GetProperty("slot"), 64, 128), 64, 128, REP, REP);

        float shadeTop = ys.TryGetProperty("shade_top", out var stv) ? stv.GetSingle() : 0.85f;
        float shadeRock = ys.TryGetProperty("shade_rock", out var srv) ? srv.GetSingle() : 0.62f;
        int seed = ys.TryGetProperty("seed", out var sdv) ? sdv.GetInt32() : 5;
        var rng = new Random(seed);
        float p1 = (float)rng.NextDouble() * 6.28f, p2 = (float)rng.NextDouble() * 6.28f, p3 = (float)rng.NextDouble() * 6.28f, p4 = (float)rng.NextDouble() * 6.28f;
        float Nz(float a, float b) => 0.5f * MathF.Sin(a * 0.11f + p1) * MathF.Cos(b * 0.09f + p2) + 0.3f * MathF.Sin(a * 0.31f + b * 0.07f + p3) + 0.2f * MathF.Sin(a * 0.83f + p4) * MathF.Sin(b * 0.61f + p1);
        GX_Vertex V(Vector3 p, Vector3 n, float shade, float u, float v) => new GX_Vertex
        {
            POS = new GXVector3(p.X, p.Y, p.Z), NRM = new GXVector3(n.X, n.Y, n.Z),
            CLR0 = new GXColor4(Math.Clamp(shade, 0, 1), Math.Clamp(shade, 0, 1), Math.Clamp(shade, 0, 1), 1), TEX0 = new GXVector2(u, v)
        };

        // ================= stage pillar (group 3) =================
        int sg = ys.TryGetProperty("stage_group", out var sgv) ? sgv.GetInt32() : 3;
        const float ZF = 30f, ZB = -32f, CH = 4f;     // front / back of the top, corner chamfer
        float yBottom = ys.TryGetProperty("pillar_bottom", out var pbv) ? pbv.GetSingle() : -900f;
        float lipBand = 14f;
        // rows: the top edge (relative) then absolute heights including every wall breakpoint
        var rowsY = new List<float> { -7f, -9.5f, -11f, -14f, -15f, -17.5f, -22f, -27f, -33f, -38.5f, -40f, -42.5f, -44f, -49f, -54f, -59f, -64.75f, -66f, -67.5f };
        for (float y = -80f; y > -195f; y -= 20f) rowsY.Add(y);
        rowsY.Add(-195f);
        for (float y = -235f; y > -400f; y -= 45f) rowsY.Add(y);
        for (float y = -480f; y > yBottom; y -= 120f) rowsY.Add(y);
        rowsY.Add(yBottom);
        rowsY = rowsY.Distinct().OrderByDescending(y => y).ToList();
        const int NC = 20;   // columns across the front: 8 units at the top (x = -80 + 8j), so +-56 are exact

        float ColX(int j, float y, bool topRow)
        {
            float u = j / (float)NC;
            if (topRow) return -80f + 160f * u;
            float wl = WallX(ysLeft, y), wr = WallX(ysRight, y);
            return -wl + (wl + wr) * u;
        }
        float WallTypeShade(float y0, float y1, (float x, float y)[] prof)
        {
            float a = WallX(prof, y0), b = WallX(prof, y1);
            return (Math.Abs(a - 75.25f) < 0.01f && Math.Abs(b - 75.25f) < 0.01f) ? 1 : Math.Abs(a - b) > 0.01f ? 2 : 0;   // 1 slot, 2 frame, 0 rock
        }
        bool IsSlotBand(float y0, float y1, bool left) => WallTypeShade(y0, y1, left ? ysLeft : ysRight) == 1;

        // ---- front face (z = ZF, chamfered corners), grass lip band then rock ----
        var lipT = new List<GX_Vertex>(); var rockT = new List<GX_Vertex>(); var slotT = new List<GX_Vertex>();
        int R = rowsY.Count + 1;   // row 0 = top edge
        var fp = new Vector3[R, NC + 1];
        var fs = new float[R, NC + 1];
        for (int r = 0; r < R; r++)
            for (int j = 0; j <= NC; j++)
            {
                bool top = r == 0;
                float yRow = top ? 0 : rowsY[r - 1];
                float x = ColX(j, yRow, top);
                float y = top ? YsTop(x) : yRow;
                float d = YsTop(x) - y;                                            // depth below the top edge
                float bulge = 1.3f * MathF.Sin(MathF.PI * Math.Min(d / 7f, 1f)) * (d < 7 ? 1 : 0)   // grass shoulder
                            + (d > 7 ? 1.6f * Nz(x, y) * Math.Clamp((d - 7) / 8f, 0, 1) : 0);           // rock relief
                float z = ZF + bulge;
                if (j == 0 || j == NC) z = ZF - CH;                                  // chamfer: the edge column bends back
                fp[r, j] = new Vector3(x, y, z);
                fs[r, j] = (d < lipBand ? shadeRock + 0.12f : shadeRock * (1f - 0.45f * Math.Clamp((-y - 20f) / 150f, 0, 1))) + 0.05f * Nz(x * 1.7f, y * 1.3f);
            }
        for (int r = 0; r + 1 < R; r++)
            for (int j = 0; j < NC; j++)
            {
                var a = fp[r, j]; var b = fp[r, j + 1]; var c = fp[r + 1, j + 1]; var e = fp[r + 1, j];
                float yMidTop = (a.Y + b.Y) / 2, yMidBot = (c.Y + e.Y) / 2;
                bool lip = YsTop((a.X + b.X) / 2) - yMidBot <= lipBand + 0.01f;
                bool edgeCol = j == 0 || j == NC - 1;
                bool slot = edgeCol && IsSlotBand(yMidTop, yMidBot, j == 0);
                var list = slot ? slotT : lip ? lipT : rockT;
                GX_Vertex Q(Vector3 p, float s)
                {
                    float u = lip ? p.X / 64f : slot ? p.Z / 16f : p.X / 48f;
                    float v = lip ? (YsTop(p.X) - p.Y) / lipBand * 0.98f + 0.01f : slot ? -p.Y / 21f : -p.Y / 48f;
                    return V(p, Vector3.UnitZ, slot ? 0.55f : s, u, v);
                }
                Quad(list, Q(a, fs[r, j]), Q(b, fs[r, j + 1]), Q(c, fs[r + 1, j + 1]), Q(e, fs[r + 1, j]));
            }

        // ---- back face (z = ZB), plain rock, reversed winding ----
        var backT = new List<GX_Vertex>();
        for (int r = 0; r + 1 < R; r++)
            foreach (var (j, j2) in new[] { (0, 1), (1, NC / 2), (NC / 2, NC - 1), (NC - 1, NC) })
            {
                Vector3 B(int rr, int jj) { var p = fp[rr, jj]; return new Vector3(p.X, p.Y, (jj == 0 || jj == NC) ? ZB + CH : ZB); }
                GX_Vertex Q(Vector3 p) => V(p, -Vector3.UnitZ, shadeRock * 0.7f, p.X / 48f, -p.Y / 48f);
                Quad(backT, Q(B(r, j2)), Q(B(r, j)), Q(B(r + 1, j)), Q(B(r + 1, j2)));
            }

        // ---- side walls on the collision profile (x = +-W(y)), z from the front chamfer to the back chamfer ----
        var sideT = new List<GX_Vertex>(); var frameT = new List<GX_Vertex>();
        var wallRows = new List<float> { -5f };
        wallRows.AddRange(rowsY.Where(y => y < -5f));
        foreach (bool left in new[] { true, false })
        {
            var prof = left ? ysLeft : ysRight; float sx = left ? -1 : 1;
            for (int r = 0; r + 1 < wallRows.Count; r++)
            {
                float y0 = wallRows[r], y1 = wallRows[r + 1];
                float w0 = WallX(prof, y0), w1 = WallX(prof, y1);
                float kind = WallTypeShade(y0, y1, prof);
                var list = kind == 1 ? slotT : kind == 2 ? frameT : sideT;
                const int NZ = 4;
                for (int k = 0; k < NZ; k++)
                {
                    float za = (ZF - CH) + (ZB + CH - (ZF - CH)) * k / NZ, zb = (ZF - CH) + (ZB + CH - (ZF - CH)) * (k + 1) / NZ;
                    float sh0 = kind == 1 ? 0.5f : kind == 2 ? 0.7f : shadeRock * 0.85f * (1f - 0.45f * Math.Clamp((-y0 - 20f) / 150f, 0, 1));
                    float sh1 = kind == 1 ? 0.5f : kind == 2 ? 0.7f : shadeRock * 0.85f * (1f - 0.45f * Math.Clamp((-y1 - 20f) / 150f, 0, 1));
                    GX_Vertex Q(float w, float y, float z, float s)
                    {
                        float u = kind == 2 ? z / 16f : kind == 1 ? z / 16f : z / 48f;
                        float v = kind == 2 ? (y == y0 ? 0.02f : 0.98f) : kind == 1 ? -y / 21f : -y / 48f;
                        return V(new Vector3(sx * w, y, z), new Vector3(sx, 0, 0), s, u, v);
                    }
                    if (left) Quad(list, Q(w0, y0, zb, sh0), Q(w0, y0, za, sh0), Q(w1, y1, za, sh1), Q(w1, y1, zb, sh1));
                    else Quad(list, Q(w0, y0, za, sh0), Q(w0, y0, zb, sh0), Q(w1, y1, zb, sh1), Q(w1, y1, za, sh1));
                }
            }
        }

        // ---- top: grass | kerb | sand path (front to back, aligned with the garden path) | kerb | grass ----
        var grassT = new List<GX_Vertex>(); var sandT = new List<GX_Vertex>(); var kerbT = new List<GX_Vertex>();
        float pathW = ys.TryGetProperty("path_half", out var phv) ? phv.GetSingle() : 11f;
        float kerbW = 1.5f;
        var xs = new List<float>();
        for (int j = 0; j <= NC; j++) xs.Add(-80f + 160f / NC * j);
        xs.AddRange(new[] { -pathW - kerbW, -pathW, pathW, pathW + kerbW });
        xs = xs.Distinct().OrderBy(x => x).ToList();
        float ZFront(float x) => Math.Abs(x) >= 80f - 0.01f ? ZF - CH : ZF;
        float ZBack(float x) => Math.Abs(x) >= 80f - 0.01f ? ZB + CH : ZB;
        const int NZT = 6;
        for (int i = 0; i + 1 < xs.Count; i++)
        {
            float xa = xs[i], xb = xs[i + 1], xm = (xa + xb) / 2;
            var list = Math.Abs(xm) < pathW ? sandT : Math.Abs(xm) < pathW + kerbW ? kerbT : grassT;
            for (int k = 0; k < NZT; k++)
            {
                float ta = k / (float)NZT, tb = (k + 1) / (float)NZT;
                Vector3 P(float x, float t) => new Vector3(x, YsTop(x) + (list == kerbT ? 0.02f : 0), ZFront(x) + (ZBack(x) - ZFront(x)) * t);
                GX_Vertex Q(Vector3 p)
                {
                    float s = shadeTop + 0.04f * Nz(p.X * 0.9f, p.Z * 1.3f) - (Math.Abs(p.X) > 56 ? 0.05f : 0);
                    float u = list == sandT ? p.X / 22f : list == kerbT ? p.Z / 16f : p.X / 40f;
                    float v = list == sandT ? p.Z / 22f : list == kerbT ? (Math.Abs(p.X) - pathW) / kerbW * 0.9f + 0.05f : p.Z / 40f;
                    return V(p, Vector3.UnitY, list == kerbT ? 0.8f : s, u, v);
                }
                Quad(list, Q(P(xa, ta)), Q(P(xb, ta)), Q(P(xb, tb)), Q(P(xa, tb)));
            }
        }

        // ---- platforms: metal slabs exactly on the collision lines ----
        float platFront = ys.TryGetProperty("plat_front", out var pfv) ? pfv.GetSingle() : 0.8f;
        var platTopT = new List<GX_Vertex>(); var platSideT = new List<GX_Vertex>(); var platUnderT = new List<GX_Vertex>();
        foreach (var (x0, x1, y) in new[] { (-85f, -40f, 33.5f), (40f, 85f, 33.5f), (-22.5f, 22.5f, 60f) })
        {
            const float TH = 3f, ZD = 11f;
            int n = Math.Max(1, (int)MathF.Round((x1 - x0) / 11f));
            for (int k = 0; k < n; k++)
            {
                float xa = x0 + (x1 - x0) * k / n, xb = x0 + (x1 - x0) * (k + 1) / n;
                Quad(platTopT, V(new(xa, y, ZD), Vector3.UnitY, 0.85f, 0, 1), V(new(xb, y, ZD), Vector3.UnitY, 0.85f, 1, 1),
                    V(new(xb, y, -ZD), Vector3.UnitY, 0.85f, 1, 0), V(new(xa, y, -ZD), Vector3.UnitY, 0.85f, 0, 0));
                Quad(platSideT, V(new(xa, y, ZD), Vector3.UnitZ, platFront, xa / 16f, 0.05f), V(new(xa, y - TH, ZD), Vector3.UnitZ, platFront * 0.75f, xa / 16f, 0.95f),
                    V(new(xb, y - TH, ZD), Vector3.UnitZ, platFront * 0.75f, xb / 16f, 0.95f), V(new(xb, y, ZD), Vector3.UnitZ, platFront, xb / 16f, 0.05f));
                Quad(platSideT, V(new(xb, y, -ZD), -Vector3.UnitZ, 0.6f, xb / 16f, 0.05f), V(new(xb, y - TH, -ZD), -Vector3.UnitZ, 0.5f, xb / 16f, 0.95f),
                    V(new(xa, y - TH, -ZD), -Vector3.UnitZ, 0.5f, xa / 16f, 0.95f), V(new(xa, y, -ZD), -Vector3.UnitZ, 0.6f, xa / 16f, 0.05f));
                Quad(platUnderT, V(new(xa, y - TH, -ZD), -Vector3.UnitY, 0.38f, 0, 0), V(new(xb, y - TH, -ZD), -Vector3.UnitY, 0.38f, 1, 0),
                    V(new(xb, y - TH, ZD), -Vector3.UnitY, 0.38f, 1, 1), V(new(xa, y - TH, ZD), -Vector3.UnitY, 0.38f, 0, 1));
            }
            foreach (var xe in new[] { x0, x1 })
            {
                float sxn = xe == x0 ? -1 : 1;
                var a = new Vector3(xe, y, -ZD); var b = new Vector3(xe, y, ZD); var c = new Vector3(xe, y - TH, ZD); var e = new Vector3(xe, y - TH, -ZD);
                if (sxn < 0) Quad(platSideT, V(a, -Vector3.UnitX, 0.6f, 0, 0.05f), V(b, -Vector3.UnitX, 0.6f, 1.4f, 0.05f), V(c, -Vector3.UnitX, 0.5f, 1.4f, 0.95f), V(e, -Vector3.UnitX, 0.5f, 0, 0.95f));
                else Quad(platSideT, V(b, Vector3.UnitX, 0.6f, 0, 0.05f), V(a, Vector3.UnitX, 0.6f, 1.4f, 0.05f), V(e, Vector3.UnitX, 0.5f, 1.4f, 0.95f), V(c, Vector3.UnitX, 0.5f, 0, 0.95f));
            }
        }

        var parts = new List<(HSD_MOBJ m, List<GX_Vertex> t, string name)>
        {
            (mGrass, grassT, "grass"), (mSand, sandT, "sand"), (mKerb, kerbT, "kerb"), (mLip, lipT, "lip"), (mRock, rockT, "rock"),
            (mRock, backT, "back"), (mRock, sideT, "side"), (mSlot, slotT, "slot"), (mKerb, frameT, "frame"),
            (mMetal, platTopT, "plat_top"), (mKerb, platSideT, "plat_side"), (mSlot, platUnderT, "plat_under"),
        };
        var dobjs = new List<HSD_DOBJ>();
        foreach (var (m, t, name) in parts)
        {
            if (t.Count == 0) continue;
            var d = MakeDobjCull(m, t, GenCullMode.None);
            dobjs.Add(d);
            Console.WriteLine($"  ys stage: {name} {t.Count / 3} tris");
        }
        for (int i = 0; i < dobjs.Count; i++) dobjs[i].Next = i + 1 < dobjs.Count ? dobjs[i + 1] : null;
        var g3 = groups[sg].RootNode;   // vanilla meshes are cleared by clear_groups; grafts (cloud sea) already appended
        Append(g3, new HSD_JOBJ { Flags = JOBJ_FLAG.OPA, SX = 1, SY = 1, SZ = 1, Dobj = dobjs[0] });
        g3.Flags |= JOBJ_FLAG.ROOT_OPA | JOBJ_FLAG.ROOT_XLU | JOBJ_FLAG.ROOT_TEXEDGE;
        if (ys.TryGetProperty("drop_stage_anims", out var dsa) && dsa.GetBoolean() && groups[sg].MaterialAnimations == null)
        {
            // the YS stage code asks for anim 1 at joint 5 by array index (&aj_t[5]); drop the vanilla anims so that never
            // touches a re-laid-out tree. (Groups that received grafts already got a single anim 0 instead.)
            var ja = groups[sg].JointAnimations;
            if (ja != null && ja.Length > 1) { groups[sg].JointAnimations = null; Console.WriteLine($"  ys: group {sg} vanilla anims dropped"); }
            head.ModelGroups[sg] = groups[sg];
        }

        // ================= cliff face (receive group) =================
        if (ys.TryGetProperty("face", out var fe))
        {
            float fz = fe.GetProperty("z").GetSingle(), yc = fe.GetProperty("y_edge").GetSingle();
            float xMax = fe.GetProperty("x_max").GetSingle(), yLo = fe.GetProperty("y_bottom").GetSingle(), yHi = fe.GetProperty("y_top").GetSingle();
            (float y, float w)[] Prof(string key) => fe.GetProperty(key).EnumerateArray().Select(e => (y: e[0].GetSingle(), w: e[1].GetSingle())).OrderBy(p => p.y).ToArray();
            var profL = Prof(fe.TryGetProperty("opening_left", out _) ? "opening_left" : "opening");
            var profR = Prof(fe.TryGetProperty("opening_right", out _) ? "opening_right" : "opening");
            float WoP((float y, float w)[] prof, float y)
            {
                if (y <= prof[0].y) return prof[0].w;
                for (int i = 0; i + 1 < prof.Length; i++) if (y <= prof[i + 1].y) return prof[i].w + (prof[i + 1].w - prof[i].w) * (y - prof[i].y) / (prof[i + 1].y - prof[i].y);
                return prof[^1].w;
            }
            float Wo(float y) => Math.Min(WoP(profL, y), WoP(profR, y));
            var mFaceRock = fe.TryGetProperty("tex", out var ftx) ? Mat(Seamless(Crop(ftx, 256, 256), 256, 256, true, true), 256, 256, REP, REP) : mRock;
            float fShade = fe.TryGetProperty("shade", out var fsv) ? fsv.GetSingle() : 0.5f;
            float relief = fe.TryGetProperty("relief", out var rlv) ? rlv.GetSingle() : 14f;
            float uvS = fe.TryGetProperty("uv", out var uvv) ? uvv.GetSingle() : 110f;
            float bigRelief = fe.TryGetProperty("big_relief", out var brv) ? brv.GetSingle() : 0f;
            float rimH = fe.TryGetProperty("rim", out var rmv) ? rmv.GetSingle() : 0f;
            float DistOpen(float x, float y) => y < yc ? 999f : Math.Abs(x) - WoP(x < 0 ? profL : profR, y);
            float ZAt(float x, float y)
            {
                float k = Math.Clamp(Math.Abs(y - yc) / 30f, 0, 1);                          // flat along the plateau edge (shared row)
                float kb = Math.Clamp((DistOpen(x, y) - 40f) / 120f, 0, 1) * k;               // big bulges only away from the canyon mouth
                return fz + 2f + relief * k * (0.5f + 0.5f * Nz(x * 0.45f, y * 0.45f))       // never behind fz: the cut canyon ends sit at fz
                     + bigRelief * kb * (0.5f + 0.5f * Nz(x * 0.11f + 40f, y * 0.13f - 20f));
            }
            float Sh(float x, float y) => fShade * (y < yc ? 1f - 0.5f * Math.Clamp((yc - y) / 160f, 0, 1) : 1f) * (0.88f + 0.14f * Nz(x * 0.8f, y * 0.8f))
                                        * (0.85f + 0.3f * (ZAt(x, y) - fz) / Math.Max(1f, relief + bigRelief));   // crevices darker
            GX_Vertex VT(Vector3 p, float sh, float u, float v)
            {
                // moss: a green tint where a slow noise is high (the canyon walls carry the same green streaks)
                float m = Math.Clamp((Nz(p.X * 0.21f - 7f, p.Y * 0.17f + 3f) - 0.15f) * 2.2f, 0, 1) * 0.55f;
                var c = new GXColor4(Math.Clamp(sh * (1f - 0.18f * m), 0, 1), Math.Clamp(sh * (1f + 0.12f * m), 0, 1), Math.Clamp(sh * (1f - 0.3f * m), 0, 1), 1);
                return new GX_Vertex { POS = new GXVector3(p.X, p.Y, p.Z), NRM = new GXVector3(0, 0, 1), CLR0 = c, TEX0 = new GXVector2(u, v) };
            }
            var faceT = new List<GX_Vertex>(); var faceLip = new List<GX_Vertex>();
            GX_Vertex F(float x, float y, float z) => VT(new Vector3(x, y, z), Sh(x, y), x / uvS + (z - fz) / uvS * 0.5f, -y / uvS);
            // part A: full width below the plateau edge
            var ra = new List<float>(); for (float y = yLo; y < yc - 16f; y += 40f) ra.Add(y); ra.Add(yc - 16f); ra.Add(yc);
            const int NA = 34;
            for (int r = 0; r + 1 < ra.Count; r++)
                for (int j = 0; j < NA; j++)
                {
                    float xa = -xMax + 2 * xMax * j / NA, xb = -xMax + 2 * xMax * (j + 1) / NA;
                    float y0 = ra[r + 1], y1 = ra[r];   // y0 above
                    bool lip = r == ra.Count - 2 && Math.Abs((xa + xb) / 2) < Wo(yc) + 4f;
                    if (lip && rimH > 0)
                    {
                        // a jagged rock rim instead of a straight grass edge: the plateau must not read as a second stage
                        const int SUB = 5;
                        for (int q = 0; q < SUB; q++)
                        {
                            float xq0 = xa + (xb - xa) * q / SUB, xq1 = xa + (xb - xa) * (q + 1) / SUB;
                            float Rim(float x) => yc + rimH * (0.25f + 0.75f * Math.Clamp(0.5f + 0.9f * Nz(x * 1.9f + 11f, 3f), 0, 1));
                            GX_Vertex Rq(float x, float y, float z) => VT(new Vector3(x, y, z), Sh(x, y) * 1.05f, x / uvS, -y / uvS);
                            // bottom edge stays ON the row below's straight top edge (no T-junction cracks)
                            float za = ZAt(xa, y1), zb = ZAt(xb, y1);
                            float zq0 = za + (zb - za) * q / SUB, zq1 = za + (zb - za) * (q + 1) / SUB;
                            Quad(faceT, Rq(xq0, Rim(xq0), fz - 3f), Rq(xq1, Rim(xq1), fz - 3f), Rq(xq1, y1, zq1), Rq(xq0, y1, zq0));
                        }
                    }
                    else if (lip)
                    {
                        GX_Vertex L(float x, float y, float z, float v) => V(new Vector3(x, y, z), Vector3.UnitZ, fShade + 0.15f, x / 64f, v);
                        Quad(faceLip, L(xa, y0 + 0.3f, fz - 2f, 0.01f), L(xb, y0 + 0.3f, fz - 2f, 0.01f), L(xb, y1, ZAt(xb, y1), 0.98f), L(xa, y1, ZAt(xa, y1), 0.98f));
                    }
                    else Quad(faceT, F(xa, y0, ZAt(xa, y0)), F(xb, y0, ZAt(xb, y0)), F(xb, y1, ZAt(xb, y1)), F(xa, y1, ZAt(xa, y1)));
                }
            // parts B/C: beside the canyon opening, up to y_top; the inner edge wraps back into the canyon
            var rb = new List<float> { yc }; for (float y = yc + 24f; y < yHi; y += 40f) rb.Add(y); rb.Add(yHi);
            const int NB = 16;
            foreach (float sx in new[] { -1f, 1f })
                for (int r = 0; r + 1 < rb.Count; r++)
                {
                    float y0 = rb[r + 1], y1 = rb[r];
                    for (int j = 0; j <= NB; j++)
                    {
                        // column j: 0 = the wrap-back edge inside the canyon, 1 = the opening edge, NB = x_max
                        Vector3 P(float y, int jj)
                        {
                            float w = WoP(sx < 0 ? profL : profR, y);
                            if (jj == 0) return new Vector3(sx * (w + 7f), y, fz - 14f);
                            float x = w + (xMax - w) * (jj - 1) / (NB - 1f);
                            return new Vector3(sx * x, y, jj == 1 ? fz + 2f : ZAt(sx * x, y));
                        }
                        if (j == NB) break;
                        var a = P(y0, j); var b = P(y0, j + 1); var c = P(y1, j + 1); var e = P(y1, j);
                        GX_Vertex Q(Vector3 p) => VT(p, Sh(p.X, p.Y), p.X / uvS + (p.Z - fz) / uvS * 0.5f, -p.Y / uvS);
                        if (sx < 0) Quad(faceT, Q(b), Q(a), Q(e), Q(c));
                        else Quad(faceT, Q(a), Q(b), Q(c), Q(e));
                    }
                }
            var dF = MakeDobjCull(mFaceRock, faceT, GenCullMode.None);
            var dL = MakeDobjCull(mLip, faceLip, GenCullMode.None);
            dF.Next = dL;
            Append(groot, new HSD_JOBJ { Flags = JOBJ_FLAG.OPA, SX = 1, SY = 1, SZ = 1, Dobj = dF });
            Console.WriteLine($"  ys face: {faceT.Count / 3} tris + lip {faceLip.Count / 3}");
        }

        // ================= Randall (group 2) =================
        if (ys.TryGetProperty("randall", out var re))
        {
            var g2 = groups[2]; var t2 = g2.RootNode.TreeList;
            var j1 = t2[1];
            j1.Dobj = null;
            j1.Flags &= ~(JOBJ_FLAG.VBILLBOARD | JOBJ_FLAG.BILLBOARD | JOBJ_FLAG.HBILLBOARD | JOBJ_FLAG.PBILLBOARD);
            j1.Flags |= JOBJ_FLAG.OPA | JOBJ_FLAG.ROOT_OPA | JOBJ_FLAG.ROOT_XLU | JOBJ_FLAG.ROOT_TEXEDGE;   // HSD_JObjDispAll only descends through joints with the pass's ROOT_* flag
            g2.RootNode.Flags |= JOBJ_FLAG.ROOT_OPA | JOBJ_FLAG.ROOT_XLU | JOBJ_FLAG.ROOT_TEXEDGE;   // vanilla root had TEXEDGE only: OPA meshes were never drawn
            g2.MaterialAnimations = null;          // Randall's face flip-book would retarget onto the new materials
            head.ModelGroups[2] = g2;
            var rf = re.GetProperty("file").GetString();
            if (!donorFiles.TryGetValue(rf, out var rdf)) { rdf = new HSDRawFile(rf); donorFiles[rf] = rdf; memos[rf] = new Dictionary<HSDStruct, HSDStruct>(); }
            var src = Scene(rdf).JOBJDescs[re.TryGetProperty("desc", out var rdv) ? rdv.GetInt32() : 0].RootJoint;
            var clone = Copy(src, memos[rf]);
            var pl = re.GetProperty("place");
            var pt = pl.GetProperty("t").EnumerateArray().Select(e => e.GetSingle()).ToArray();
            float ps = pl.TryGetProperty("s", out var psv) ? psv.GetSingle() : 1f;
            float ry = (pl.TryGetProperty("ry", out var ryv) ? ryv.GetSingle() : 0f) * MathF.PI / 180f;
            float dropAbove = re.TryGetProperty("drop_above", out var dav) ? dav.GetSingle() : float.MaxValue;   // model-space y: trim walls above the deck
            int trimmed = 0;
            if (dropAbove < float.MaxValue)
            {
                var worlds = new Dictionary<HSD_JOBJ, Matrix4x4>();
                Worlds(clone, Matrix4x4.Identity, worlds);
                foreach (var jo in clone.TreeList)
                {
                    if (jo.Dobj == null) continue;
                    foreach (var d in jo.Dobj.List)
                    {
                        HSD_POBJ headP = null, tailP = null;
                        foreach (var p in d.Pobj.List)
                        {
                            HSD_POBJ np = p;
                            if (Rigid(p))
                            {
                                var tris = Triangles(p.ToDisplayList()); var keep = new List<GX_Vertex>();
                                for (int i = 0; i + 2 < tris.Count; i += 3)
                                {
                                    float ymax = Enumerable.Range(0, 3).Max(k => Vector3.Transform(new Vector3(tris[i + k].POS.X, tris[i + k].POS.Y, tris[i + k].POS.Z), worlds[jo]).Y);
                                    if (ymax > dropAbove) { trimmed++; continue; }
                                    keep.Add(tris[i]); keep.Add(tris[i + 1]); keep.Add(tris[i + 2]);
                                }
                                if (keep.Count == 0) continue;
                                var attrs = p.ToGXAttributes().Select(a => a.AttributeName).Where(a => a != GXAttribName.GX_VA_NULL).ToArray();
                                var cf = p.Flags.HasFlag(POBJ_FLAG.CULLFRONT); var cb = p.Flags.HasFlag(POBJ_FLAG.CULLBACK);
                                var gen = new POBJ_Generator { CullMode = cf && cb ? GenCullMode.FrontAndBack : cf ? GenCullMode.Front : cb ? GenCullMode.Back : GenCullMode.None, VertexColorFormat = (GXCompType)GXCompTypeClr.RGBA8 };
                                np = gen.CreatePOBJsFromTriangleList(keep, attrs, null); gen.SaveChanges();
                            }
                            var last = np; while (last.Next != null) last = last.Next;
                            if (headP == null) headP = np; else tailP.Next = np;
                            tailP = last;
                        }
                        if (tailP != null) tailP.Next = null;
                        d.Pobj = headP;
                    }
                }
            }
            if (re.TryGetProperty("bake_flat", out var bfv) && bfv.GetBoolean())
            {
                // lit model on a lit-by-YS joint: draw unlit with its own vertex/material colour (no Melee lights on it)
                foreach (var jo in clone.TreeList) if (jo.Dobj != null) foreach (var d in jo.Dobj.List)
                    if (d.Mobj != null) d.Mobj.RenderFlags &= ~(RENDER_MODE.DIFFUSE | RENDER_MODE.SPECULAR);
            }
            if (re.TryGetProperty("tex_modulate", out var rtm) && rtm.GetBoolean())
                foreach (var jo in clone.TreeList) if (jo.Dobj != null) foreach (var d in jo.Dobj.List) if (d.Mobj?.Textures != null)
                    foreach (var tt in d.Mobj.Textures.List)
                    {
                        int f = (int)tt.Flags;
                        if ((f & 0xF0000) == (3 << 16)) f = (f & ~0xF0000) | (4 << 16);
                        if ((f & 0xF00000) == (2 << 20)) f = (f & ~0xF00000) | (3 << 20);
                        tt.Flags = (TOBJ_FLAGS)f;
                    }
            if (re.TryGetProperty("ambient", out var amb))
            {
                float k = amb.GetSingle(); var seen = new HashSet<HSDStruct>();
                foreach (var jo in clone.TreeList) if (jo.Dobj != null) foreach (var d in jo.Dobj.List)
                    if (d.Mobj?.Material != null && seen.Add(d.Mobj._s)) { var c = d.Mobj.Material.AmbientColor; d.Mobj.Material.AmbientColor = System.Drawing.Color.FromArgb(c.A, (int)(c.R * k), (int)(c.G * k), (int)(c.B * k)); }
            }
            var holder = new HSD_JOBJ { Flags = JOBJ_FLAG.ROOT_OPA | JOBJ_FLAG.ROOT_XLU | JOBJ_FLAG.ROOT_TEXEDGE, SX = ps, SY = ps, SZ = ps, RY = ry, TX = pt[0], TY = pt[1], TZ = pt[2], Child = clone };
            Append(j1, holder);   // after j2 in j1's child chain; the code only uses depth 1 (j1) and the PATH AOBJ points at j3 directly
            Console.WriteLine($"  ys randall: {src.TreeList.Count} joints under group 2 j1, trimmed {trimmed} tris above {dropAbove}");
        }
    }

    static HSD_DOBJ MakeDobjCull(HSD_MOBJ m, List<GX_Vertex> tris, GenCullMode cull)
    {
        var gen = new POBJ_Generator { CullMode = cull, VertexColorFormat = (GXCompType)GXCompTypeClr.RGBA8 };
        var p = gen.CreatePOBJsFromTriangleList(tris, new[] { GXAttribName.GX_VA_POS, GXAttribName.GX_VA_NRM, GXAttribName.GX_VA_CLR0, GXAttribName.GX_VA_TEX0 }, null);
        gen.SaveChanges();
        return new HSD_DOBJ { Mobj = m, Pobj = p };
    }

    // Colosseum character fixes for a cloned model (same rules as the donor path): CI4/tiny textures to direct colour,
    // COLORMAP_BLEND -> modulate, ambient scale, and the untextured hit-box meshes stripped.
    static void CharFix(HSD_JOBJ clone, JsonElement o)
    {
        var tl = clone.TreeList;
        if (o.TryGetProperty("strip_cubes", out var sc) && sc.GetBoolean())
            foreach (var jo in tl)
            {
                if (jo.Dobj == null) continue;
                var keep = jo.Dobj.List.Where(d => d.Mobj?.Textures != null && !jo.Flags.HasFlag(JOBJ_FLAG.HIDDEN)).ToList();
                for (int i = 0; i < keep.Count; i++) keep[i].Next = i + 1 < keep.Count ? keep[i + 1] : null;
                jo.Dobj = keep.Count > 0 ? keep[0] : null;
            }
        var seenT = new HashSet<HSDStruct>(); var seenM = new HashSet<HSDStruct>();
        float amb = o.TryGetProperty("ambient", out var av) ? av.GetSingle() : 1f;
        foreach (var jo in tl) if (jo.Dobj != null) foreach (var d in jo.Dobj.List)
        {
            if (d.Mobj?.Material != null && amb != 1f && d.Mobj.RenderFlags.HasFlag(RENDER_MODE.DIFFUSE) && seenM.Add(d.Mobj._s))
            {
                var c = d.Mobj.Material.AmbientColor;
                d.Mobj.Material.AmbientColor = System.Drawing.Color.FromArgb(c.A, (int)(c.R * amb), (int)(c.G * amb), (int)(c.B * amb));
            }
            if (d.Mobj?.Textures == null) continue;
            foreach (var tt in d.Mobj.Textures.List)
            {
                if (!seenT.Add(tt._s)) continue;
                int f = (int)tt.Flags;
                if ((f & 0xF0000) == (3 << 16)) f = (f & ~0xF0000) | (4 << 16);
                if ((f & 0xF00000) == (2 << 20)) f = (f & ~0xF00000) | (3 << 20);
                tt.Flags = (TOBJ_FLAGS)f;
                if (tt.ImageData != null && (tt.ImageData.Format == GXTexFmt.CI4 ||
                    ((tt.ImageData.Format == GXTexFmt.CMP || tt.ImageData.Format == GXTexFmt.CI8) && (tt.ImageData.Width <= 8 || tt.ImageData.Height <= 8))))
                {
                    var px = tt.GetDecodedImageData(); int w = tt.ImageData.Width, h = tt.ImageData.Height;
                    bool alpha = false; for (int i = 3; i < px.Length; i += 4) if (px[i] < 250) { alpha = true; break; }
                    tt.ImageData = new HSD_Image();
                    tt.EncodeImageData(px, w, h, alpha ? GXTexFmt.RGB5A3 : GXTexFmt.RGB565, GXTlutFmt.RGB565);
                    tt.TlutData = null;
                }
            }
        }
    }

    // Yoshi's Story's Shy Guys are a stage item (kind 0xD2) whose model lives in GrSt.dat's itemdata: a 2-joint card with
    // a texture flip-book. Swap the card for a Colosseum model hung under the same joint j1 (so it keeps the item's own
    // bob anim, hurtbox bone and facing flip), and append its idle anim to each state's anim tree. The item code copies
    // every joint into a 100-entry bone table, so the model must stay small (Castform: 6 joints).
    static void BuildHeiho(JsonElement hh, HSDRawFile file, Dictionary<string, HSDRawFile> donorFiles, Dictionary<string, Dictionary<HSDStruct, HSDStruct>> memos)
    {
        var itemRoot = file.Roots.First(r => r.Name == "itemdata").Data._s;
        var art = itemRoot.References[0].References[4];
        var md = art.References[0x10];
        var root = new HSD_JOBJ { _s = md.References[0] };
        var j1 = root.Child;
        var mf = hh.GetProperty("file").GetString();
        if (!donorFiles.TryGetValue(mf, out var df)) { df = new HSDRawFile(mf); donorFiles[mf] = df; memos[mf] = new Dictionary<HSDStruct, HSDStruct>(); }
        var jd = Scene(df).JOBJDescs[hh.TryGetProperty("desc", out var dv) ? dv.GetInt32() : 0];
        var memo = new Dictionary<HSDStruct, HSDStruct>();   // its own copy: the item instantiates it per Shy Guy
        var clone = Copy(jd.RootJoint, memo);
        CharFix(clone, hh);
        int total = root.TreeList.Count + 1 + clone.TreeList.Count;
        if (total > 100) throw new Exception($"heiho: {total} joints would overflow the item bone table (100)");
        var pl = hh.GetProperty("place");
        var pt = pl.GetProperty("t").EnumerateArray().Select(e => e.GetSingle()).ToArray();
        float ps = pl.TryGetProperty("s", out var psv) ? psv.GetSingle() : 1f;
        float ry = (pl.TryGetProperty("ry", out var ryv) ? ryv.GetSingle() : 0f) * MathF.PI / 180f;
        var holder = new HSD_JOBJ { Flags = JOBJ_FLAG.ROOT_OPA | JOBJ_FLAG.ROOT_XLU | JOBJ_FLAG.ROOT_TEXEDGE, SX = ps, SY = ps, SZ = ps, RY = ry, TX = pt[0], TY = pt[1], TZ = pt[2], Child = clone };
        if (!(hh.TryGetProperty("keep_card", out var kc) && kc.GetBoolean())) j1.Dobj = null;
        if (j1.Child != null) throw new Exception("heiho: j1 already has children");
        j1.Child = holder;
        root.Flags |= JOBJ_FLAG.ROOT_OPA | JOBJ_FLAG.ROOT_XLU | JOBJ_FLAG.ROOT_TEXEDGE;
        j1.Flags |= JOBJ_FLAG.OPA | JOBJ_FLAG.ROOT_OPA | JOBJ_FLAG.ROOT_XLU | JOBJ_FLAG.ROOT_TEXEDGE;

        HSD_AnimJoint animClone = null;
        int ai = hh.TryGetProperty("anim_index", out var aiv) ? aiv.GetInt32() : 0;
        if (jd.JointAnimations != null && jd.JointAnimations.Length > ai) { animClone = Copy(jd.JointAnimations[ai], memo); SetLoop(animClone); }
        var st = art.References[0xC];
        int states = 0;
        for (int s = 0; s * 0x10 < st.Length; s++)
        {
            if (animClone == null) break;
            if (!st.References.TryGetValue(s * 0x10, out var ajs)) continue;
            var aroot = new HSD_AnimJoint { _s = ajs };
            var a1 = aroot.Child;
            if (a1 == null) { a1 = new HSD_AnimJoint(); aroot.Child = a1; }
            a1.Child = new HSD_AnimJoint { Child = animClone };   // holder (no track) -> the model's own tree
            states++;
        }
        Console.WriteLine($"  heiho: {clone.TreeList.Count} joints under the Shy Guy's j1 ({total} total), anim {ai} on {states} states");
    }
}
