// colodump: Colosseum map rdat (HSD archive, root "scene_data" = HSD_SOBJ) ->
//   <out>/scene.json   joints, meshes, materials, textures, lights, fog (raw)
//   <out>/geom.bin     float32 / uint8 vertex streams referenced by scene.json
//   <out>/tex/*.png    decoded textures (RGBA)
//
// Why not the DAE route: Colosseum reuses one JOBJ struct under several parents
// (the same sub-tree drawn at several places), which made HSDRawViewer's
// ModelExporter throw "same key ... HSD_JOBJ" and drop whole JOBJDescs. Here a
// joint is processed per OCCURRENCE in the tree walk (exactly what the game's
// HSD_JObjLoadJoint does: one JObj per reference), so every copy is emitted at
// its own world transform. Material data (render mode, TObj flags/wrap/repeat/
// transform/TEV, PE blend + alpha compare, POBJ cull flags) is emitted raw so
// the Blender side can reproduce the GX look instead of a texture-only guess.
//
// Joint animations: the JOBJDesc's first AnimJoint is evaluated at --frame F
// (default 0; --frame -1 = bind pose) so animated pieces sit where the game
// starts them, not at their authoring rest pose.
//
// usage: colodump <map.rdat> <outdir> [--diag] [--frame F]
using System.IO.Compression;
using System.Numerics;
using System.Text;
using System.Text.Json;
using HSDRaw;
using HSDRaw.Common;
using HSDRaw.GX;
using HSDRaw.Common.Animation;
using HSDRaw.Tools;

static class Program
{
    static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.WriteLine("usage: colodump <map.rdat> <outdir> [--diag] [--frame F]");
            return 2;
        }
        float frame = 0;
        int fi = Array.IndexOf(args, "--frame");
        if (fi >= 0 && fi + 1 < args.Length) frame = float.Parse(args[fi + 1], System.Globalization.CultureInfo.InvariantCulture);
        var exp = new Exporter(args[0], args[1], args.Contains("--diag"), frame);
        exp.Run();
        return 0;
    }
}

class Occ
{
    public int Id;
    public int Desc;
    public int Parent;
    public HSD_JOBJ J;
    public Matrix4x4 World;      // posed (joint anim at --frame)
    public Matrix4x4 RestWorld;  // authoring rest pose
    public Matrix4x4 Bind;       // invBind * World (skin matrix for envelopes)
    public bool Hidden;      // HIDDEN on itself or an ancestor
    public int Depth;
    public bool Dup;         // struct already visited earlier (shared joint)
    public Dictionary<HSDStruct, Occ> Scope;  // non-null inside an instance copy
}

class Exporter
{
    readonly string _rdat, _out;
    readonly bool _diag;
    readonly float _frame;
    readonly List<Occ> _occ = new();
    readonly Dictionary<HSDStruct, Occ> _firstOcc = new();
    readonly Dictionary<HSDStruct, int> _matIds = new();
    readonly List<object> _materials = new();
    readonly Dictionary<(HSDStruct, HSDStruct, int, int, int), int> _texIds = new();
    readonly List<object> _textures = new();
    readonly List<object> _meshes = new();
    readonly MemoryStream _bin = new();
    readonly Dictionary<string, int> _stats = new();

    public Exporter(string rdat, string outDir, bool diag, float frame)
    {
        _rdat = rdat; _out = outDir; _diag = diag; _frame = frame;
    }

    void Stat(string k, int n = 1) { _stats[k] = _stats.GetValueOrDefault(k) + n; }

