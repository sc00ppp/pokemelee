// Pokemon Stadium as Phenac City: envelope baking, stage body, default-form floor + platforms, jumbotron placement.
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
    // Envelope (skinned) meshes baked rigid on their own joint: Colosseum palms store their vertices local to the
    // skeleton-root joint, so dropping the weights shows the bind pose there. Bone-only subtrees are pruned.
    static int BakeEnvelopes(HSD_JOBJ root, HSD_MatAnimJoint mroot, HSD_AnimJoint aroot)
    {
        var mp = new Dictionary<HSD_JOBJ, HSD_MatAnimJoint>(); if (mroot != null) PairAnim(root, mroot, mp);
        var ap = new Dictionary<HSD_JOBJ, HSD_AnimJoint>(); if (aroot != null) PairAnim(root, aroot, ap);
        int baked = 0;
        var bakedD = new HashSet<HSDStruct>();
        bool HasMesh(HSD_JOBJ j) { for (var c = j; c != null; c = c.Next) { if (c.Dobj != null || (c.Child != null && HasMesh(c.Child))) return true; } return false; }
        foreach (var j in root.TreeList)
        {
            if (j.Dobj == null) continue;
            bool any = false;
            foreach (var d in j.Dobj.List)
            {
                if (bakedD.Contains(d._s)) { any = true; continue; }   // shared with an instance copy baked earlier
                if (d.Pobj == null || d.Pobj.List.All(Rigid)) continue;
                HSD_POBJ head = null, tail = null;
                foreach (var p in d.Pobj.List)
                {
                    HSD_POBJ np = p;
                    if (!Rigid(p))
                    {
                        var attrs = p.ToGXAttributes().Select(x => x.AttributeName).Where(x => x != GXAttribName.GX_VA_NULL && x != GXAttribName.GX_VA_PNMTXIDX
                            && x != GXAttribName.GX_VA_TEX0MTXIDX && x != GXAttribName.GX_VA_TEX1MTXIDX).ToArray();
                        var tris = Triangles(p.ToDisplayList());
                        var cf = p.Flags.HasFlag(POBJ_FLAG.CULLFRONT); var cb = p.Flags.HasFlag(POBJ_FLAG.CULLBACK);
                        var gen = new POBJ_Generator { CullMode = cf && cb ? GenCullMode.FrontAndBack : cf ? GenCullMode.Front : cb ? GenCullMode.Back : GenCullMode.None,
                            VertexColorFormat = (GXCompType)GXCompTypeClr.RGBA8 };
                        np = gen.CreatePOBJsFromTriangleList(tris, attrs, null);
                        gen.SaveChanges();
                        any = true;
                    }
                    var last = np; while (last.Next != null) last = last.Next;
                    if (head == null) head = np; else tail.Next = np;
                    tail = last;
                }
                tail.Next = null;
                d.Pobj = head;
                bakedD.Add(d._s);
            }
            if (!any) continue;
            baked++;
            j.Flags &= ~(JOBJ_FLAG.SKELETON_ROOT | JOBJ_FLAG.ENVELOPE_MODEL | JOBJ_FLAG.SKELETON);
            if (j.Child != null && !HasMesh(j.Child))
            {
                j.Child = null;
                if (mp.TryGetValue(j, out var m)) m.Child = null;
                if (ap.TryGetValue(j, out var a)) a.Child = null;
            }
        }
        return baked;
    }

    static byte[] Rot90(byte[] s, int w, int h)   // w x h -> h x w, rotated clockwise
    {
        var o = new byte[w * h * 4];
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++)
            for (int c = 0; c < 4; c++) o[(x * h + (h - 1 - y)) * 4 + c] = s[(y * w + x) * 4 + c];
        return o;
    }

    static List<Vector2> Oct(float hx, float hz, float c) => new List<Vector2> {
        new(hx, hz - c), new(hx - c, hz), new(-hx + c, hz), new(-hx, hz - c),
        new(-hx, -hz + c), new(-hx + c, -hz), new(hx - c, -hz), new(hx, -hz + c) };

    static void BuildPs(JsonElement ps, SBM_Map_Head head, SBM_Map_GOBJ[] groups,
        Dictionary<string, HSDRawFile> donorFiles, Dictionary<string, Dictionary<HSDStruct, HSDStruct>> memos)
    {
        if (ps.TryGetProperty("clear_joints", out var cj))
            foreach (var e in cj.EnumerateArray())
            {
                int g = e[0].GetInt32(), j = e[1].GetInt32();
                groups[g].RootNode.TreeList[j].Dobj = null;
            }
        if (ps.TryGetProperty("group_xform", out var gx))
            foreach (var e in gx.EnumerateArray())
            {
                var jo = groups[e.GetProperty("group").GetInt32()].RootNode.TreeList[e.GetProperty("joint").GetInt32()];
                var t = e.GetProperty("t").EnumerateArray().Select(v => v.GetSingle()).ToArray();
                float s = e.TryGetProperty("s", out var sv) ? sv.GetSingle() : 1f;
                jo.TX = t[0]; jo.TY = t[1]; jo.TZ = t[2]; jo.SX = jo.SY = jo.SZ = s;
                Console.WriteLine($"ps: group {e.GetProperty("group").GetInt32()} joint {e.GetProperty("joint").GetInt32()} -> T=({t[0]},{t[1]},{t[2]}) S={s}");
            }
        if (!ps.TryGetProperty("atlas", out var at)) return;

        // atlas: [file, desc, flattened joint, dobj] -> template material + its texture
        var path = at[0].GetString();
        if (!donorFiles.TryGetValue(path, out var df)) { df = new HSDRawFile(path); donorFiles[path] = df; memos[path] = new Dictionary<HSDStruct, HSDStruct>(); }
        var droot = Copy(Scene(df).JOBJDescs[at[1].GetInt32()].RootJoint, memos[path]);
        FlattenInstances(droot, null, null);
        var tmplM = droot.TreeList[at[2].GetInt32()].Dobj.List[at[3].GetInt32()].Mobj;
        var atex = tmplM.Textures;
        int aw = atex.ImageData.Width;
        var apx = atex.GetDecodedImageData();
        var cr = ps.GetProperty("crops");
        int[] R(string k) => cr.GetProperty(k).EnumerateArray().Select(v => v.GetInt32()).ToArray();
        byte[] Crop(string k, int w, int h) { var r = R(k); return CropResize(apx, aw, r[0], r[1], r[2] - r[0], r[3] - r[1], w, h); }
        HSD_MOBJ Mat(byte[] px, int w, int h, GXWrapMode ws, GXWrapMode wt)
        {
            var t = NewTobj(atex, px, w, h, ws, wt);
            t.Flags = TOBJ_FLAGS.LIGHTMAP_DIFFUSE | TOBJ_FLAGS.COLORMAP_MODULATE;
            t.Blending = 1; t.TEV = null;
            t.GXTexGenSrc = GXTexGenSrc.GX_TG_TEX0; t.TexMapID = GXTexMapID.GX_TEXMAP0;
            var m = MobjWith(tmplM, t);
            m.RenderFlags = RENDER_MODE.VERTEX | RENDER_MODE.TEX0;
            noBrighten.Add(m._s);
            return m;
        }
        const GXWrapMode REP = GXWrapMode.REPEAT, CLA = GXWrapMode.CLAMP, MIR = GXWrapMode.MIRROR;
        var mPlaster = Mat(Seamless(Crop("plaster", 128, 64), 128, 64, true, true), 128, 64, REP, REP);
        var mFrieze = Mat(Crop("frieze", 128, 64), 128, 64, REP, CLA);
        var mCircuit = Mat(Crop("circuit", 256, 128), 256, 128, REP, CLA);
        var mSand = Mat(Crop("sand_blocks", 128, 64), 128, 64, MIR, MIR);
        var mVert = Mat(Crop("sand_vert", 64, 128), 64, 128, MIR, MIR);
        var mPale = Mat(Crop("pale_tiles", 128, 128), 128, 128, MIR, MIR);
        var mBlue = Mat(Rot90(Crop("blue_trim", 32, 128), 32, 128), 128, 32, REP, CLA);   // vertical rivet strip -> horizontal band
        var mGrate = Mat(Crop("grate", 64, 64), 64, 64, REP, REP);

        // shading baked into vertex colours (the materials are unlit like the city)
        var Ld = Vector3.Normalize(new Vector3(-0.4f, 0.85f, 0.45f));
        float shadeAmb = ps.TryGetProperty("shade_ambient", out var sa) ? sa.GetSingle() : 0.55f;
        float shadeDir = ps.TryGetProperty("shade_direct", out var sd) ? sd.GetSingle() : 0.5f;
        float Sh(Vector3 n) => Math.Min(1f, shadeAmb + shadeDir * Math.Max(0f, Vector3.Dot(Vector3.Normalize(n), Ld)));
        GX_Vertex V(Vector3 p, Vector3 n, float u, float v, float k = 1f) => new GX_Vertex
        { POS = new GXVector3(p.X, p.Y, p.Z), NRM = new GXVector3(n.X, n.Y, n.Z), CLR0 = new GXColor4(Sh(n) * k, Sh(n) * k, Sh(n) * k, 1), TEX0 = new GXVector2(u, v) };

        // side band between two outlines; u along the perimeter (units per repeat), v0..v1 top -> bottom
        List<GX_Vertex> Loft(List<Vector2> A, float ya, List<Vector2> B, float yb, float uUnit, float v0, float v1, float k = 1f, bool inward = false)
        {
            var t = new List<GX_Vertex>(); float s = 0;
            for (int i = 0; i < A.Count; i++)
            {
                int j = (i + 1) % A.Count;
                var a0 = new Vector3(A[i].X, ya, A[i].Y); var a1 = new Vector3(A[j].X, ya, A[j].Y);
                var b0 = new Vector3(B[i].X, yb, B[i].Y); var b1 = new Vector3(B[j].X, yb, B[j].Y);
                float len = Vector2.Distance(A[i], A[j]);
                int segs = Math.Max(1, (int)MathF.Round(len / uUnit * 2));
                var n = Vector3.Normalize(Vector3.Cross(b0 - a0, a1 - a0));
                var mid = (a0 + a1 + b0 + b1) / 4;
                bool outward = Vector3.Dot(new Vector3(n.X, 0, n.Z), new Vector3(mid.X, 0, mid.Z)) >= 0;
                if (outward == inward) n = -n;
                for (int q = 0; q < segs; q++)
                {
                    float f0 = q / (float)segs, f1 = (q + 1) / (float)segs;
                    var p00 = Vector3.Lerp(a0, a1, f0); var p01 = Vector3.Lerp(a0, a1, f1);
                    var p10 = Vector3.Lerp(b0, b1, f0); var p11 = Vector3.Lerp(b0, b1, f1);
                    float u0 = (s + len * f0) / uUnit, u1 = (s + len * f1) / uUnit;
                    Quad(t, V(p00, n, u0, v0, k), V(p01, n, u1, v0, k), V(p11, n, u1, v1, k), V(p10, n, u0, v1, k));
                }
                s += len;
            }
            return t;
        }
        // flat ring between outlines O and I at height y (full cap fanned from 'centre' when I is null), planar UVs
        List<GX_Vertex> Cap(List<Vector2> O, List<Vector2> I, float y, float uUnit, bool down, float k = 1f, Vector2? centre = null)
        {
            var t = new List<GX_Vertex>(); var n = down ? -Vector3.UnitY : Vector3.UnitY;
            GX_Vertex P(Vector2 p) => V(new Vector3(p.X, y, p.Y), n, p.X / uUnit, p.Y / uUnit, k);
            var c0 = centre ?? Vector2.Zero;
            for (int i = 0; i < O.Count; i++)
            {
                int j = (i + 1) % O.Count;
                if (I == null) { t.Add(P(c0)); t.Add(P(O[i])); t.Add(P(O[j])); }
                else Quad(t, P(O[i]), P(O[j]), P(I[j]), P(I[i]));
            }
            return t;
        }

        // ---- restyle vanilla meshes in place (e.g. the jumbotron frame): new Phenac material, vertex colours lifted
        //      (lum -> lo + (hi - lo) * lum / maxLum), original positions and UVs kept ----
        var mats = new Dictionary<string, HSD_MOBJ> { ["plaster"] = mPlaster, ["blue"] = mBlue, ["sand"] = mSand, ["pale"] = mPale, ["frieze"] = mFrieze };
        if (ps.TryGetProperty("restyle", out var rs))
            foreach (var e in rs.EnumerateArray())
            {
                int g = e.GetProperty("g").GetInt32(), j = e.GetProperty("j").GetInt32(), o = e.GetProperty("o").GetInt32();
                var dob = groups[g].RootNode.TreeList[j].Dobj.List[o];
                var cl = e.GetProperty("clr").EnumerateArray().Select(v => v.GetSingle()).ToArray();
                var src = dob.Pobj.List;
                float maxL = 1e-3f;
                foreach (var p in src) foreach (var v in p.ToDisplayList().Vertices) maxL = Math.Max(maxL, (v.CLR0.R + v.CLR0.G + v.CLR0.B) / 3);
                HSD_POBJ head2 = null, tail2 = null;
                foreach (var p in src)
                {
                    var attrs = p.ToGXAttributes().Select(x => x.AttributeName).Where(x => x != GXAttribName.GX_VA_NULL).ToArray();
                    var tris = Triangles(p.ToDisplayList());
                    for (int i = 0; i < tris.Count; i++)
                    {
                        var v = tris[i]; float l = (v.CLR0.R + v.CLR0.G + v.CLR0.B) / 3 / maxL;
                        float c = cl[0] + (cl[1] - cl[0]) * l;
                        v.CLR0 = new GXColor4(c, c, c, 1); tris[i] = v;
                    }
                    var cf = p.Flags.HasFlag(POBJ_FLAG.CULLFRONT); var cb = p.Flags.HasFlag(POBJ_FLAG.CULLBACK);
                    var gen = new POBJ_Generator { CullMode = cf && cb ? GenCullMode.FrontAndBack : cf ? GenCullMode.Front : cb ? GenCullMode.Back : GenCullMode.None,
                        VertexColorFormat = (GXCompType)GXCompTypeClr.RGBA8 };
                    var np = gen.CreatePOBJsFromTriangleList(tris, attrs, null); gen.SaveChanges();
                    var last = np; while (last.Next != null) last = last.Next;
                    if (head2 == null) head2 = np; else tail2.Next = np;
                    tail2 = last;
                }
                dob.Pobj = head2;
                dob.Mobj = mats[e.GetProperty("mat").GetString()];
                Console.WriteLine($"ps: restyled g{g} j{j} o{o} -> {e.GetProperty("mat").GetString()}");
            }

        // ---- the permanent stage body on group 2 (vanilla collision area 6 profile) ----
        if (ps.TryGetProperty("base", out var bs))
        {
            float colBottom = bs.TryGetProperty("column_bottom", out var cb2) ? cb2.GetSingle() : -135f;
            var O0 = Oct(87.75f, 62, 14); var P0 = Oct(70, 50, 10); var O2 = Oct(73.75f, 52, 12); var O3 = Oct(60, 44, 10);
            var C = Oct(15, 15, 8.79f);
            var parts = new List<HSD_DOBJ>
            {
                MakeDobj(mPale, Cap(O0, P0, 0f, 24f, false)),                               // top ring (outer ledges)
                MakeDobj(mBlue, Loft(P0, 0f, P0, -5.5f, 16f, 0.15f, 0.85f, 0.85f, true)),   // pit wall
                MakeDobj(mGrate, Cap(P0, null, -5.5f, 10f, false, 0.6f)),                   // pit floor (seen during transformations)
                MakeDobj(mBlue, Loft(O0, 0f, O0, -4f, 16f, 0f, 1f)),                        // rim band
                MakeDobj(mFrieze, Loft(O0, -4f, O2, -15f, 24f, 0f, 1f)),                    // bevel with the meander
                MakeDobj(mSand, Loft(O2, -15f, O2, -17.5f, 16f, 0f, 0.3f)),
                MakeDobj(mPlaster, Cap(O2, O3, -17.5f, 24f, true)),                         // under the ledges
                MakeDobj(mCircuit, Loft(O3, -17.5f, O3, -38f, 33f, 0f, 1f)),               // body
                MakeDobj(mSand, Loft(O3, -38f, C, -60f, 20f, 0f, 1f)),                     // taper to the column
                MakeDobj(mVert, Loft(C, -60f, C, colBottom, 12f, 0f, (-60f - colBottom) / 24f)),
            };
            for (int i = 0; i < parts.Count; i++) parts[i].Next = i + 1 < parts.Count ? parts[i + 1] : null;
            Append(groups[2].RootNode, new HSD_JOBJ { Flags = JOBJ_FLAG.OPA | JOBJ_FLAG.CLASSICAL_SCALING, SX = 1, SY = 1, SZ = 1, Dobj = parts[0] });
            Console.WriteLine($"ps: stage body {parts.Count} meshes on group 2 (column to {colBottom})");
        }

        // ---- piers / pylons on group 2 (e.g. the jumbotron's support on the dome crown): tapered octagonal prism,
        //      body material + a blue rivet band under the top, flat lid ----
        if (ps.TryGetProperty("piers", out var prs))
            foreach (var e in prs.EnumerateArray())
            {
                var c = e.GetProperty("center"); float cx = c[0].GetSingle(), cz = c[1].GetSingle();
                float y0 = e.GetProperty("y0").GetSingle(), y1 = e.GetProperty("y1").GetSingle();
                float w0 = e.GetProperty("w0").GetSingle() / 2, w1 = e.GetProperty("w1").GetSingle() / 2, dz = e.GetProperty("d").GetSingle() / 2;
                float k1 = w1 / w0, band = 4f;
                List<Vector2> O(float hx, float hz) => Oct(hx, hz, Math.Min(hx, hz) * 0.25f).Select(v => new Vector2(v.X + cx, v.Y + cz)).ToList();
                var bot = O(w0, dz); var mid = O(w1 + (w0 - w1) * band / (y1 - y0), dz * (k1 + (1 - k1) * band / (y1 - y0))); var top = O(w1, dz * k1);
                var body = Loft(bot, y0, mid, y1 - band, 20f, 0f, (y1 - band - y0) / 30f);
                var bandT = Loft(mid, y1 - band, top, y1, 16f, 0f, 1f);
                var lid = Cap(top, null, y1, 16f, false, 1f, new Vector2(cx, cz));
                var d0 = MakeDobj(mats[e.TryGetProperty("mat", out var pm) ? pm.GetString() : "plaster"], body);
                var d1 = MakeDobj(mBlue, bandT); var d2 = MakeDobj(mSand, lid);
                d0.Next = d1; d1.Next = d2;
                Append(groups[2].RootNode, new HSD_JOBJ { Flags = JOBJ_FLAG.OPA | JOBJ_FLAG.CLASSICAL_SCALING, SX = 1, SY = 1, SZ = 1, Dobj = d0 });
                Console.WriteLine($"ps: pier at ({cx},{cz}) y {y0}..{y1}");
            }

        // ---- default form (group 5): plaza floor on j0, white-stone platforms on j1 ----
        if (ps.TryGetProperty("top", out var tp))
        {
            int DS = tp.TryGetProperty("disc_size", out var dsz) ? dsz.GetInt32() : 256;
            var disc = new byte[DS * DS * 4];
            var pale = Crop("pale_tiles", 128, 128); var gold = Crop("sand_blocks", 128, 128);
            var cob = Crop("cobble", 128, 128); var blue = Crop("blue_plain", 32, 32);
            int rays = tp.TryGetProperty("rays", out var ry) ? ry.GetInt32() : 24;
            for (int y = 0; y < DS; y++)
                for (int x = 0; x < DS; x++)
                {
                    float dx = (x + 0.5f) / DS * 2 - 1, dy = (y + 0.5f) / DS * 2 - 1, r = MathF.Sqrt(dx * dx + dy * dy);
                    float a = MathF.Atan2(dy, dx); int sector = (int)MathF.Floor((a + MathF.PI) / MathF.Tau * rays);
                    byte[] src; int sw, sx, sy;
                    if (r < 0.2f || (r >= 0.9f && r < 0.96f)) { src = cob; sw = 128; sx = (x * 1024 / DS) % 128; sy = (y * 1024 / DS) % 128; }
                    else if (r < 0.25f || (r > 0.84f && r < 0.9f)) { src = blue; sw = 32; sx = (x * 512 / DS) % 32; sy = (y * 512 / DS) % 32; }
                    else if (r <= 0.84f) { src = (sector & 1) == 0 ? gold : pale; sw = 128; sx = (x * 1024 / DS) % 128; sy = (y * 1024 / DS) % 128; }
                    else { src = pale; sw = 128; sx = (x * 1024 / DS) % 128; sy = (y * 1024 / DS) % 128; }
                    for (int c = 0; c < 4; c++) disc[(y * DS + x) * 4 + c] = c == 3 ? (byte)255 : src[(sy * sw + sx) * 4 + c];
                }
            var mDisc = Mat(disc, DS, DS, CLA, CLA);
            var t5 = groups[5].RootNode.TreeList;
            var fl = new List<GX_Vertex>();
            const float FX = 70, FZ = 50, EX = 70, EZ = 50;   // UVs exactly 0..1: CLAMP never smears edge pixels
            const int nx = 14, nz = 10;
            for (int i = 0; i < nx; i++) for (int k = 0; k < nz; k++)
            {
                float x0 = -FX + 2 * FX * i / nx, x1 = -FX + 2 * FX * (i + 1) / nx, z0 = -FZ + 2 * FZ * k / nz, z1 = -FZ + 2 * FZ * (k + 1) / nz;
                GX_Vertex P(float x, float z) => V(new Vector3(x, 0.02f, z), Vector3.UnitY, 0.5f + x / (2 * EX), 0.5f + z / (2 * EZ));
                Quad(fl, P(x0, z0), P(x1, z0), P(x1, z1), P(x0, z1));
            }
            t5[0].Dobj = MakeDobj(mDisc, fl);
            t5[0].Flags = (t5[0].Flags & ~(JOBJ_FLAG.LIGHTING | JOBJ_FLAG.SPECULAR | JOBJ_FLAG.XLU)) | JOBJ_FLAG.OPA;
            // platforms: collision lines y=25, x 25..55 (and mirrored); j1's own translate is subtracted
            var j1 = t5[1]; float jy = j1.TY;
            var mPlatTop = tp.TryGetProperty("plat_top", out var ptop) ? Mat(Crop(ptop.GetString(), 128, 128), 128, 128, MIR, MIR) : mPale;
            var pTop = new List<GX_Vertex>(); var pSide = new List<GX_Vertex>(); var pUnder = new List<GX_Vertex>();
            foreach (var (x0, x1) in new[] { (-55f, -25f), (25f, 55f) })
            {
                float ZD = tp.TryGetProperty("plat_depth", out var pdz) ? pdz.GetSingle() : 9f, TH = tp.TryGetProperty("plat_thick", out var pth) ? pth.GetSingle() : 3.2f;
                var A = new List<Vector2> { new(x1, ZD), new(x0, ZD), new(x0, -ZD), new(x1, -ZD) };
                var c0 = new Vector2((x0 + x1) / 2, 0);
                pTop.AddRange(Cap(A, null, 25f - jy, 16f, false, 1f, c0));
                pSide.AddRange(Loft(A, 25f - jy, A, 25f - TH - jy, 16f, 0f, 1f));
                pUnder.AddRange(Cap(A, null, 25f - TH - jy, 16f, true, 0.8f, c0));
            }
            var dT = MakeDobj(mPlatTop, pTop); var dS = MakeDobj(mBlue, pSide); var dU = MakeDobj(mPlaster, pUnder);
            dT.Next = dS; dS.Next = dU;
            j1.Dobj = dT;
            j1.Flags = (j1.Flags & ~(JOBJ_FLAG.LIGHTING | JOBJ_FLAG.SPECULAR | JOBJ_FLAG.XLU)) | JOBJ_FLAG.OPA;
            groups[5].MaterialAnimations = null;     // vanilla texture anims would retarget onto the new materials
            head.ModelGroups[5] = groups[5];
            Console.WriteLine("ps: default form floor + platforms rebuilt on group 5 (mat anims cleared)");
        }
    }
}
