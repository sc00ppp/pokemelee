// Final Destination rebuilt as a Mt. Battle steel battle deck: a lathe on FD's exact collision profile, its top a
// single disc texture baked from the Mt. Battle arena floor (the "100" emblem), riveted drum rim with a hazard lip,
// an underside of lava-lit steel bands on FD's spinning joint 4, and a screw-jack column on spinning joint 1 that
// runs down into the lava. FD's background cycle (groups 4-9, driven by grlast.c) keeps its joints and anims so the
// state machine still works, but loses its meshes and particle tracks; the global fog is pushed past the far plane
// so the cycle's fog-colour fades can't tint the crater.
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
    static void BuildFd(JsonElement fd, SBM_Map_Head head, SBM_Map_GOBJ[] groups,
        Dictionary<string, HSDRawFile> donorFiles, Dictionary<string, Dictionary<HSDStruct, HSDStruct>> memos)
    {
        var path = fd.GetProperty("file").GetString();
        if (!donorFiles.TryGetValue(path, out var df)) { df = new HSDRawFile(path); donorFiles[path] = df; memos[path] = new Dictionary<HSDStruct, HSDStruct>(); }
        var descs = Scene(df).JOBJDescs.Array;
        HSD_TOBJ SrcT(JsonElement e) => descs[e[0].GetInt32()].RootJoint.TreeList[e[1].GetInt32()].Dobj.List[e[2].GetInt32()].Mobj.Textures.List[e[3].GetInt32()];
        HSD_MOBJ SrcM(JsonElement e) => descs[e[0].GetInt32()].RootJoint.TreeList[e[1].GetInt32()].Dobj.List[e[2].GetInt32()].Mobj;
        byte[] Px(JsonElement e, out int w, out int h) { var t = SrcT(e); w = t.ImageData.Width; h = t.ImageData.Height; return t.GetDecodedImageData(); }
        // [desc, joint, dobj, tex, (rot90 0/1), (x0, y0, x1, y1)] -> dw x dh BGRA
        byte[] Tex(JsonElement e, int dw, int dh)
        {
            var px = Px(e, out int w, out int h);
            bool rot = e.GetArrayLength() > 4 && e[4].GetInt32() == 1;
            int x0 = 0, y0 = 0, x1 = w, y1 = h;
            if (e.GetArrayLength() > 8) { x0 = e[5].GetInt32(); y0 = e[6].GetInt32(); x1 = e[7].GetInt32(); y1 = e[8].GetInt32(); }
            var c = CropResize(px, w, x0, y0, x1 - x0, y1 - y0, rot ? dh : dw, rot ? dw : dh);
            if (!rot) return c;
            // rotate 90 degrees: source (dh wide, dw tall) -> dest dw x dh
            var o = new byte[dw * dh * 4];
            for (int y = 0; y < dh; y++)
                for (int x = 0; x < dw; x++)
                    for (int k = 0; k < 4; k++) o[(y * dw + x) * 4 + k] = c[(x * dh + (dh - 1 - y)) * 4 + k];
            return o;
        }

        var tmplM = Copy(SrcM(fd.GetProperty("material")), memos[path]);
        HSD_MOBJ Mat(byte[] px, int w, int h, GXWrapMode ws, GXWrapMode wt)
        {
            for (int i = 3; i < px.Length; i += 4) px[i] = 255;
            var t = NewTobj(tmplM.Textures, px, w, h, ws, wt);
            t.Flags = TOBJ_FLAGS.LIGHTMAP_DIFFUSE | TOBJ_FLAGS.COLORMAP_MODULATE;
            t.Blending = 1; t.TEV = null;
            t.GXTexGenSrc = GXTexGenSrc.GX_TG_TEX0; t.TexMapID = GXTexMapID.GX_TEXMAP0;
            var m = MobjWith(tmplM, t);
            m.RenderFlags = RENDER_MODE.VERTEX | RENDER_MODE.TEX0;
            if (m.Material != null) { m.Material.DiffuseColor = System.Drawing.Color.White; m.Material.AmbientColor = System.Drawing.Color.White; m.Material.Alpha = 1; }
            noBrighten.Add(m._s);
            return m;
        }
        const GXWrapMode REP = GXWrapMode.REPEAT, CLA = GXWrapMode.CLAMP, MIR = GXWrapMode.MIRROR;
        HSD_MOBJ MatE(string key, int w, int h, GXWrapMode ws, GXWrapMode wt) => Mat(Tex(fd.GetProperty(key), w, h), w, h, ws, wt);

        // ---- the arena floor (desc 1 floor + "100" decal + grates) baked into one disc ----
        var fl = fd.GetProperty("floor");
        int FS = fl.GetProperty("size").GetInt32();
        var floorPx = BakeTop(df, ParseItems(fl.GetProperty("items").EnumerateArray().Select(e => e.GetString())),
            fl.GetProperty("cx").GetSingle(), fl.GetProperty("cz").GetSingle(), fl.GetProperty("r").GetSingle(), FS);
        if (fl.TryGetProperty("tone", out var ftn))
        {
            float k = ftn.GetSingle();
            for (int i = 0; i < floorPx.Length; i++) if (i % 4 != 3) floorPx[i] = (byte)Math.Clamp(floorPx[i] * k, 0, 255);
        }
        var mTop = Mat(floorPx, FS, FS, CLA, CLA);
        var mHaz = MatE("hazard", 128, 32, REP, CLA);
        var mRim = MatE("rim", 128, 64, REP, CLA);
        var mSlope = MatE("slope", 64, 64, REP, REP);
        var mPipe = MatE("pipe", 128, 64, REP, CLA);
        var mPanel = MatE("panel", 128, 128, REP, REP);
        var mBottom = MatE("bottom", 128, 128, REP, REP);
        var mCollar = MatE("collar", 64, 64, REP, CLA);
        var mScrew = MatE("screw", 64, 64, REP, REP);

        // ---- shading baked into vertex colours, symmetric about the y axis (the underside spins) ----
        var glow = fd.GetProperty("glow").EnumerateArray().Select(e => e.GetSingle()).ToArray();   // lava bounce colour
        float lavaY = fd.GetProperty("lava_y").GetSingle();
        GXColor4 Shade(Vector3 n, float y)
        {
            n = Vector3.Normalize(n);
            float sky = 0.58f + 0.34f * Math.Max(0f, n.Y);
            float down = Math.Max(0f, -n.Y);
            float h = Math.Clamp((y - lavaY) / (0f - lavaY), 0f, 1f);              // 0 at the lava, 1 at the deck top
            float g = (0.65f * down + 0.25f * (1 - Math.Abs(n.Y))) * (0.45f + 0.55f * (1 - h));
            return new GXColor4(Math.Min(1f, sky + g * glow[0]), Math.Min(1f, sky * 0.97f + g * glow[1]), Math.Min(1f, sky * 0.94f + g * glow[2]), 1);
        }
        GX_Vertex V(Vector3 p, Vector3 n, float u, float v, float shadeMul = 1f)
        {
            var c = Shade(n, p.Y);
            return new GX_Vertex { POS = new GXVector3(p.X, p.Y, p.Z), NRM = new GXVector3(n.X, n.Y, n.Z),
                CLR0 = new GXColor4(c.R * shadeMul, c.G * shadeMul, c.B * shadeMul, 1), TEX0 = new GXVector2(u, v) };
        }

        const float R = 85.57f; const int N = 64;
        // top: flat on the collision floor, the baked arena disc
        var top = new List<GX_Vertex>();
        var rings = new[] { 0f, 10f, 22f, 34f, 46f, 58f, 68f, 76f, 82f, R };
        for (int i = 0; i + 1 < rings.Length; i++)
            for (int k = 0; k < N; k++)
            {
                float a0 = k * MathF.Tau / N, a1 = (k + 1) * MathF.Tau / N;
                GX_Vertex Q(float r, float a) { var p = new Vector3(r * MathF.Cos(a), 0f, r * MathF.Sin(a)); var v = V(p, Vector3.UnitY, 0.5f + p.X / (2 * R), 0.5f + p.Z / (2 * R)); v.CLR0 = new GXColor4(0.93f, 0.93f, 0.93f, 1); return v; }
                Quad(top, Q(rings[i], a0), Q(rings[i], a1), Q(rings[i + 1], a1), Q(rings[i + 1], a0));
            }

        HSD_DOBJ Lathe(HSD_MOBJ m, (float r, float y)[] prof, float uTiles, float vLen, int sides, float vOff = 0f)
        {
            var t = new List<GX_Vertex>();
            var s = new float[prof.Length];
            for (int i = 1; i < prof.Length; i++) s[i] = s[i - 1] + MathF.Sqrt(MathF.Pow(prof[i].r - prof[i - 1].r, 2) + MathF.Pow(prof[i].y - prof[i - 1].y, 2));
            var nrm = new Vector2[prof.Length];
            for (int i = 0; i < prof.Length; i++)
            {
                var sum = Vector2.Zero;
                foreach (var (a, b) in new[] { (i - 1, i), (i, i + 1) })
                {
                    if (a < 0 || b >= prof.Length) continue;
                    var tg = Vector2.Normalize(new Vector2(prof[b].r - prof[a].r, prof[b].y - prof[a].y));
                    sum += new Vector2(-tg.Y, tg.X);
                }
                nrm[i] = Vector2.Normalize(sum);
                if (nrm[i].X < 0 && prof[i].r > 0.01f) nrm[i] = -nrm[i];      // outward
                if (prof.All(p => MathF.Abs(p.y - prof[0].y) < 0.01f)) nrm[i] = new Vector2(0, -1);   // flat bottom ring faces down
            }
            float total = vLen > 0 ? vLen : s[^1];
            for (int i = 0; i + 1 < prof.Length; i++)
                for (int k = 0; k < sides; k++)
                {
                    float a0 = k * MathF.Tau / sides, a1 = (k + 1) * MathF.Tau / sides;
                    GX_Vertex Q(int pi, float a, int kk)
                    {
                        var p = new Vector3(prof[pi].r * MathF.Cos(a), prof[pi].y, prof[pi].r * MathF.Sin(a));
                        var n = Vector3.Normalize(new Vector3(nrm[pi].X * MathF.Cos(a), nrm[pi].Y, nrm[pi].X * MathF.Sin(a)));
                        return V(p, n, kk / (float)sides * uTiles, vOff + s[pi] / total);
                    }
                    Quad(t, Q(i, a0, k), Q(i, a1, k + 1), Q(i + 1, a1, k + 1), Q(i + 1, a0, k));
                }
            return MakeDobjUV(m, t);
        }

        // FD's collision, right side, from the ledge down: (85.57, 0) (85.57, -10.5) (65.8, -20.45) (65.84, -31.34)
        // (61.42, -47.37) (53.77, -54.26) (47.46, -55.39), flat underside to the centre
        float hazH = fd.TryGetProperty("hazard_h", out var hh) ? hh.GetSingle() : 1.8f;
        var staticBands = new List<HSD_DOBJ>
        {
            MakeDobjUV(mTop, top),
            Lathe(mHaz, new[] { (R, 0f), (R, -hazH) }, 40, 0, N),
            Lathe(mRim, new[] { (R, -hazH), (R, -10.5f) }, 22, 0, N),
        };
        float colR = fd.GetProperty("column_r").GetSingle(), colBot = fd.GetProperty("column_bottom").GetSingle();
        var spinBands = new List<HSD_DOBJ>
        {
            Lathe(mSlope, new[] { (R, -10.5f), (65.8f, -20.45f) }, 30, 0, N),
            Lathe(mPipe, new[] { (65.8f, -20.45f), (65.84f, -31.34f) }, 18, 0, N),
            Lathe(mPanel, new[] { (65.84f, -31.34f), (61.42f, -47.37f), (53.77f, -54.26f), (47.46f, -55.39f) }, 14, 30f, N),
            Lathe(mBottom, new[] { (47.46f, -55.39f), (colR + 5f, -55.39f) }, 12, 12f, N),
        };
        var screwBands = new List<HSD_DOBJ>
        {
            Lathe(mCollar, new[] { (colR + 5f, -55.39f), (colR + 5f, -60f), (colR + 3f, -63f), (colR + 1.5f, -64f) }, 10, 0, 32),
            Lathe(mScrew, new[] { (colR, -63f), (colR, colBot) }, 4, 22f, 24),
        };
        void Chain(List<HSD_DOBJ> l) { for (int i = 0; i < l.Count; i++) l[i].Next = i + 1 < l.Count ? l[i + 1] : null; }
        Chain(staticBands); Chain(spinBands); Chain(screwBands);

        // ---- group 3: vanilla FD meshes out; deck top + rim on the static joint 3, underside on joint 4 (spins -1 turn
        // per 10 s), screw column on joint 1 (spins +1 turn per 10 s) ----
        var t3 = groups[3].RootNode.TreeList;
        foreach (var jo in t3) jo.Dobj = null;
        const JOBJ_FLAG Clear = JOBJ_FLAG.LIGHTING | JOBJ_FLAG.SPECULAR | JOBJ_FLAG.XLU | JOBJ_FLAG.BILLBOARD;
        void Put(int j, HSD_DOBJ d) { t3[j].Dobj = d; t3[j].Flags = (t3[j].Flags & ~Clear) | JOBJ_FLAG.OPA; }
        Put(3, staticBands[0]); Put(4, spinBands[0]); Put(1, screwBands[0]);
        t3[2].Flags &= ~JOBJ_FLAG.BILLBOARD;
        if (groups[3].MaterialAnimations != null)
            foreach (var ma0 in groups[3].MaterialAnimations.Array)
                if (ma0 != null) foreach (var n in DfsM(ma0)) n.MaterialAnimation = null;    // would retarget onto the new materials
        head.ModelGroups[3] = groups[3];
        Console.WriteLine($"fd: deck top {top.Count / 3} tris, rim+hazard, {spinBands.Count} spinning underside bands, screw column r {colR} to y {colBot}");

        // ---- groups 4-9 (FD's background cycle): keep joints + anims (grlast.c checks their AObjs), drop meshes and particles ----
        int dropped = 0, ptcl = 0;
        for (int g = 4; g <= 9 && g < groups.Length; g++)
        {
            foreach (var jo in groups[g].RootNode.TreeList) if (jo.Dobj != null) { jo.Dobj = null; dropped++; }
            if (groups[g].JointAnimations != null)
                foreach (var ja in groups[g].JointAnimations.Array)
                    if (ja != null) foreach (var n in DfsAJ(ja))
                    {
                        if (n.AOBJ?.FObjDesc == null) continue;
                        var keep = n.AOBJ.FObjDesc.List.Where(t => t.JointTrackType != JointTrackType.HSD_A_J_PTCL).ToList();
                        ptcl += n.AOBJ.FObjDesc.List.Count - keep.Count;
                        for (int i = 0; i < keep.Count; i++) keep[i].Next = i + 1 < keep.Count ? keep[i + 1] : null;
                        n.AOBJ.FObjDesc = keep.Count > 0 ? keep[0] : null;
                    }
            head.ModelGroups[g] = groups[g];
        }
        // state 9 spawns particle generator 0x7531 at group 7 joint 5: send that point far below the cloud sea
        var t7 = groups[7].RootNode.TreeList;
        if (t7.Count > 5)
        {
            var par = t7.FirstOrDefault(p => p.Child != null && DfsSiblings(p.Child).Contains(t7[5]));
            t7[5].TY -= 40000f;
            Console.WriteLine($"fd: group 7 joint 5 (ptcl point) parent j{(par == null ? -1 : t7.IndexOf(par))}, moved 40000 down");
        }
        // the global fog lives on group 4; the cycle fades its colour (light blue, grey, black): push it past the far plane
        if (groups[4].Fog != null)
        {
            var fg = groups[4].Fog;
            fg.Start = fd.TryGetProperty("fog_start", out var fs0) ? fs0.GetSingle() : 60000f;
            fg.End = fd.TryGetProperty("fog_end", out var fe0) ? fe0.GetSingle() : 70000f;
            groups[4].Fog = fg;
            head.ModelGroups[4] = groups[4];
        }
        Console.WriteLine($"fd: background cycle groups 4-9 blanked ({dropped} meshes, {ptcl} particle tracks); fog {groups[4].Fog?.Start}..{groups[4].Fog?.End}");
    }

    static List<HSD_JOBJ> DfsSiblings(HSD_JOBJ first) { var l = new List<HSD_JOBJ>(); for (var c = first; c != null; c = c.Next) l.Add(c); return l; }
}