    public void Run()
    {
        Directory.CreateDirectory(_out);
        Directory.CreateDirectory(Path.Combine(_out, "tex"));
        var file = new HSDRawFile(_rdat);
        var node = file.Roots.FirstOrDefault(r => r.Name == "scene_data");
        if (node == null) throw new Exception("no scene_data root");
        var sobj = new HSD_SOBJ { _s = node.Data._s };
        var descs = sobj.JOBJDescs?.Array ?? Array.Empty<HSD_JOBJDesc>();

        var descInfo = new List<object>();
        for (int k = 0; k < descs.Length; k++)
        {
            var root = descs[k].RootJoint;
            int before = _occ.Count;
            var onPath = new HashSet<HSDStruct>();
            // the root's NEXT siblings are loaded by HSD_JObjLoadJoint too
            int sib = 0;
            HSD_AnimJoint anim = null;
            if (_frame >= 0 && descs[k].JointAnimations != null && descs[k].JointAnimations.Length > 0)
                anim = descs[k].JointAnimations[0];
            NaturalPass(root, Matrix4x4.Identity, new HashSet<HSDStruct>());
            var ar = anim;
            for (var r = root; r != null; r = r.Next, sib++, ar = ar?.Next)
                Walk(r, ar, k, -1, Matrix4x4.Identity, Matrix4x4.Identity, false, 0, onPath);
            int n = _occ.Count - before;
            int uniq = _occ.Skip(before).Select(o => o.J._s).Distinct().Count();
            descInfo.Add(new
            {
                index = k,
                occurrences = n,
                unique_joints = uniq,
                root_siblings = sib,
                has_joint_anim = descs[k].JointAnimations != null && descs[k].JointAnimations.Length > 0,
                has_mat_anim = descs[k].MaterialAnimations != null && descs[k].MaterialAnimations.Length > 0,
            });
            if (_diag) Console.WriteLine($"desc {k}: occ {n} unique {uniq} rootsiblings {sib}");
        }

        foreach (var o in _occ)
            EmitDObjs(o);

        // lights (raw)
        var lights = new List<object>();
        try
        {
            if (sobj.Lights != null)
                foreach (var l in sobj.Lights.Array)
                {
                    var lo = l.LightObject;
                    for (; lo != null; lo = lo.Next)
                    {
                        lights.Add(new
                        {
                            flags = (int)lo.Flags,
                            color = new[] { (int)lo.ColorR, lo.ColorG, lo.ColorB, lo.ColorAlpha },
                            pos = lo.Position == null ? null : new[] { lo.Position.V1, lo.Position.V2, lo.Position.V3 },
                            interest = lo.Interest == null ? null : new[] { lo.Interest.V1, lo.Interest.V2, lo.Interest.V3 },
                        });
                    }
                }
        }
        catch (Exception e) { Console.WriteLine("lights: " + e.Message); }

        // fog: dump raw words of what SOBJ+0x0C points at, and one level down
        object fog = null;
        try
        {
            var fs = sobj._s.GetReference<HSDAccessor>(0x0C)?._s;
            if (fs != null)
            {
                var sub = new Dictionary<string, string>();
                foreach (var r in fs.References)
                    sub[r.Key.ToString()] = Convert.ToHexString(r.Value.GetData());
                fog = new { raw = Convert.ToHexString(fs.GetData()), refs = sub };
            }
        }
        catch (Exception e) { Console.WriteLine("fog: " + e.Message); }

        File.WriteAllBytes(Path.Combine(_out, "geom.bin"), _bin.ToArray());
        var scene = new
        {
            source = Path.GetFullPath(_rdat),
            descs = descInfo,
            joints = _occ.Select(o => new
            {
                id = o.Id, desc = o.Desc, parent = o.Parent, depth = o.Depth,
                flags = (int)o.J.Flags, hidden = o.Hidden, dup = o.Dup,
                name = o.J.ClassName,
                world = M(o.World),
            }),
            meshes = _meshes,
            materials = _materials,
            textures = _textures,
            lights,
            fog,
            stats = _stats,
        };
        File.WriteAllText(Path.Combine(_out, "scene.json"),
            JsonSerializer.Serialize(scene, new JsonSerializerOptions { WriteIndented = false }));
        Console.WriteLine($"OK descs {descs.Length} joints {_occ.Count} meshes {_meshes.Count} mats {_materials.Count} tex {_textures.Count} bin {_bin.Length}");
        foreach (var kv in _stats.OrderBy(k => k.Key)) Console.WriteLine($"  {kv.Key}: {kv.Value}");
    }

    static float[] M(Matrix4x4 m) => new[] { m.M11, m.M12, m.M13, m.M14, m.M21, m.M22, m.M23, m.M24, m.M31, m.M32, m.M33, m.M34, m.M41, m.M42, m.M43, m.M44 };

    static Matrix4x4 InvBind(HSD_JOBJ j, Matrix4x4 restWorld)
    {
        // as HSDRawViewer LiveJObj: the desc's inverse bind for skeleton joints,
        // else the inverse of the rest-pose world matrix
        if ((j.Flags.HasFlag(JOBJ_FLAG.SKELETON) || j.Flags.HasFlag(JOBJ_FLAG.SKELETON_ROOT)) && j.InverseWorldTransform != null)
        {
            var t = j.InverseWorldTransform;
            return new Matrix4x4(t.M11, t.M21, t.M31, 0, t.M12, t.M22, t.M32, 0, t.M13, t.M23, t.M33, 0, t.M14, t.M24, t.M34, 1);
        }
        return Matrix4x4.Invert(restWorld, out var inv) ? inv : Matrix4x4.Identity;
    }

    Matrix4x4 Local(HSD_JOBJ j, HSD_AnimJoint a)
    {
        float rx = j.RX, ry = j.RY, rz = j.RZ, tx = j.TX, ty = j.TY, tz = j.TZ, sx = j.SX, sy = j.SY, sz = j.SZ;
        if (a?.AOBJ?.FObjDesc != null)
        {
            bool any = false;
            foreach (var f in a.AOBJ.FObjDesc.List)
            {
                float v;
                try { v = new FOBJ_Player(f).GetValue(_frame); } catch { Stat("anim_track_error"); continue; }
                switch (f.JointTrackType)
                {
                    case JointTrackType.HSD_A_J_ROTX: rx = v; break;
                    case JointTrackType.HSD_A_J_ROTY: ry = v; break;
                    case JointTrackType.HSD_A_J_ROTZ: rz = v; break;
                    case JointTrackType.HSD_A_J_TRAX: tx = v; break;
                    case JointTrackType.HSD_A_J_TRAY: ty = v; break;
                    case JointTrackType.HSD_A_J_TRAZ: tz = v; break;
                    case JointTrackType.HSD_A_J_SCAX: sx = v; break;
                    case JointTrackType.HSD_A_J_SCAY: sy = v; break;
                    case JointTrackType.HSD_A_J_SCAZ: sz = v; break;
                    default: Stat("anim_track_other_" + f.JointTrackType); continue;
                }
                any = true;
            }
            if (any) Stat("animated_joints");
        }
        // HSD SRT, row-vector convention: v * S * Rx * Ry * Rz * T
        return Matrix4x4.CreateScale(sx, sy, sz)
            * Matrix4x4.CreateRotationX(rx) * Matrix4x4.CreateRotationY(ry) * Matrix4x4.CreateRotationZ(rz)
            * Matrix4x4.CreateTranslation(tx, ty, tz);
    }

    // rest-pose world of every joint struct at its NATURAL place in the tree
    // (instance children not followed): the bind space its envelope vertices use
    readonly Dictionary<HSDStruct, Matrix4x4> _naturalRest = new();

    void NaturalPass(HSD_JOBJ j, Matrix4x4 parentRest, HashSet<HSDStruct> seen)
    {
        for (var c = j; c != null; c = c.Next)
        {
            if (!seen.Add(c._s)) continue;
            var w = Local(c, null) * parentRest;
            _naturalRest[c._s] = w;
            if (!c.Flags.HasFlag(JOBJ_FLAG.INSTANCE) && c.Child != null)
                NaturalPass(c.Child, w, seen);
        }
    }

    Occ FindOcc(Occ o, HSDStruct s)
    {
        // inside an instance copy, joints of the copied sub-tree resolve to the
        // copy's own occurrences; everything else to the natural occurrence
        if (o.Scope != null && o.Scope.TryGetValue(s, out var r)) return r;
        return _firstOcc.TryGetValue(s, out r) ? r : null;
    }

    void Walk(HSD_JOBJ j, HSD_AnimJoint a, int desc, int parent, Matrix4x4 parentWorld, Matrix4x4 parentRest, bool hidden, int depth, HashSet<HSDStruct> onPath, Dictionary<HSDStruct, Occ> scope = null)
    {
        if (j == null) return;
        if (onPath.Contains(j._s) || depth > 200) { Stat("cycle_skipped"); return; }
        var o = new Occ
        {
            Id = _occ.Count, Desc = desc, Parent = parent, J = j, Depth = depth,
            World = Local(j, a) * parentWorld,
            RestWorld = Local(j, null) * parentRest,
            Hidden = hidden || j.Flags.HasFlag(JOBJ_FLAG.HIDDEN),
            Dup = scope != null || _firstOcc.ContainsKey(j._s),
            Scope = scope,
        };
        o.Bind = InvBind(j, _naturalRest.TryGetValue(j._s, out var nr) ? nr : o.RestWorld) * o.World;
        if (o.Dup) Stat("shared_joint_occurrences");
        if (scope != null) scope[j._s] = o;
        else if (!_firstOcc.ContainsKey(j._s)) _firstOcc[j._s] = o;
        if (((int)j.Flags & (7 << 9)) != 0) Stat("billboard_joints");
        _occ.Add(o);
        onPath.Add(j._s);
        if (j.Flags.HasFlag(JOBJ_FLAG.INSTANCE))
        {
            // JOBJ_INSTANCE: Child points at a prototype joint (a sibling, in the
            // Colosseum maps) whose DObjs + sub-tree are drawn again with THIS
            // joint's SRT in place of the prototype's own. The prototype's Next
            // chain is NOT part of the instance (following it is what blew up into
            // tens of thousands of bogus copies and cycles).
            Stat("instance_flag_joints");
            var t = j.Child;
            int guard = 0;
            while (t != null && t.Flags.HasFlag(JOBJ_FLAG.INSTANCE) && guard++ < 8) t = t.Child;
            if (t != null && !onPath.Contains(t._s))
            {
                var sc2 = scope == null ? new Dictionary<HSDStruct, Occ>() : new Dictionary<HSDStruct, Occ>(scope);
                var v = new Occ
                {
                    Id = _occ.Count, Desc = desc, Parent = o.Id, J = t, Depth = depth + 1,
                    World = o.World,
                    RestWorld = o.RestWorld,
                    Hidden = o.Hidden || t.Flags.HasFlag(JOBJ_FLAG.HIDDEN),
                    Dup = true,
                    Scope = sc2,
                };
                // the copy stands where the prototype stood: skin space maps the
                // prototype's natural rest pose onto the instance's world
                v.Bind = InvBind(t, _naturalRest.TryGetValue(t._s, out var tr) ? tr : v.RestWorld) * v.World;
                sc2[t._s] = v;
                _occ.Add(v);
                Stat("instance_copies");
                onPath.Add(t._s);
                // children keep their own SRT relative to the instance
                for (var c = t.Child; c != null; c = c.Next)
                    Walk(c, null, desc, v.Id, v.World, v.RestWorld, v.Hidden, depth + 2, onPath, sc2);
                onPath.Remove(t._s);
            }
        }
        else
        {
            var ac = a?.Child;
            for (var c = j.Child; c != null; c = c.Next, ac = ac?.Next)
                Walk(c, ac, desc, o.Id, o.World, o.RestWorld, o.Hidden, depth + 1, onPath, scope);
        }
        onPath.Remove(j._s);
    }

    int TexId(HSD_TOBJ t)
    {
        if (t.ImageData?.ImageData == null || t.ImageData.Width <= 0 || t.ImageData.Height <= 0) return -1;
        // key on the pixel + palette BUFFERS: Colosseum points many HSD_Image
        // headers at one shared atlas buffer (same pixels -> one file)
        var key = (t.ImageData._s.GetReference<HSDAccessor>(0x00)?._s ?? t.ImageData._s,
                   t.TlutData?._s.GetReference<HSDAccessor>(0x00)?._s,
                   (int)t.ImageData.Format, (int)t.ImageData.Width, (int)t.ImageData.Height);
        if (_texIds.TryGetValue(key, out int id)) return id;
        id = _textures.Count;
        var bgra = t.GetDecodedImageData();
        int w = t.ImageData.Width, h = t.ImageData.Height;
        var rgba = new byte[w * h * 4];
        bool anyAlpha = false, anyPartial = false;
        for (int i = 0; i < w * h; i++)
        {
            rgba[i * 4 + 0] = bgra[i * 4 + 2];
            rgba[i * 4 + 1] = bgra[i * 4 + 1];
            rgba[i * 4 + 2] = bgra[i * 4 + 0];
            byte a = bgra[i * 4 + 3];
            rgba[i * 4 + 3] = a;
            if (a < 250) anyAlpha = true;
            if (a > 8 && a < 247) anyPartial = true;
        }
        string fn = $"T{id:D4}_{t.ImageData.Format}.png";
        Png.Write(Path.Combine(_out, "tex", fn), w, h, rgba);
        _textures.Add(new { file = "tex/" + fn, w, h, fmt = t.ImageData.Format.ToString(), has_alpha = anyAlpha, partial_alpha = anyPartial });
        _texIds[key] = id;
        return id;
    }

    int MatId(HSD_MOBJ m)
    {
        if (_matIds.TryGetValue(m._s, out int id)) return id;
        id = _materials.Count;
        var mat = m.Material;
        var pe = m.PEDesc;
        var texs = new List<object>();
        if (m.Textures != null)
        {
            int slot = 0;
            foreach (var t in m.Textures.List)
            {
                var tev = t.TEV;
                texs.Add(new
                {
                    slot,
                    tex = TexId(t),
                    flags = (int)t.Flags,
                    coord = (int)t.Flags & 0xF,
                    lightmap = ((int)t.Flags >> 4) & 0x1F,
                    colormap = ((int)t.Flags >> 16) & 0xF,
                    alphamap = ((int)t.Flags >> 20) & 0xF,
                    bump = t.Flags.HasFlag(TOBJ_FLAGS.BUMP),
                    texmap = (int)t.TexMapID,
                    gensrc = (int)t.GXTexGenSrc,
                    wrap_s = (int)t.WrapS, wrap_t = (int)t.WrapT,
                    repeat_s = (int)t.RepeatS, repeat_t = (int)t.RepeatT,
                    s = new[] { t.SX, t.SY, t.SZ },
                    r = new[] { t.RX, t.RY, t.RZ },
                    t = new[] { t.TX, t.TY, t.TZ },
                    blending = t.Blending,
                    mag = (int)t.MagFilter,
                    tev = tev == null ? null : new
                    {
                        color_op = (int)tev.color_op, alpha_op = (int)tev.alpha_op,
                        color_bias = (int)tev.color_bias, alpha_bias = (int)tev.alpha_bias,
                        color_scale = (int)tev.color_scale, alpha_scale = (int)tev.alpha_scale,
                        color_clamp = tev.color_clamp, alpha_clamp = tev.alpha_clamp,
                        color_in = new[] { (int)tev.color_a_in, (int)tev.color_b_in, (int)tev.color_c_in, (int)tev.color_d_in },
                        alpha_in = new[] { (int)tev.alpha_a_in, (int)tev.alpha_b_in, (int)tev.alpha_c_in, (int)tev.alpha_d_in },
                        konst = new[] { (int)tev.constant.R, tev.constant.G, tev.constant.B, tev.constantAlpha },
                        tev0 = new[] { (int)tev.tev0.R, tev.tev0.G, tev.tev0.B, tev.tev0Alpha },
                        tev1 = new[] { (int)tev.tev1.R, tev.tev1.G, tev.tev1.B, tev.tev1Alpha },
                        active = (int)tev.active,
                    },
                });
                slot++;
            }
        }
        _materials.Add(new
        {
            id,
            render = (int)m.RenderFlags,
            amb = mat == null ? null : new[] { (int)mat.AMB_R, mat.AMB_G, mat.AMB_B, mat.AMB_A },
            dif = mat == null ? null : new[] { (int)mat.DIF_R, mat.DIF_G, mat.DIF_B, mat.DIF_A },
            spc = mat == null ? null : new[] { (int)mat.SPC_R, mat.SPC_G, mat.SPC_B, mat.SPC_A },
            alpha = mat?.Alpha ?? 1f,
            shininess = mat?.Shininess ?? 0f,
            pe = pe == null ? null : new
            {
                flags = (int)pe.Flags, ref0 = (int)pe.AlphaRef0, ref1 = (int)pe.AlphaRef1,
                dst_alpha = (int)pe.DestinationAlpha, blend_mode = (int)pe.BlendMode,
                src = (int)pe.SrcFactor, dst = (int)pe.DstFactor, logic = (int)pe.BlendOp,
                depth = (int)pe.DepthFunction, comp0 = (int)pe.AlphaComp0, alpha_op = (int)pe.AlphaOp,
                comp1 = (int)pe._s.GetByte(0x0B),
            },
            textures = texs,
        });
        _matIds[m._s] = id;
        return id;
    }

    long Put(float[] a)
    {
        long off = _bin.Position;
        var b = new byte[a.Length * 4];
        Buffer.BlockCopy(a, 0, b, 0, b.Length);
        _bin.Write(b);
        return off;
    }

    long Put(byte[] a)
    {
        long off = _bin.Position;
        _bin.Write(a);
        while (_bin.Position % 4 != 0) _bin.WriteByte(0);
        return off;
    }

    static List<int> Triangulate(GXPrimitiveType t, int count, out bool unsupported)
    {
        // indices into the group's vertex run, keeping GX winding
        unsupported = false;
        var r = new List<int>();
        switch (t)
        {
            case GXPrimitiveType.Triangles:
                for (int i = 0; i + 2 < count; i += 3) { r.Add(i); r.Add(i + 1); r.Add(i + 2); }
                break;
            case GXPrimitiveType.TriangleStrip:
                for (int i = 2; i < count; i++)
                {
                    if ((i & 1) == 0) { r.Add(i - 2); r.Add(i - 1); r.Add(i); }
                    else { r.Add(i - 1); r.Add(i - 2); r.Add(i); }
                }
                break;
            case GXPrimitiveType.TriangleFan:
                for (int i = 2; i < count; i++) { r.Add(0); r.Add(i - 1); r.Add(i); }
                break;
            case GXPrimitiveType.Quads:
                for (int i = 0; i + 3 < count; i += 4) { r.Add(i); r.Add(i + 1); r.Add(i + 2); r.Add(i); r.Add(i + 2); r.Add(i + 3); }
                break;
            default:
                unsupported = true;
                break;
        }
        return r;
    }

    void EmitDObjs(Occ o)
    {
        var j = o.J;
        if (j.Dobj == null) return;
        int dIndex = 0;
        foreach (var dobj in j.Dobj.List)
        {
            int di = dIndex++;
            if (dobj.Mobj == null || dobj.Pobj == null) { Stat("dobj_without_mobj_or_pobj"); continue; }
            int mat = MatId(dobj.Mobj);
            var pos = new List<float>(); var nrm = new List<float>(); var clr = new List<float>();
            var uv = new List<float>[4] { new(), new(), new(), new() };
            var cull = new List<byte>();
            bool hasNrm = false, hasClr = false;
            bool[] hasUv = new bool[4];
            int pIndex = 0;
            foreach (var pobj in dobj.Pobj.List)
            {
                pIndex++;
                GX_DisplayList dl;
                try { dl = pobj.ToDisplayList(); }
                catch (Exception e) { Stat("pobj_decode_error"); Console.WriteLine($"pobj decode {e.Message}"); continue; }
                var attrs = pobj.ToGXAttributes().Select(a => a.AttributeName).ToHashSet();
                bool env = attrs.Contains(GXAttribName.GX_VA_PNMTXIDX);
                if (env) Stat("pobj_envelope");
                if (pobj.Flags.HasFlag(POBJ_FLAG.SHAPESET_AVERAGE)) Stat("pobj_shapeset");
                if (pobj.Flags.HasFlag(POBJ_FLAG.UNKNOWN2)) Stat("pobj_unknown2_parentbind");
                if (attrs.Contains(GXAttribName.GX_VA_NRM)) hasNrm = true;
                if (attrs.Contains(GXAttribName.GX_VA_CLR0)) hasClr = true;
                if (attrs.Contains(GXAttribName.GX_VA_CLR1)) Stat("pobj_clr1");
                for (int u = 0; u < 4; u++) if (attrs.Contains(GXAttribName.GX_VA_TEX0 + u)) hasUv[u] = true;
                byte cm = (byte)((pobj.Flags.HasFlag(POBJ_FLAG.CULLBACK) ? 1 : 0) | (pobj.Flags.HasFlag(POBJ_FLAG.CULLFRONT) ? 2 : 0));
                Stat("pobj_cull_" + cm);
                var envs = env ? pobj.EnvelopeWeights : null;
                var single = pobj.SingleBoundJOBJ;
                Matrix4x4 singleM = Matrix4x4.Identity;
                if (single != null)
                {
                    Stat("pobj_singlebind");
                    var so = FindOcc(o, single._s); if (so != null) singleM = so.World;
                }
                bool skel = j.Flags.HasFlag(JOBJ_FLAG.SKELETON) || j.Flags.HasFlag(JOBJ_FLAG.SKELETON_ROOT);

                int offset = 0;
                foreach (var prim in dl.Primitives)
                {
                    var tri = Triangulate(prim.PrimitiveType, prim.Count, out bool unsup);
                    if (unsup) Stat("prim_unsupported_" + prim.PrimitiveType);
                    for (int ti = 0; ti < tri.Count; ti++)
                    {
                        var v = dl.Vertices[offset + tri[ti]];
                        Matrix4x4 m = Matrix4x4.Identity;
                        if (env && envs != null)
                        {
                            // Envelopes are skinned in the BIND pose. Map pieces such as
                            // Phenac's palms are IK rigs (JOINT1/JOINT2/EFFECTOR) whose
                            // effector translations only make sense to the IK solver;
                            // posing their joints literally flings the fronds hundreds
                            // of units away. HSD inverse binds are relative to the
                            // skeleton root (this DObj's joint), so in the bind pose:
                            //   weight-1 vertex (stored joint-local): IWT(j)^-1 * rootWorld
                            //   blended vertex (stored root-local):   rootWorld
                            var en = envs[Math.Min(v.PNMTXIDX / 3, envs.Length - 1)];
                            m = o.World;
                            if (en.EnvelopeCount > 0 && en.GetWeightAt(0) >= 0.999f && en.JOBJs[0] != null)
                            {
                                var bj = en.JOBJs[0];
                                if (bj.InverseWorldTransform != null)
                                {
                                    var t = bj.InverseWorldTransform;
                                    var iwt = new Matrix4x4(t.M11, t.M21, t.M31, 0, t.M12, t.M22, t.M32, 0, t.M13, t.M23, t.M33, 0, t.M14, t.M24, t.M34, 1);
                                    if (Matrix4x4.Invert(iwt, out var bindLocal)) m = bindLocal * o.World;
                                }
                                else if (FindOcc(o, bj._s) is Occ eo)
                                    m = eo.World;
                            }
                        }
                        else if (!pobj.Flags.HasFlag(POBJ_FLAG.SHAPESET_AVERAGE))
                        {
                            m = o.World;
                        }
                        if (single != null) m = m * singleM;
                        var p = Vector3.Transform(new Vector3(v.POS.X, v.POS.Y, v.POS.Z), m);
                        pos.Add(p.X); pos.Add(p.Y); pos.Add(p.Z);
                        var nn = Vector3.TransformNormal(new Vector3(v.NRM.X, v.NRM.Y, v.NRM.Z), m);
                        if (nn.LengthSquared() > 1e-12f) nn = Vector3.Normalize(nn);
                        nrm.Add(nn.X); nrm.Add(nn.Y); nrm.Add(nn.Z);
                        if (attrs.Contains(GXAttribName.GX_VA_CLR0)) { clr.Add(v.CLR0.R); clr.Add(v.CLR0.G); clr.Add(v.CLR0.B); clr.Add(v.CLR0.A); }
                        else { clr.Add(1); clr.Add(1); clr.Add(1); clr.Add(1); }
                        var uvs = new[] { v.TEX0, v.TEX1, v.TEX2, v.TEX3 };
                        for (int u = 0; u < 4; u++) { uv[u].Add(uvs[u].X); uv[u].Add(uvs[u].Y); }
                        if (ti % 3 == 2) cull.Add(cm);
                    }
                    offset += prim.Count;
                }
            }
            int nv = pos.Count / 3;
            if (nv == 0) { Stat("dobj_empty"); continue; }
            var rec = new Dictionary<string, object>
            {
                ["name"] = $"d{o.Desc}_j{o.Id}_o{di}",
                ["desc"] = o.Desc,
                ["joint"] = o.Id,
                ["dobj"] = di,
                ["jflags"] = (int)j.Flags,
                ["hidden"] = o.Hidden,
                ["dup"] = o.Dup,
                ["material"] = mat,
                ["nverts"] = nv,
                ["pos"] = Put(pos.ToArray()),
                ["clr"] = hasClr ? Put(clr.ToArray()) : -1,
                ["nrm"] = hasNrm ? Put(nrm.ToArray()) : -1,
                ["cull"] = Put(cull.ToArray()),
                // billboard joints (BILLBOARD/V/H/R) face the camera in game: keep the
                // joint's world matrix so the renderer can re-orient per view
                ["bb"] = ((int)j.Flags >> 9) & 7,
                ["jworld"] = ((((int)j.Flags >> 9) & 7) != 0) ? M(o.World) : null,
            };
            for (int u = 0; u < 4; u++) rec["uv" + u] = hasUv[u] ? Put(uv[u].ToArray()) : -1;
            _meshes.Add(rec);
            Stat("tris", nv / 3);
        }
    }
}

static class Png
{
    static readonly uint[] Crc = MakeCrc();
    static uint[] MakeCrc()
    {
        var t = new uint[256];
        for (uint n = 0; n < 256; n++)
        {
            uint c = n;
            for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            t[n] = c;
        }
        return t;
    }
    static void Chunk(Stream s, string type, byte[] data)
    {
        var tb = Encoding.ASCII.GetBytes(type);
        s.Write(BE((uint)data.Length));
        s.Write(tb); s.Write(data);
        uint c = 0xFFFFFFFF;
        foreach (var b in tb) c = Crc[(c ^ b) & 0xFF] ^ (c >> 8);
        foreach (var b in data) c = Crc[(c ^ b) & 0xFF] ^ (c >> 8);
        s.Write(BE(c ^ 0xFFFFFFFF));
    }
    static byte[] BE(uint v) => new[] { (byte)(v >> 24), (byte)(v >> 16), (byte)(v >> 8), (byte)v };
    public static void Write(string path, int w, int h, byte[] rgba)
    {
        using var fs = File.Create(path);
        fs.Write(new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A });
        var ihdr = new byte[13];
        BE((uint)w).CopyTo(ihdr, 0); BE((uint)h).CopyTo(ihdr, 4);
        ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
        Chunk(fs, "IHDR", ihdr);
        var raw = new byte[(w * 4 + 1) * h];
        for (int y = 0; y < h; y++)
        {
            raw[y * (w * 4 + 1)] = 0;
            Buffer.BlockCopy(rgba, y * w * 4, raw, y * (w * 4 + 1) + 1, w * 4);
        }
        using var ms = new MemoryStream();
        using (var z = new ZLibStream(ms, CompressionLevel.Fastest, true)) z.Write(raw);
        Chunk(fs, "IDAT", ms.ToArray());
        Chunk(fs, "IEND", Array.Empty<byte>());
    }
}
