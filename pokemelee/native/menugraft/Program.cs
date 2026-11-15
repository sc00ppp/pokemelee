// menugraft: dump and replace the textures of Melee's menu files (MnSlChr / MnSlMap).
//
//   menugraft dump  <file.usd> <out_dir>
//       Writes <out_dir>/<md5>.bgra (raw BGRA, mip 0) for every distinct image reachable from the select table's
//       models and material animations, and <out_dir>/manifest.json:
//       [{md5, width, height, format, tlut, uses: ["Menu j12 d0 t0", "Menu anim j3 m0 f2", ...]}]
//   menugraft patch <file.usd> <spec.json> <out.usd>
//       spec: [{"md5": "...", "bgra": "path", "width": w, "height": h, "format": "RGB5A3"|"CMPR"|"RGBA8"|"I8"|"IA8"|...}]
//       Every TOBJ (model or texture-animation frame) whose image buffer has that md5 gets the new picture, encoded in
//       that format (no palette), at the new size. The image's size may change: the TOBJ's own UV transform is kept,
//       so a texture drawn across a quad still fills the quad.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using HSDRaw;
using HSDRaw.Common;
using HSDRaw.Common.Animation;
using HSDRaw.GX;
using HSDRaw.Tools;

static class Program
{
    class Use { public string Where; public HSD_TOBJ Tobj; public HSD_TexAnim Anim; public int Frame; }

    static HSD_SOBJ Scene(HSDRootNode r) => r.Data as HSD_SOBJ ?? new HSD_SOBJ { _s = r.Data._s };

    static string Md5(byte[] b) => Convert.ToHexString(MD5.HashData(b ?? Array.Empty<byte>())).ToLower();

    static IEnumerable<(string name, object value)> Models(HSDRawFile f)
    {
        foreach (var r in f.Roots)
        {
            if (r.Data is HSD_JOBJ j) { yield return (r.Name, j); continue; }
            if (r.Data is HSD_MatAnimJoint m) { yield return (r.Name, m); continue; }
            if (r.Data == null) continue;
            if (r.Name.EndsWith("_scene_data"))
            {
                // a scene (GmPause: ScGamPause_scene_data): each JOBJDesc's model as <root>.j<i>, its material animations .j<i>.m<k>
                var descs = Scene(r).JOBJDescs?.Array;
                if (descs == null) continue;
                for (int i = 0; i < descs.Length; i++)
                {
                    if (descs[i]?.RootJoint != null) yield return ($"{r.Name}.j{i}", descs[i].RootJoint);
                    var mats = descs[i]?.MaterialAnimations?.Array;
                    for (int k = 0; mats != null && k < mats.Length; k++)
                        if (mats[k] != null) yield return ($"{r.Name}.j{i}.m{k}", mats[k]);
                }
                continue;
            }
            foreach (var p in r.Data.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (p.PropertyType != typeof(HSD_JOBJ) && p.PropertyType != typeof(HSD_MatAnimJoint)) continue;
                object v = null;
                try { v = p.GetValue(r.Data); } catch { }
                if (v != null) yield return (p.Name, v);
            }
        }
    }

    static List<Use> Uses(HSDRawFile f)
    {
        var uses = new List<Use>();
        foreach (var (name, v) in Models(f))
        {
            if (v is HSD_JOBJ root)
            {
                var list = root.TreeList;
                for (int ji = 0; ji < list.Count; ji++)
                {
                    var dobjs = list[ji].Dobj?.List;
                    if (dobjs == null) continue;
                    for (int di = 0; di < dobjs.Count; di++)
                    {
                        var tex = dobjs[di].Mobj?.Textures?.List;
                        if (tex == null) continue;
                        for (int ti = 0; ti < tex.Count; ti++)
                            if (tex[ti].ImageData != null)
                                uses.Add(new Use { Where = $"{name} j{ji} d{di} t{ti}", Tobj = tex[ti] });
                    }
                }
            }
            else if (v is HSD_MatAnimJoint mroot)
            {
                var list = mroot.TreeList;
                for (int ji = 0; ji < list.Count; ji++)
                {
                    var mats = list[ji].MaterialAnimation?.List;
                    if (mats == null) continue;
                    for (int mi = 0; mi < mats.Count; mi++)
                    {
                        var tas = mats[mi].TextureAnimation?.List;
                        if (tas == null) continue;
                        for (int ai = 0; ai < tas.Count; ai++)
                        {
                            var ta = tas[ai];
                            var tobjs = ta.ToTOBJs();
                            for (int k = 0; k < tobjs.Length; k++)
                                uses.Add(new Use { Where = $"{name} j{ji} m{mi} a{ai} f{k}", Tobj = tobjs[k], Anim = ta, Frame = k });
                        }
                    }
                }
            }
        }
        return uses;
    }

    static int Dump(string file, string outDir)
    {
        Directory.CreateDirectory(outDir);
        var f = new HSDRawFile(file);
        var seen = new Dictionary<string, Dictionary<string, object>>();
        foreach (var u in Uses(f))
        {
            var img = u.Tobj.ImageData;
            var md5 = Md5(img.ImageData);
            if (!seen.TryGetValue(md5, out var e))
            {
                byte[] px;
                try { px = u.Tobj.GetDecodedImageData(); }
                catch (Exception ex) { Console.WriteLine($"decode failed {u.Where}: {ex.Message}"); continue; }
                File.WriteAllBytes(Path.Combine(outDir, md5 + ".bgra"), px);
                e = new Dictionary<string, object>
                {
                    ["md5"] = md5, ["width"] = (int)img.Width, ["height"] = (int)img.Height,
                    ["format"] = img.Format.ToString(), ["tlut"] = u.Tobj.TlutData?.Format.ToString(),
                    ["wrapS"] = u.Tobj.WrapS.ToString(), ["wrapT"] = u.Tobj.WrapT.ToString(),
                    ["uses"] = new List<string>(),
                };
                seen[md5] = e;
            }
            ((List<string>)e["uses"]).Add(u.Where);
        }
        File.WriteAllText(Path.Combine(outDir, "manifest.json"),
            JsonSerializer.Serialize(seen.Values.ToList(), new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"{seen.Count} images");
        return 0;
    }

    // only (optional): the uses (as dump lists them, e.g. "SingleMenuModel j41 d0 t0") that get the new picture; the
    // picture's other uses keep the old one (each replaced TOBJ gets an image of its own)
    class Spec { public string md5 { get; set; } public string bgra { get; set; } public int width { get; set; } public int height { get; set; } public string format { get; set; } public List<string> only { get; set; } }
    class Recolor { public string model { get; set; } public List<int> joints { get; set; } public List<List<JsonElement>> stops { get; set; } public float mix { get; set; } = 1f; }
    class MatEdit { public string model { get; set; } public int joint { get; set; } public int dobj { get; set; } public string diffuse { get; set; } public string ambient { get; set; } public float? alpha { get; set; }
                    public string colormap { get; set; } public bool dropTev { get; set; } public bool dropPe { get; set; } public bool dropBump { get; set; } }
    class Tint { public string model { get; set; } public string from { get; set; } public string to { get; set; } public float? alpha { get; set; } }
    // textures: also turn colour textures in place (a CI's palette, an RGB/CMPR image re-encoded at its own size and
    // format), texture-animation frames included; keepTextures: model names whose textures stay as they are
    class Hue { public List<string> models { get; set; } public float from { get; set; } public float to { get; set; } public float shift { get; set; } public float sat { get; set; } = 1f; public float minSat { get; set; } = 0.12f;
                public bool textures { get; set; } public List<string> keepTextures { get; set; } }
    // inplace: write only the changed bytes into a copy of the input file, every struct at its original offset (code
    // that finds things in a file by offset, like Slippi's in MnMaAll, keeps working); edits that would add, drop or
    // resize a struct are refused
    // move: shift joints of a select-table model (e.g. MenuModel, by TreeList index) by dx/dy, with the TRAX/TRAY keys
    // of that model's animation (<model minus Model>Animation); dobjs [[joint, dobj], ...] shift that DOBJ's vertices
    // instead (one joint holding several doors' meshes)
    // scale (dobjs only, default 1): the DOBJ's x and y are first scaled about the joint's origin, then shifted
    class Move { public string model { get; set; } public List<int> joints { get; set; } public List<List<int>> dobjs { get; set; } public float dx { get; set; } public float dy { get; set; } public float scale { get; set; } = 1f; }
    class PatchSpec { public List<Spec> images { get; set; } public List<Recolor> recolor { get; set; } public List<MatEdit> materials { get; set; } public List<Tint> tints { get; set; } public List<Hue> hue { get; set; }
                      public bool inplace { get; set; } public List<Move> moves { get; set; } public List<Quad> quads { get; set; }
                      public List<TexKey> texkeys { get; set; } public List<Append> append { get; set; }
                      public List<QuadSet> quadset { get; set; } public List<Hide> hide { get; set; } public List<Retex> retex { get; set; } }
    // quadset (in place): a 4-corner DOBJ's corners moved to the rect [x0, ytop, x1, ybottom] (joint space) and its UVs
    // to [u0, v0, u1, v1] (u0,v0 at the top-left), each vertex by the corner it was nearest (the winding stays)
    class QuadSet { public string model { get; set; } public int joint { get; set; } public int dobj { get; set; } public List<float> rect { get; set; } public List<float> uv { get; set; } }
    // hide (in place): the joints' HIDDEN flag set (their own DOBJs are not drawn)
    class Hide { public string model { get; set; } public List<int> joints { get; set; } }
    // retex (in place): a DOBJ's material takes another DOBJ's texture (the MOBJ's texture pointer is pointed at that
    // TOBJ: an existing pointer slot, so no relocation is added) - a bigger picture for a quad whose own is small
    class Retex { public string model { get; set; } public int joint { get; set; } public int dobj { get; set; } public string fromModel { get; set; } public int fromJoint { get; set; } public int fromDobj { get; set; } }
    // append (with inplace): new joints written AFTER the file's data block, so every existing struct keeps its offset
    // (the relocation, root and string tables after the data move, which the game reads from the header). Each item is
    // one new joint, hung as the next sibling of joint `after`, which must be the model's last joint in tree order (no
    // joint index moves, so the model's joint and material animations still line up); items with the same model and
    // after are chained in the order given. pos: the joint's local position. quads: drawn in order, as Quad (rect, z,
    // uv, wrap, picture, alpha); colormap REPLACE shows the picture's own colours, MODULATE tints it by diffuse; lit:
    // lit by the scene's lights like the menu frame (diffuse, ambient; the quad gets a normal facing the camera)
    class AppendQuad { public List<float> rect { get; set; } public float z { get; set; } public List<float> uv { get; set; } public string wrap { get; set; }
                       public string bgra { get; set; } public int width { get; set; } public int height { get; set; } public string format { get; set; }
                       public float alpha { get; set; } = 1f; public string colormap { get; set; } = "REPLACE"; public bool lit { get; set; }
                       public string diffuse { get; set; } = "#FFFFFF"; public string ambient { get; set; } = "#808080"; }
    class Append { public string model { get; set; } public int after { get; set; } public List<float> pos { get; set; } public List<AppendQuad> quads { get; set; } }
    // a new textured quad, appended as the last DOBJ of an existing joint (no joint index moves): rect and z in the joint's
    // local space, uv the texture corners (u0,v0 at the rect's top-left), the texture's own colours (REPLACE) by its alpha
    class Quad { public string model { get; set; } public int joint { get; set; } public List<float> rect { get; set; } public float z { get; set; }
                 public List<float> uv { get; set; } public string wrap { get; set; } public string bgra { get; set; } public int width { get; set; }
                 public int height { get; set; } public string format { get; set; } public float alpha { get; set; } = 1f; public bool first { get; set; } }
    static bool InPlace;

    static (float r, float g, float b) ParseRgb(string h) => (Convert.ToInt32(h.Substring(1, 2), 16) / 255f, Convert.ToInt32(h.Substring(3, 2), 16) / 255f, Convert.ToInt32(h.Substring(5, 2), 16) / 255f);
    static System.Drawing.Color ParseColor(string h)
    {
        int a = h.Length >= 9 ? Convert.ToInt32(h.Substring(7, 2), 16) : 255;
        return System.Drawing.Color.FromArgb(a, Convert.ToInt32(h.Substring(1, 2), 16), Convert.ToInt32(h.Substring(3, 2), 16), Convert.ToInt32(h.Substring(5, 2), 16));
    }

    // a colour whose hue lies in [from, to] degrees (and is not grey) turned by `shift` degrees, saturation scaled
    static (float, float, float) HueTurn(float r, float g, float b, Hue h)
    {
        float mx = Math.Max(r, Math.Max(g, b)), mn = Math.Min(r, Math.Min(g, b)), c = mx - mn;
        if (mx <= 0 || c / mx < h.minSat) return (r, g, b);
        float hue = mx == r ? 60 * (((g - b) / c) % 6) : mx == g ? 60 * ((b - r) / c + 2) : 60 * ((r - g) / c + 4);
        if (hue < 0) hue += 360;
        if (hue < h.from || hue > h.to) return (r, g, b);
        float s = Math.Clamp(c / mx * h.sat, 0, 1), v = mx, nh = (hue + h.shift + 360) % 360;
        float cc = v * s, x = cc * (1 - Math.Abs((nh / 60) % 2 - 1)), m = v - cc;
        var (rr, gg, bb) = nh < 60 ? (cc, x, 0f) : nh < 120 ? (x, cc, 0f) : nh < 180 ? (0f, cc, x) : nh < 240 ? (0f, x, cc) : nh < 300 ? (x, 0f, cc) : (cc, 0f, x);
        return (rr + m, gg + m, bb + m);
    }

    static System.Drawing.Color HueTurn(System.Drawing.Color c, Hue h)
    {
        var (r, g, b) = HueTurn(c.R / 255f, c.G / 255f, c.B / 255f, h);
        return System.Drawing.Color.FromArgb(c.A, (int)Math.Round(r * 255), (int)Math.Round(g * 255), (int)Math.Round(b * 255));
    }

    // every model (or the listed ones): material diffuse/ambient, TEV constants and vertex colours turned by HueTurn
    static void HueShifts(HSDRawFile f, PatchSpec spec)
    {
        var edited = new HashSet<HSDStruct>();
        foreach (var h in spec.hue ?? new List<Hue>())
        {
            int mats = 0, cols = 0;
            foreach (var (name, value) in Models(f))
            {
                if (value is not HSD_JOBJ root || (h.models != null && h.models.Count > 0 && !h.models.Contains(name))) continue;
                foreach (var j in root.TreeList)
                    foreach (var d in j.Dobj?.List ?? new List<HSD_DOBJ>())
                    {
                        var mat = d.Mobj?.Material;
                        if (mat != null && !edited.Contains(mat._s))
                        {
                            edited.Add(mat._s);
                            mat.DiffuseColor = HueTurn(mat.DiffuseColor, h);
                            mat.AmbientColor = HueTurn(mat.AmbientColor, h);
                            mats++;
                        }
                        for (var t = d.Mobj?.Textures; t != null; t = t.Next)
                            if (t.TEV != null && !edited.Contains(t.TEV._s))
                            {
                                edited.Add(t.TEV._s);
                                t.TEV.constant = HueTurn(t.TEV.constant, h);
                                t.TEV.tev0 = HueTurn(t.TEV.tev0, h);
                                t.TEV.tev1 = HueTurn(t.TEV.tev1, h);
                            }
                        foreach (var p in d.Pobj?.List ?? new List<HSD_POBJ>())
                            foreach (var at in p.ToGXAttributes())
                            {
                                if (at.AttributeName != GXAttribName.GX_VA_CLR0) continue;
                                var stops = new List<(float t, (float r, float g, float b) c)>();
                                if (at.AttributeType == GXAttribType.GX_DIRECT)
                                {
                                    if (edited.Contains(p._s)) continue;
                                    edited.Add(p._s);
                                    var dl = p.ToDisplayList();
                                    foreach (var prim in dl.Primitives)
                                        foreach (var g in prim.Indices)
                                        {
                                            if (g.Clr0 == null) continue;
                                            var (nr, ng, nb) = HueTurn(g.Clr0[0] / 255f, g.Clr0[1] / 255f, g.Clr0[2] / 255f, h);
                                            g.Clr0 = new byte[] { (byte)Math.Round(nr * 255), (byte)Math.Round(ng * 255), (byte)Math.Round(nb * 255), g.Clr0[3] };
                                            cols++;
                                        }
                                    var newDl = dl.ToBuffer();
                                    var dlBuf = p._s.GetReference<HSDAccessor>(0x10)?._s;
                                    if (InPlace)
                                    {
                                        if (dlBuf != null && newDl.Length == dlBuf.Length) dlBuf.SetData(newDl);
                                        else Console.WriteLine($"hue: display list of a direct-colour POBJ changes size ({newDl.Length} vs {dlBuf?.Length}), left as it was");
                                    }
                                    else p.DisplayListBuffer = newDl;
                                    continue;
                                }
                                if (at.Buffer == null || edited.Contains(at.Buffer._s)) continue;
                                edited.Add(at.Buffer._s);
                                cols += HueBuffer(at, h);
                            }
                    }
            }
            int texs = h.textures ? HueTextures(f, h, edited) : 0;
            Console.WriteLine($"hue {h.from}-{h.to} +{h.shift}: {mats} materials, {cols} vertex colours, {texs} textures");
        }
    }

    static (int r, int g, int b, int a) Rgb565(int v) => (((v >> 11) & 31) * 255 / 31, ((v >> 5) & 63) * 255 / 63, (v & 31) * 255 / 31, 255);
    static (int r, int g, int b, int a) Rgb5a3(int v) => (v & 0x8000) != 0
        ? (((v >> 10) & 31) * 255 / 31, ((v >> 5) & 31) * 255 / 31, (v & 31) * 255 / 31, 255)
        : (((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17, ((v >> 12) & 7) * 255 / 7);
    static int ToRgb565(int r, int g, int b) => ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
    static int ToRgb5a3(int r, int g, int b, int a) => a >= 0xE0
        ? 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
        : ((a >> 5) << 12) | ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);

    // colour textures of the hue's models turned where they lie: a CI image's palette entries, or an RGB565 / RGB5A3 /
    // RGBA8 / CMPR image decoded, turned and re-encoded into its own buffer (same size and format; only mip 0 if it
    // has mips). Intensity textures (I4, IA4, ...) take their colour from the material and are left alone.
    static int HueTextures(HSDRawFile f, Hue h, HashSet<HSDStruct> edited)
    {
        int n = 0;
        foreach (var u in Uses(f))
        {
            var model = u.Where.Split(' ')[0];
            if (h.keepTextures != null && h.keepTextures.Contains(model)) continue;
            if (h.models != null && h.models.Count > 0 && !h.models.Contains(model) && !h.models.Contains(model.Replace("_matanim_joint", "_joint"))) continue;
            var img = u.Tobj.ImageData;
            if (img == null) continue;
            var fmt = img.Format;
            if (fmt == GXTexFmt.CI4 || fmt == GXTexFmt.CI8 || fmt == GXTexFmt.CI14X2)
            {
                var tl = u.Tobj.TlutData;
                var pal = tl?._s.GetReference<HSDAccessor>(0x00)?._s;
                if (pal == null || edited.Contains(pal) || (tl.Format != GXTlutFmt.RGB565 && tl.Format != GXTlutFmt.RGB5A3)) continue;
                edited.Add(pal);
                int changed = 0;
                for (int o = 0; o + 1 < pal.Length; o += 2)
                {
                    int v = (ushort)pal.GetInt16(o);
                    var (r, g, b, a) = tl.Format == GXTlutFmt.RGB565 ? Rgb565(v) : Rgb5a3(v);
                    var (nr, ng, nb) = HueTurn(r / 255f, g / 255f, b / 255f, h);
                    int R = (int)Math.Round(Math.Clamp(nr, 0, 1) * 255), G = (int)Math.Round(Math.Clamp(ng, 0, 1) * 255), B = (int)Math.Round(Math.Clamp(nb, 0, 1) * 255);
                    if (R == r && G == g && B == b) continue;
                    pal.SetInt16(o, (short)(tl.Format == GXTlutFmt.RGB565 ? ToRgb565(R, G, B) : ToRgb5a3(R, G, B, a)));
                    changed++;
                }
                if (changed > 0) n++;
                continue;
            }
            if (fmt != GXTexFmt.RGB565 && fmt != GXTexFmt.RGB5A3 && fmt != GXTexFmt.RGBA8 && fmt != GXTexFmt.CMP) continue;
            var buf = img._s.GetReference<HSDAccessor>(0x00)?._s;
            if (buf == null || edited.Contains(buf)) continue;
            edited.Add(buf);
            byte[] px;
            try { px = new HSD_TOBJ { ImageData = img }.GetDecodedImageData(); }
            catch (Exception ex) { Console.WriteLine($"hue: decode failed {u.Where}: {ex.Message}"); continue; }
            int moved = 0;
            for (int i = 0; i + 3 < px.Length; i += 4)          // BGRA
            {
                var (nr, ng, nb) = HueTurn(px[i + 2] / 255f, px[i + 1] / 255f, px[i] / 255f, h);
                byte R = (byte)Math.Round(Math.Clamp(nr, 0, 1) * 255), G = (byte)Math.Round(Math.Clamp(ng, 0, 1) * 255), B = (byte)Math.Round(Math.Clamp(nb, 0, 1) * 255);
                if (R == px[i + 2] && G == px[i + 1] && B == px[i]) continue;
                px[i + 2] = R; px[i + 1] = G; px[i] = B;
                moved++;
            }
            if (moved == 0) continue;
            var enc = new HSD_TOBJ();
            enc.EncodeImageData(px, img.Width, img.Height, fmt, GXTlutFmt.RGB5A3);
            var bytes = enc.ImageData.ImageData;
            if (bytes.Length > buf.Length) { Console.WriteLine($"hue: {u.Where} re-encodes larger ({bytes.Length} vs {buf.Length}), left as it was"); continue; }
            var data = (byte[])buf.GetData().Clone();
            Array.Copy(bytes, data, bytes.Length);         // mip 0; any further mips keep their old colours
            buf.SetData(data);
            n++;
        }
        return n;
    }

    // In-place save: every struct HSDRaw read keeps its offset; only changed bytes are written over the input file.
    class Snap { public int Offset; public byte[] Data; public Dictionary<int, HSDStruct> Refs; }

    static Dictionary<HSDStruct, Snap> TakeSnapshot(HSDRawFile f)
    {
        var fi = typeof(HSDRawFile).GetField("_structCacheToOffset", BindingFlags.NonPublic | BindingFlags.Instance)
                 ?? throw new Exception("HSDRaw has no _structCacheToOffset: in-place patching needs the ssbmNucleus-hsdlib fork");
        var cache = (Dictionary<HSDStruct, int>)fi.GetValue(f);
        return cache.ToDictionary(kv => kv.Key, kv => new Snap { Offset = kv.Value, Data = (byte[])kv.Key.GetData().Clone(), Refs = new Dictionary<int, HSDStruct>(kv.Key.References) });
    }

    static int SaveInPlace(string inFile, Dictionary<HSDStruct, Snap> snap, string outFile)
    {
        var bytes = File.ReadAllBytes(inFile);
        var errors = new List<string>();
        int structs = 0, written = 0;
        foreach (var (s, sn) in snap)
        {
            var refs = s.References;
            if (refs.Count != sn.Refs.Count || refs.Any(kv => !sn.Refs.TryGetValue(kv.Key, out var o) || !ReferenceEquals(o, kv.Value)))
            {
                errors.Add($"struct at 0x{sn.Offset:X}: references changed");
                continue;
            }
            var now = s.GetData();
            if (now.Length != sn.Data.Length) { errors.Add($"struct at 0x{sn.Offset:X}: size {sn.Data.Length} -> {now.Length}"); continue; }
            bool any = false;
            for (int i = 0; i < now.Length; i++)
            {
                if (now[i] == sn.Data[i] || refs.ContainsKey(i - i % 4)) continue;     // never touch a pointer slot
                bytes[sn.Offset + i] = now[i];
                written++;
                any = true;
            }
            if (any) structs++;
        }
        if (errors.Count > 0)
        {
            foreach (var e in errors.Take(20)) Console.WriteLine("inplace: " + e);
            throw new Exception($"in-place patch refused: {errors.Count} structs added, dropped or resized");
        }
        File.WriteAllBytes(outFile, bytes);
        Console.WriteLine($"inplace: {written} bytes in {structs} structs changed, file size {bytes.Length} unchanged");
        return 0;
    }

    static int HueBuffer(GX_Attribute at, Hue h)
    {
        var buf = at.Buffer._s;
        int stride = at.Stride, n = buf.Length / stride, ct = (int)at.CompType;
        for (int i = 0; i < n; i++)
        {
            int o = i * stride;
            float r, g, b; int a8 = 255;
            switch (ct)
            {
                case 0: { int v = (ushort)buf.GetInt16(o); r = ((v >> 11) & 31) / 31f; g = ((v >> 5) & 63) / 63f; b = (v & 31) / 31f; break; }
                case 1: case 2: case 5: r = buf.GetByte(o) / 255f; g = buf.GetByte(o + 1) / 255f; b = buf.GetByte(o + 2) / 255f; break;
                case 3: { int v = (ushort)buf.GetInt16(o); r = ((v >> 12) & 15) / 15f; g = ((v >> 8) & 15) / 15f; b = ((v >> 4) & 15) / 15f; a8 = (v & 15) * 17; break; }
                case 4: { int v = (buf.GetByte(o) << 16) | (buf.GetByte(o + 1) << 8) | buf.GetByte(o + 2); r = ((v >> 18) & 63) / 63f; g = ((v >> 12) & 63) / 63f; b = ((v >> 6) & 63) / 63f; a8 = (v & 63) * 255 / 63; break; }
                default: continue;
            }
            var (nr, ng, nb) = HueTurn(r, g, b, h);
            int R = (int)Math.Round(Math.Clamp(nr, 0, 1) * 255), G = (int)Math.Round(Math.Clamp(ng, 0, 1) * 255), B = (int)Math.Round(Math.Clamp(nb, 0, 1) * 255);
            switch (ct)
            {
                case 0: buf.SetInt16(o, (short)(((R >> 3) << 11) | ((G >> 2) << 5) | (B >> 3))); break;
                case 1: case 2: case 5: buf.SetByte(o, (byte)R); buf.SetByte(o + 1, (byte)G); buf.SetByte(o + 2, (byte)B); break;
                case 3: buf.SetInt16(o, (short)(((R >> 4) << 12) | ((G >> 4) << 8) | ((B >> 4) << 4) | (a8 >> 4))); break;
                case 4: { int v = ((R >> 2) << 18) | ((G >> 2) << 12) | ((B >> 2) << 6) | (a8 >> 2); buf.SetByte(o, (byte)(v >> 16)); buf.SetByte(o + 1, (byte)(v >> 8)); buf.SetByte(o + 2, (byte)v); break; }
            }
        }
        return n;
    }

    // a vertex colour through a gradient map keyed by its luminance, mixed with the original by `mix`
    static (float, float, float) MapColor(float r, float g, float b, List<(float t, (float r, float g, float b) c)> stops, float mix)
    {
        float l = Math.Clamp(0.299f * r + 0.587f * g + 0.114f * b, 0, 1);
        var c = l < stops[0].t ? stops[0].c : stops[^1].c;
        for (int i = 0; i + 1 < stops.Count; i++)
            if (l >= stops[i].t && l <= stops[i + 1].t)
            {
                float k = Math.Clamp((l - stops[i].t) / Math.Max(1e-6f, stops[i + 1].t - stops[i].t), 0, 1);
                c = (stops[i].c.r + (stops[i + 1].c.r - stops[i].c.r) * k, stops[i].c.g + (stops[i + 1].c.g - stops[i].c.g) * k, stops[i].c.b + (stops[i + 1].c.b - stops[i].c.b) * k);
                break;
            }
        return (r + (c.r - r) * mix, g + (c.g - g) * mix, b + (c.b - b) * mix);
    }

    // rewrite an indexed CLR0 array in place (same layout), so display lists and envelopes stay as they are; alpha kept
    static int RecolorBuffer(GX_Attribute at, List<(float t, (float r, float g, float b) c)> stops, float mix)
    {
        var buf = at.Buffer._s;
        int stride = at.Stride, n = buf.Length / stride, ct = (int)at.CompType;
        for (int i = 0; i < n; i++)
        {
            int o = i * stride;
            float r, g, b; int a8 = 255;
            switch (ct)
            {
                case 0: { int v = (ushort)buf.GetInt16(o); r = ((v >> 11) & 31) / 31f; g = ((v >> 5) & 63) / 63f; b = (v & 31) / 31f; break; }
                case 1: case 2: r = buf.GetByte(o) / 255f; g = buf.GetByte(o + 1) / 255f; b = buf.GetByte(o + 2) / 255f; break;
                case 3: { int v = (ushort)buf.GetInt16(o); r = ((v >> 12) & 15) / 15f; g = ((v >> 8) & 15) / 15f; b = ((v >> 4) & 15) / 15f; a8 = (v & 15) * 17; break; }
                case 4: { int v = (buf.GetByte(o) << 16) | (buf.GetByte(o + 1) << 8) | buf.GetByte(o + 2); r = ((v >> 18) & 63) / 63f; g = ((v >> 12) & 63) / 63f; b = ((v >> 6) & 63) / 63f; a8 = (v & 63) * 255 / 63; break; }
                case 5: r = buf.GetByte(o) / 255f; g = buf.GetByte(o + 1) / 255f; b = buf.GetByte(o + 2) / 255f; a8 = buf.GetByte(o + 3); break;
                default: throw new Exception($"colour type {ct}");
            }
            var (nr, ng, nb) = MapColor(r, g, b, stops, mix);
            int R = (int)Math.Round(Math.Clamp(nr, 0, 1) * 255), G = (int)Math.Round(Math.Clamp(ng, 0, 1) * 255), B = (int)Math.Round(Math.Clamp(nb, 0, 1) * 255);
            switch (ct)
            {
                case 0: buf.SetInt16(o, (short)(((R >> 3) << 11) | ((G >> 2) << 5) | (B >> 3))); break;
                case 1: case 2: buf.SetByte(o, (byte)R); buf.SetByte(o + 1, (byte)G); buf.SetByte(o + 2, (byte)B); break;
                case 3: buf.SetInt16(o, (short)(((R >> 4) << 12) | ((G >> 4) << 8) | ((B >> 4) << 4) | (a8 >> 4))); break;
                case 4: { int v = ((R >> 2) << 18) | ((G >> 2) << 12) | ((B >> 2) << 6) | (a8 >> 2); buf.SetByte(o, (byte)(v >> 16)); buf.SetByte(o + 1, (byte)(v >> 8)); buf.SetByte(o + 2, (byte)v); break; }
                case 5: buf.SetByte(o, (byte)R); buf.SetByte(o + 1, (byte)G); buf.SetByte(o + 2, (byte)B); break;
            }
        }
        return n;
    }

    static void Recolors(HSDRawFile f, PatchSpec spec)
    {
        // a file can name two roots alike (MnSlMap.usd): the first one wins
        var models = Models(f).Where(m => m.value is HSD_JOBJ).GroupBy(m => m.name).ToDictionary(g => g.Key, g => (HSD_JOBJ)g.First().value);
        var edited = new HashSet<HSDStruct>();
        foreach (var rc in spec.recolor ?? new List<Recolor>())
        {
            var stops = rc.stops.Select(s => (s[0].GetSingle(), ParseRgb(s[1].GetString()))).ToList();
            var list = models[rc.model].TreeList;
            int bufs = 0, cols = 0;
            for (int ji = 0; ji < list.Count; ji++)
            {
                if (rc.joints != null && rc.joints.Count > 0 && !rc.joints.Contains(ji)) continue;
                foreach (var d in list[ji].Dobj?.List ?? new List<HSD_DOBJ>())
                {
                    if (d.Mobj == null || !d.Mobj.RenderFlags.HasFlag(RENDER_MODE.VERTEX)) continue;
                    foreach (var p in d.Pobj?.List ?? new List<HSD_POBJ>())
                        foreach (var at in p.ToGXAttributes())
                        {
                            if (at.AttributeName != GXAttribName.GX_VA_CLR0) continue;
                            if (at.AttributeType == GXAttribType.GX_DIRECT)
                            {
                                // colours inline in the display list: decode it, map each vertex's colour, write it back
                                var dl = p.ToDisplayList();
                                foreach (var prim in dl.Primitives)
                                    foreach (var g in prim.Indices)
                                    {
                                        if (g.Clr0 == null) continue;
                                        var (nr, ng, nb) = MapColor(g.Clr0[0] / 255f, g.Clr0[1] / 255f, g.Clr0[2] / 255f, stops, rc.mix);
                                        g.Clr0 = new byte[] { (byte)Math.Round(Math.Clamp(nr, 0, 1) * 255), (byte)Math.Round(Math.Clamp(ng, 0, 1) * 255), (byte)Math.Round(Math.Clamp(nb, 0, 1) * 255), g.Clr0[3] };
                                        cols++;
                                    }
                                var before = p.DisplayListBuffer.Length;
                                var buf = dl.ToBuffer();
                                if (buf.Length != before) Console.WriteLine($"  {rc.model} j{ji}: display list {before} -> {buf.Length} bytes");
                                p.DisplayListBuffer = buf;
                                bufs++;
                                continue;
                            }
                            if (at.Buffer == null || edited.Contains(at.Buffer._s)) continue;
                            edited.Add(at.Buffer._s);
                            cols += RecolorBuffer(at, stops, rc.mix);
                            bufs++;
                        }
                }
            }
            Console.WriteLine($"recolor {rc.model} {(rc.joints == null ? "all" : string.Join(",", rc.joints))}: {bufs} buffers, {cols} colours");
        }
        // every material of a model whose diffuse RGB is `from` gets `to` (and `alpha` if given)
        foreach (var t in spec.tints ?? new List<Tint>())
        {
            var from = ParseColor(t.from); var to = ParseColor(t.to); int n = 0;
            foreach (var j in models[t.model].TreeList)
                foreach (var d in j.Dobj?.List ?? new List<HSD_DOBJ>())
                {
                    var mat = d.Mobj?.Material;
                    if (mat == null) continue;
                    var c = mat.DiffuseColor;
                    if (c.R != from.R || c.G != from.G || c.B != from.B) continue;
                    mat.DiffuseColor = System.Drawing.Color.FromArgb(c.A, to.R, to.G, to.B);
                    if (t.alpha.HasValue) mat.Alpha = t.alpha.Value;
                    n++;
                }
            Console.WriteLine($"tint {t.model} {t.from} -> {t.to}: {n} materials");
        }
        foreach (var me in spec.materials ?? new List<MatEdit>())
        {
            var mat = models[me.model].TreeList[me.joint].Dobj.List[me.dobj].Mobj.Material;
            if (me.diffuse != null) mat.DiffuseColor = ParseColor(me.diffuse);
            if (me.ambient != null) mat.AmbientColor = ParseColor(me.ambient);
            if (me.alpha.HasValue) mat.Alpha = me.alpha.Value;
            var mobj = models[me.model].TreeList[me.joint].Dobj.List[me.dobj].Mobj;
            var pe = mobj.PEDesc;
            Console.WriteLine($"  rm {mobj.RenderFlags} pe {(pe != null ? $"{pe.BlendMode} src={pe.SrcFactor} dst={pe.DstFactor} flags={pe.Flags}" : "none")}");
            if (me.dropPe) mobj.PEDesc = null;   // the default blend: source over by its alpha
            var tex = mobj.Textures;
            if (tex != null)
            {
                Console.WriteLine($"  tobj flags {tex.Flags} tev {(tex.TEV == null ? "none" : "yes")}");
                if (me.colormap != null)   // e.g. REPLACE: the texture's own colour, not tinted by the material or an animated colour
                {
                    var cm = (TOBJ_FLAGS)Enum.Parse(typeof(TOBJ_FLAGS), "COLORMAP_" + me.colormap);
                    tex.Flags = (tex.Flags & ~(TOBJ_FLAGS)(0xF << 16)) | cm;
                }
                if (me.dropTev) tex.TEV = null;
                if (me.dropBump) tex.Flags &= ~TOBJ_FLAGS.BUMP;   // GmPause's stick knob: its ring picture is a bump map; a colour picture must not be
            }
            Console.WriteLine($"material {me.model} j{me.joint} d{me.dobj} set");
        }
    }

    static int Patch(string file, string specPath, string outFile)
    {
        var f = new HSDRawFile(file);
        var text = File.ReadAllText(specPath).TrimStart();
        var spec = text.StartsWith("[") ? new PatchSpec { images = JsonSerializer.Deserialize<List<Spec>>(text) } : JsonSerializer.Deserialize<PatchSpec>(text);
        var specs = spec.images ?? new List<Spec>();
        InPlace = spec.inplace;
        if (InPlace && specs.Any(s => s.only != null)) throw new Exception("an image's 'only' needs a normal patch, not inplace");
        var snap = InPlace ? TakeSnapshot(f) : null;
        int missing = InPlace && specs.Count > 0 ? ImagesInPlace(f, specs) : 0;
        Recolors(f, spec);
        HueShifts(f, spec);
        Moves(f, spec);
        Quads(f, spec);
        TexKeys(f, spec);
        QuadSets(f, spec);
        Hides(f, spec);
        if (InPlace)
        {
            int rc = SaveInPlace(file, snap, outFile);
            if (rc == 0) Retexes(f, snap, spec, outFile);
            if (rc == 0) AppendSplice(f, snap, spec, outFile);
            return rc != 0 ? rc : missing > 0 ? 2 : 0;
        }
        if (spec.append != null && spec.append.Count > 0) throw new Exception("append needs inplace");
        var byMd5 = specs.ToDictionary(s => s.md5);
        var uses = Uses(f);
        var useMd5 = uses.ToDictionary(u => u, u => Md5(u.Tobj.ImageData.ImageData));   // before any image changes: images are shared
        var hit = new Dictionary<string, int>();
        // texture-animation frames: rebuild each touched TexAnim from its TOBJs once
        var anims = new Dictionary<HSD_TexAnim, HSD_TOBJ[]>();
        var done = new HashSet<HSD_TOBJ>();
        foreach (var u in uses)
        {
            var md5 = useMd5[u];
            if (!byMd5.TryGetValue(md5, out var s)) continue;
            if (s.only != null && !s.only.Contains(u.Where)) continue;
            var px = File.ReadAllBytes(s.bgra);
            if (px.Length != s.width * s.height * 4) throw new Exception($"{s.bgra}: {px.Length} bytes for {s.width}x{s.height}");
            var fmt = Enum.Parse<GXTexFmt>(s.format);
            if (u.Anim != null)
            {
                if (!anims.ContainsKey(u.Anim)) anims[u.Anim] = u.Anim.ToTOBJs();
                var t = anims[u.Anim][u.Frame];
                t.EncodeImageData(px, s.width, s.height, fmt, GXTlutFmt.RGB5A3);
            }
            else if (!done.Contains(u.Tobj))
            {
                if (s.only != null) { u.Tobj.ImageData = null; u.Tobj.TlutData = null; }   // its own image, not the shared one
                u.Tobj.EncodeImageData(px, s.width, s.height, fmt, GXTlutFmt.RGB5A3);
                if (fmt != GXTexFmt.CI4 && fmt != GXTexFmt.CI8 && fmt != GXTexFmt.CI14X2) u.Tobj.TlutData = null;
                done.Add(u.Tobj);
            }
            hit[md5] = hit.GetValueOrDefault(md5) + 1;
        }
        foreach (var (ta, tobjs) in anims)
            ta.FromTOBJs(tobjs, false);
        f.Save(outFile);
        foreach (var s in specs)
            Console.WriteLine($"{s.md5} {(hit.TryGetValue(s.md5, out var n) ? n + " uses" : "NOT FOUND")}");
        return specs.All(s => hit.ContainsKey(s.md5)) ? 0 : 2;
    }

    // In place: each named image re-encoded at its own size and format into its own buffer (model textures and
    // texture-animation frames alike; a buffer shared by several uses is written once). Palette formats are refused.
    static int ImagesInPlace(HSDRawFile f, List<Spec> specs)
    {
        var byMd5 = specs.ToDictionary(s => s.md5);
        var uses = Uses(f);
        var useMd5 = uses.ToDictionary(u => u, u => Md5(u.Tobj.ImageData.ImageData));
        var done = new HashSet<HSDStruct>();
        var hit = new Dictionary<string, int>();
        foreach (var u in uses)
        {
            if (!byMd5.TryGetValue(useMd5[u], out var s)) continue;
            var img = u.Tobj.ImageData;
            var fmt = Enum.Parse<GXTexFmt>(s.format);
            if (img.Width != s.width || img.Height != s.height || img.Format != fmt)
                throw new Exception($"{s.md5}: in place needs {img.Width}x{img.Height} {img.Format}, the spec says {s.width}x{s.height} {s.format}");
            bool ci = fmt == GXTexFmt.CI4 || fmt == GXTexFmt.CI8 || fmt == GXTexFmt.CI14X2;
            var buf = img._s.GetReference<HSDAccessor>(0x00)?._s ?? throw new Exception($"{s.md5}: no image buffer");
            hit[s.md5] = hit.GetValueOrDefault(s.md5) + 1;
            if (!done.Add(buf)) continue;
            var px = File.ReadAllBytes(s.bgra);
            if (px.Length != s.width * s.height * 4) throw new Exception($"{s.bgra}: {px.Length} bytes for {s.width}x{s.height}");
            var enc = new HSD_TOBJ();
            if (ci)
            {
                // a palette picture: the indices into its buffer and the new palette into the TLUT's own buffer, in its
                // own TLUT format; a palette shorter than the old one is padded with its last colour
                var tl = u.Tobj.TlutData ?? throw new Exception($"{s.md5}: palette picture without a TLUT");
                var tbuf = tl._s.GetReference<HSDAccessor>(0x00)?._s ?? throw new Exception($"{s.md5}: no TLUT buffer");
                enc.EncodeImageData(px, s.width, s.height, fmt, tl.Format);
                var pal = enc.TlutData.TlutData;
                var tdata = (byte[])tbuf.GetData().Clone();
                if (pal.Length > tdata.Length) throw new Exception($"{s.md5}: palette {pal.Length} bytes, the TLUT holds {tdata.Length}");
                Array.Copy(pal, tdata, pal.Length);
                for (int k = pal.Length; k + 1 < tdata.Length; k += 2) { tdata[k] = pal[pal.Length - 2]; tdata[k + 1] = pal[pal.Length - 1]; }
                tbuf.SetData(tdata);
                Console.WriteLine($"  {s.md5}: palette {pal.Length / 2} colours into a TLUT of {tdata.Length / 2}");
            }
            else enc.EncodeImageData(px, s.width, s.height, fmt, GXTlutFmt.RGB5A3);
            var bytes = enc.ImageData.ImageData;
            if (bytes.Length > buf.Length) throw new Exception($"{s.md5}: encodes to {bytes.Length} bytes, the buffer holds {buf.Length}");
            var data = (byte[])buf.GetData().Clone();
            Array.Copy(bytes, data, bytes.Length);     // mip 0; any further mips keep the old picture
            buf.SetData(data);
        }
        int missing = 0;
        foreach (var s in specs)
        {
            Console.WriteLine($"{s.md5} {(hit.TryGetValue(s.md5, out var n) ? n + " uses (in place)" : "NOT FOUND")}");
            if (!hit.ContainsKey(s.md5)) missing++;
        }
        return missing;
    }

    // texkeys: the colour of a texture animation at one key frame (KONST / TEV0 / TEV1 tracks of every texanim of one
    // joint of a material-animation tree), written over the key's own value bytes: same encoding, same length.
    class TexKey { public string model { get; set; } public int joint { get; set; } public string track { get; set; } public float frame { get; set; } public string rgb { get; set; } }

    static int ReadPacked(byte[] b, ref int p)
    {
        int r = 0, shift = 0, x;
        do { x = b[p++]; r |= (x & 0x7F) << shift; shift += 7; } while ((x & 0x80) != 0);
        return r;
    }

    static int FmtSize(GXAnimDataFormat f) => f switch
    {
        GXAnimDataFormat.HSD_A_FRAC_FLOAT => 4,
        GXAnimDataFormat.HSD_A_FRAC_S16 or GXAnimDataFormat.HSD_A_FRAC_U16 => 2,
        _ => 1,
    };

    static int SetKeyValue(HSD_FOBJDesc fo, float frame, float value)
    {
        var bufS = fo._s.GetReference<HSDAccessor>(0x10)?._s;
        if (bufS == null) return 0;
        var b = (byte[])bufS.GetData().Clone();
        byte vf = fo._s.GetByte(0x0D), tf = fo._s.GetByte(0x0E);
        var fmt = (GXAnimDataFormat)(vf & 0xE0); float scale = 1 << (vf & 0x1F);
        var tfmt = (GXAnimDataFormat)(tf & 0xE0);
        int p = 0, hits = 0; float clock = 0;
        while (p < b.Length)
        {
            int type = ReadPacked(b, ref p), interp = type & 0x0F, num = (type >> 4) + 1;
            if (interp == 0) break;
            for (int i = 0; i < num; i++)
            {
                int at = -1, time = 0;
                switch (interp)
                {
                    case 1: case 2: case 3: at = p; p += FmtSize(fmt); time = ReadPacked(b, ref p); break;
                    case 4: at = p; p += FmtSize(fmt) + FmtSize(tfmt); time = ReadPacked(b, ref p); break;
                    case 5: p += FmtSize(tfmt); break;
                    case 6: at = p; p += FmtSize(fmt); break;
                    default: throw new Exception($"interpolation {interp}");
                }
                if (at >= 0 && Math.Abs(clock - frame) < 0.01f)
                {
                    double v = value * scale;
                    switch (fmt)   // FObj values are little-endian
                    {
                        case GXAnimDataFormat.HSD_A_FRAC_FLOAT: BitConverter.GetBytes((float)value).CopyTo(b, at); break;
                        case GXAnimDataFormat.HSD_A_FRAC_S16: BitConverter.GetBytes((short)Math.Clamp(Math.Round(v), short.MinValue, short.MaxValue)).CopyTo(b, at); break;
                        case GXAnimDataFormat.HSD_A_FRAC_U16: BitConverter.GetBytes((ushort)Math.Clamp(Math.Round(v), 0, ushort.MaxValue)).CopyTo(b, at); break;
                        case GXAnimDataFormat.HSD_A_FRAC_S8: b[at] = (byte)(sbyte)Math.Clamp(Math.Round(v), sbyte.MinValue, sbyte.MaxValue); break;
                        default: b[at] = (byte)Math.Clamp(Math.Round(v), 0, 255); break;
                    }
                    hits++;
                }
                clock += time;
            }
        }
        if (hits > 0) bufS.SetData(b);
        return hits;
    }

    static void TexKeys(HSDRawFile f, PatchSpec spec)
    {
        foreach (var tk in spec.texkeys ?? new List<TexKey>())
        {
            var m = (HSD_MatAnimJoint)Models(f).First(x => x.name == tk.model).value;
            var j = m.TreeList[tk.joint];
            var (r, g, b) = ParseRgb(tk.rgb);
            int first = tk.track switch { "KONST" => 12, "TEV0" => 16, "TEV1" => 20, _ => throw new Exception($"track {tk.track}") };
            int n = 0;
            foreach (var mat in j.MaterialAnimation?.List ?? new List<HSD_MatAnim>())
                foreach (var ta in mat.TextureAnimation?.List ?? new List<HSD_TexAnim>())
                    foreach (var fo in ta.AnimationObject?.FObjDesc?.List ?? new List<HSD_FOBJDesc>())
                    {
                        int c = fo.TrackType - first;
                        if (c < 0 || c > 2) continue;
                        n += SetKeyValue(fo, tk.frame, c == 0 ? r : c == 1 ? g : b);
                    }
            Console.WriteLine($"texkey {tk.model} j{tk.joint} {tk.track}@{tk.frame} = {tk.rgb}: {n} keys");
            if (n == 0) throw new Exception($"texkey {tk.model} j{tk.joint} {tk.track}@{tk.frame}: no key at that frame");
        }
    }

    static string Hex(System.Drawing.Color c) => $"#{c.R:X2}{c.G:X2}{c.B:X2}{c.A:X2}";

    // every DOBJ of every model: joint index, world position, render flags, colours, textures, matanim tracks
    static int Mats(string file, string model)
    {
        var f = new HSDRawFile(file);
        foreach (var (name, v) in Models(f))
        {
            if (model != "*" && name != model) continue;
            if (v is not HSD_JOBJ root) continue;
            var list = root.TreeList;
            var world = new Dictionary<HSD_JOBJ, (float x, float y, float z)>();
            void Walk(HSD_JOBJ j, (float x, float y, float z) parent)
            {
                for (var c = j; c != null; c = c.Next)
                {
                    var w = (parent.x + c.TX, parent.y + c.TY, parent.z + c.TZ);
                    world[c] = w;
                    if (c.Child != null) Walk(c.Child, w);
                }
            }
            Walk(root, (0, 0, 0));
            for (int ji = 0; ji < list.Count; ji++)
            {
                var jo = list[ji];
                var w = world.TryGetValue(jo, out var ww) ? ww : (0, 0, 0);
                var dobjs = jo.Dobj?.List;
                string head = $"{name} j{ji} flags={jo.Flags} pos=({w.Item1:0.0},{w.Item2:0.0},{w.Item3:0.0}) scale=({jo.SX:0.00},{jo.SY:0.00})" + (jo.RX != 0 || jo.RY != 0 || jo.RZ != 0 ? $" rot=({jo.RX:0.00},{jo.RY:0.00},{jo.RZ:0.00})" : "") + $" local=({jo.TX:0.0},{jo.TY:0.0},{jo.TZ:0.0})";
                if (dobjs == null) { Console.WriteLine(head + " (no dobj)"); continue; }
                Console.WriteLine(head);
                for (int di = 0; di < dobjs.Count; di++)
                {
                    var m = dobjs[di].Mobj;
                    if (m == null) continue;
                    var mat = m.Material;
                    var tex = m.Textures?.List;
                    string ts = tex == null ? "-" : string.Join(",", tex.Select(t => t.ImageData == null ? "null" : Md5(t.ImageData.ImageData).Substring(0, 6) + ":" + t.ImageData.Format + " " + t.Flags));
                    Console.WriteLine($"   d{di} rm={m.RenderFlags} dif={(mat == null ? "-" : Hex(mat.DiffuseColor))} amb={(mat == null ? "-" : Hex(mat.AmbientColor))} a={(mat == null ? 0 : mat.Alpha):0.00} tex={ts}");
                    for (var t = m.Textures; t != null; t = t.Next)
                        Console.WriteLine($"      tobj S=({t.SX:0.###},{t.SY:0.###}) T=({t.TX:0.###},{t.TY:0.###}) R=({t.RX:0.##},{t.RY:0.##},{t.RZ:0.##}) rep=({t.RepeatS},{t.RepeatT}) wrap={t.WrapS}/{t.WrapT} blend={t.Blending:0.##} src={t.GXTexGenSrc}");
                    for (var t = m.Textures; t != null; t = t.Next)
                        if (t.TEV != null)
                            Console.WriteLine($"      tev konst={Hex(t.TEV.constant)} tev0={Hex(t.TEV.tev0)} tev1={Hex(t.TEV.tev1)} active={t.TEV.active} color_op={t.TEV.color_op} a={t.TEV.color_a_in} b={t.TEV.color_b_in} c={t.TEV.color_c_in} d={t.TEV.color_d_in}");
                }
            }
        }
        return 0;
    }

    static (HSD_JOBJ root, HSD_AnimJoint anim) TableModel(HSDRawFile f, string prop)
    {
        var table = f.Roots.Select(r => r.Data).FirstOrDefault(d => d != null && d.GetType().GetProperty(prop) != null)
                    ?? throw new Exception($"no root with a {prop}");
        var root = (HSD_JOBJ)table.GetType().GetProperty(prop).GetValue(table);
        var anim = table.GetType().GetProperty(prop.Replace("Model", "Animation"))?.GetValue(table) as HSD_AnimJoint;
        return (root, anim);
    }

    static void Moves(HSDRawFile f, PatchSpec spec)
    {
        foreach (var mv in spec.moves ?? new List<Move>())
        {
            var (root, anim) = TableModel(f, mv.model);
            var list = root.TreeList;
            var alist = anim?.TreeList;
            int keys = 0;
            foreach (int i in mv.joints ?? new List<int>())
            {
                var j = list[i];
                j.TX += mv.dx;
                j.TY += mv.dy;
                if (alist == null || i >= alist.Count || alist[i].AOBJ?.FObjDesc == null) continue;
                foreach (var fo in alist[i].AOBJ.FObjDesc.List)
                {
                    var t = (JointTrackType)fo.TrackType;
                    float d = t == JointTrackType.HSD_A_J_TRAX ? mv.dx : t == JointTrackType.HSD_A_J_TRAY ? mv.dy : 0;
                    if (d == 0) continue;
                    var ks = fo.GetDecodedKeys();
                    foreach (var k in ks) k.Value += d;
                    fo.SetKeys(ks, fo.TrackType);
                    keys += ks.Count;
                }
            }
            int verts = 0;
            foreach (var jd in mv.dobjs ?? new List<List<int>>())
            {
                // the DOBJ gets its own copy of the vertex descriptor list and position buffer (a joint's DOBJs often
                // share one buffer), then its positions are shifted
                var d = list[jd[0]].Dobj.List[jd[1]];
                var copies = new Dictionary<HSDStruct, HSDStruct>();
                var shifted = new HashSet<HSDStruct>();
                foreach (var po in d.Pobj?.List ?? new List<HSD_POBJ>())
                {
                    var attrs = po._s.GetReference<HSDAccessor>(0x08)?._s;
                    if (attrs == null) continue;
                    if (!copies.TryGetValue(attrs, out var na))
                    {
                        na = new HSDStruct(attrs.GetData().ToArray());
                        foreach (var r in attrs.References) na.SetReferenceStruct(r.Key, r.Value);
                        for (int e = 0; e + 0x18 <= na.Length; e += 0x18)
                        {
                            if (na.GetInt32(e) != (int)GXAttribName.GX_VA_POS || !na.References.TryGetValue(e + 0x14, out var buf)) continue;
                            na.SetReferenceStruct(e + 0x14, new HSDStruct(buf.GetData().ToArray()) { IsBufferAligned = buf.IsBufferAligned });
                        }
                        copies[attrs] = na;
                    }
                    po._s.SetReferenceStruct(0x08, na);
                }
                foreach (var po in d.Pobj?.List ?? new List<HSD_POBJ>())
                    foreach (var at in po.ToGXAttributes())
                        if (at.AttributeName == GXAttribName.GX_VA_POS && at.Buffer != null && shifted.Add(at.Buffer._s))
                            verts += ShiftPositions(at, mv.dx, mv.dy, mv.scale);
            }
            Console.WriteLine($"move {mv.model} {(mv.joints == null ? "" : "j" + string.Join(",", mv.joints))} {(mv.dobjs == null ? "" : "dobjs " + string.Join(" ", mv.dobjs.Select(x => $"j{x[0]}d{x[1]}")))} by ({mv.dx},{mv.dy}): {keys} keys, {verts} vertices");
        }
    }

    static HSD_DOBJ quadTemplate;
    static void Quads(HSDRawFile f, PatchSpec spec)
    {
        if (spec.quads == null || spec.quads.Count == 0) return;
        var models = Models(f).Where(m => m.value is HSD_JOBJ).GroupBy(m => m.name).ToDictionary(g => g.Key, g => (HSD_JOBJ)g.First().value);
        var shared = new Dictionary<string, HSD_TOBJ>();
        foreach (var q in spec.quads)
        {
            var j = models[q.model].TreeList[q.joint];
            var mobj = new HSD_MOBJ();
            mobj.RenderFlags = RENDER_MODE.CONSTANT | RENDER_MODE.TEX0 | RENDER_MODE.NO_ZUPDATE | RENDER_MODE.XLU;
            mobj.Material = new HSD_Material();
            mobj.Material.DiffuseColor = System.Drawing.Color.White;
            mobj.Material.AmbientColor = System.Drawing.Color.FromArgb(255, 128, 128, 128);
            mobj.Material.SpecularColor = System.Drawing.Color.White;
            mobj.Material.Alpha = q.alpha;
            mobj.Material.Shininess = 50;
            var t = new HSD_TOBJ();
            t.GXTexGenSrc = GXTexGenSrc.GX_TG_TEX0;
            t.TexMapID = GXTexMapID.GX_TEXMAP0;
            t.SX = 1; t.SY = 1; t.SZ = 1;
            var wrap = q.wrap == "REPEAT" ? GXWrapMode.REPEAT : GXWrapMode.CLAMP;
            t.WrapS = wrap; t.WrapT = wrap;
            t.RepeatS = 1; t.RepeatT = 1;
            t.Flags = TOBJ_FLAGS.COORD_UV | TOBJ_FLAGS.LIGHTMAP_DIFFUSE | TOBJ_FLAGS.COLORMAP_REPLACE | TOBJ_FLAGS.ALPHAMAP_MODULATE;
            t.Blending = 1;
            t.MagFilter = GXTexFilter.GX_LINEAR;
            var px = File.ReadAllBytes(q.bgra);
            if (px.Length != q.width * q.height * 4) throw new Exception($"{q.bgra}: {px.Length} bytes for {q.width}x{q.height}");
            // Identical pictures share one image (and palette) in the file: the online CSS has little memory to spare.
            var key = Convert.ToHexString(System.Security.Cryptography.MD5.HashData(px)) + $"{q.width}x{q.height}{q.format}";
            if (shared.TryGetValue(key, out var same)) { t.ImageData = same.ImageData; t.TlutData = same.TlutData; }
            else { t.EncodeImageData(px, q.width, q.height, Enum.Parse<GXTexFmt>(q.format), GXTlutFmt.RGB5A3); shared[key] = t; }
            mobj.Textures = t;
            float x0 = q.rect[0], y0 = q.rect[1], x1 = q.rect[2], y1 = q.rect[3];   // y0 top, y1 bottom
            var uv = q.uv ?? new List<float> { 0, 0, 1, 1 };
            GX_Vertex V(float x, float y, float u, float v) => new GX_Vertex { POS = new GXVector3(x, y, q.z), TEX0 = new GXVector2(u, v) };
            var tl = V(x0, y0, uv[0], uv[1]); var tr = V(x1, y0, uv[2], uv[1]);
            var bl = V(x0, y1, uv[0], uv[3]); var br = V(x1, y1, uv[2], uv[3]);
            var tris = new List<GX_Vertex> { tl, bl, br, tl, br, tr };
            var gen = new POBJ_Generator();
            var pobj = gen.CreatePOBJsFromTriangleList(tris, new[] { GXAttribName.GX_VA_POS, GXAttribName.GX_VA_TEX0 }, null);
            gen.SaveChanges();
            for (var po = pobj; po != null; po = po.Next) { Console.WriteLine($"  pobj flags {po.Flags}"); po.Flags = 0; }
            var d = new HSD_DOBJ { Mobj = mobj, Pobj = pobj };
            if (j.Dobj == null) j.Dobj = d;
            else if (q.first) { d.Next = j.Dobj; j.Dobj = d; }
            else { var last = j.Dobj; while (last.Next != null) last = last.Next; last.Next = d; }
            Console.WriteLine($"quad {q.model} j{q.joint} ({x0},{y0})..({x1},{y1}) z {q.z} {q.width}x{q.height} {q.format}{(q.first ? " first" : "")}");
        }
    }

    static HSD_DOBJ AppendDobj(AppendQuad q)
    {
        var mobj = new HSD_MOBJ();
        mobj.RenderFlags = (q.lit ? RENDER_MODE.DIFFUSE : RENDER_MODE.CONSTANT) | RENDER_MODE.TEX0 | RENDER_MODE.NO_ZUPDATE | RENDER_MODE.XLU;
        mobj.Material = new HSD_Material();
        mobj.Material.DiffuseColor = ParseColor(q.diffuse);
        mobj.Material.AmbientColor = ParseColor(q.ambient);
        mobj.Material.SpecularColor = System.Drawing.Color.White;
        mobj.Material.Alpha = q.alpha;
        mobj.Material.Shininess = 50;
        var t = new HSD_TOBJ();
        t.GXTexGenSrc = GXTexGenSrc.GX_TG_TEX0;
        t.TexMapID = GXTexMapID.GX_TEXMAP0;
        t.SX = 1; t.SY = 1; t.SZ = 1;
        var wrap = q.wrap == "REPEAT" ? GXWrapMode.REPEAT : q.wrap == "MIRROR" ? GXWrapMode.MIRROR : GXWrapMode.CLAMP;
        t.WrapS = wrap; t.WrapT = wrap;
        t.RepeatS = 1; t.RepeatT = 1;
        var cm = (TOBJ_FLAGS)Enum.Parse(typeof(TOBJ_FLAGS), "COLORMAP_" + q.colormap);
        t.Flags = TOBJ_FLAGS.COORD_UV | TOBJ_FLAGS.LIGHTMAP_DIFFUSE | cm | TOBJ_FLAGS.ALPHAMAP_MODULATE;
        t.Blending = 1;
        t.MagFilter = GXTexFilter.GX_LINEAR;
        var px = File.ReadAllBytes(q.bgra);
        if (px.Length != q.width * q.height * 4) throw new Exception($"{q.bgra}: {px.Length} bytes for {q.width}x{q.height}");
        t.EncodeImageData(px, q.width, q.height, Enum.Parse<GXTexFmt>(q.format), GXTlutFmt.RGB5A3);
        mobj.Textures = t;
        float x0 = q.rect[0], y0 = q.rect[1], x1 = q.rect[2], y1 = q.rect[3];   // y0 top, y1 bottom
        var uv = q.uv ?? new List<float> { 0, 0, 1, 1 };
        GX_Vertex V(float x, float y, float u, float v) => new GX_Vertex { POS = new GXVector3(x, y, q.z), NRM = new GXVector3(0, 0, 1), TEX0 = new GXVector2(u, v) };
        var tl = V(x0, y0, uv[0], uv[1]); var tr = V(x1, y0, uv[2], uv[1]);
        var bl = V(x0, y1, uv[0], uv[3]); var br = V(x1, y1, uv[2], uv[3]);
        var tris = new List<GX_Vertex> { tl, bl, br, tl, br, tr };
        var gen = new POBJ_Generator();
        var attrs = q.lit ? new[] { GXAttribName.GX_VA_POS, GXAttribName.GX_VA_NRM, GXAttribName.GX_VA_TEX0 } : new[] { GXAttribName.GX_VA_POS, GXAttribName.GX_VA_TEX0 };
        var pobj = gen.CreatePOBJsFromTriangleList(tris, attrs, null);
        gen.SaveChanges();
        for (var po = pobj; po != null; po = po.Next) po.Flags = 0;
        return new HSD_DOBJ { Mobj = mobj, Pobj = pobj };
    }

    static Dictionary<string, HSD_JOBJ> JointModels(HSDRawFile f) =>
        Models(f).Where(m => m.value is HSD_JOBJ).GroupBy(m => m.name).ToDictionary(g => g.Key, g => (HSD_JOBJ)g.First().value);

    static void QuadSets(HSDRawFile f, PatchSpec spec)
    {
        if (spec.quadset == null || spec.quadset.Count == 0) return;
        var models = JointModels(f);
        foreach (var qs in spec.quadset)
        {
            var d = models[qs.model].TreeList[qs.joint].Dobj.List[qs.dobj];
            foreach (var po in d.Pobj.List)
            {
                var attrs = po.ToGXAttributes().Where(a => a.AttributeName != GXAttribName.GX_VA_NULL).ToList();
                int pi = attrs.FindIndex(a => a.AttributeName == GXAttribName.GX_VA_POS), ti = attrs.FindIndex(a => a.AttributeName == GXAttribName.GX_VA_TEX0);
                var pos = attrs[pi]; var tex = ti >= 0 ? attrs[ti] : null;
                if (pos.AttributeType != GXAttribType.GX_INDEX8 && pos.AttributeType != GXAttribType.GX_INDEX16) throw new Exception("quadset: positions are not indexed");
                if (pos.CompType != GXCompType.Float) throw new Exception("quadset: positions are not floats");
                var pb = pos.Buffer._s;
                var groups = po.ToDisplayList().Primitives.SelectMany(p => p.Indices).ToList();
                var pidx = groups.Select(g => (int)g.Indices[pi]).Distinct().ToList();
                if (pidx.Count != 4) throw new Exception($"quadset: {pidx.Count} positions, not 4");
                float cx = pidx.Average(i => pb.GetFloat(i * pos.Stride)), cy = pidx.Average(i => pb.GetFloat(i * pos.Stride + 4));
                var corner = new Dictionary<int, (bool left, bool top)>();
                foreach (var i in pidx) corner[i] = (pb.GetFloat(i * pos.Stride) < cx, pb.GetFloat(i * pos.Stride + 4) > cy);
                if (corner.Values.Distinct().Count() != 4) throw new Exception("quadset: the corners do not fall one per quadrant");
                foreach (var (i, c) in corner)
                {
                    pb.SetFloat(i * pos.Stride, c.left ? qs.rect[0] : qs.rect[2]);
                    pb.SetFloat(i * pos.Stride + 4, c.top ? qs.rect[1] : qs.rect[3]);
                }
                if (tex != null && qs.uv != null)
                {
                    var tb = tex.Buffer._s;
                    float q = 1 << tex.Scale;
                    foreach (var g in groups)
                    {
                        var c = corner[g.Indices[pi]];
                        int o = g.Indices[ti] * tex.Stride;
                        float u = c.left ? qs.uv[0] : qs.uv[2], v = c.top ? qs.uv[1] : qs.uv[3];
                        switch (tex.CompType)
                        {
                            case GXCompType.Float: tb.SetFloat(o, u); tb.SetFloat(o + 4, v); break;
                            case GXCompType.Int16: tb.SetInt16(o, (short)Math.Round(u * q)); tb.SetInt16(o + 2, (short)Math.Round(v * q)); break;
                            case GXCompType.UInt16: tb.SetInt16(o, (short)(ushort)Math.Round(u * q)); tb.SetInt16(o + 2, (short)(ushort)Math.Round(v * q)); break;
                            default: throw new Exception($"quadset: UVs as {tex.CompType}");
                        }
                    }
                }
            }
            Console.WriteLine($"quadset {qs.model} j{qs.joint} d{qs.dobj}: ({qs.rect[0]},{qs.rect[1]})..({qs.rect[2]},{qs.rect[3]})");
        }
    }

    static void Hides(HSDRawFile f, PatchSpec spec)
    {
        if (spec.hide == null) return;
        var models = JointModels(f);
        foreach (var h in spec.hide)
        {
            foreach (var j in h.joints) models[h.model].TreeList[j].Flags |= JOBJ_FLAG.HIDDEN;
            Console.WriteLine($"hide {h.model} {string.Join(",", h.joints)}");
        }
    }

    static void Retexes(HSDRawFile f, Dictionary<HSDStruct, Snap> snap, PatchSpec spec, string outFile)
    {
        if (spec.retex == null || spec.retex.Count == 0) return;
        var models = JointModels(f);
        var b = File.ReadAllBytes(outFile);
        int ds = (int)BE(b, 4), rc = (int)BE(b, 8);
        var relocs = new HashSet<uint>();
        for (int i = 0; i < rc; i++) relocs.Add(BE(b, 0x20 + ds + 4 * i));
        foreach (var r in spec.retex)
        {
            var dst = models[r.model].TreeList[r.joint].Dobj.List[r.dobj].Mobj;
            var src = models[r.fromModel].TreeList[r.fromJoint].Dobj.List[r.fromDobj].Mobj.Textures;
            int slot = snap[dst._s].Offset - 0x20 + 0x08;   // MOBJ +0x08: the texture
            if (!relocs.Contains((uint)slot) || BE(b, 0x20 + slot) == 0) throw new Exception($"retex: {r.model} j{r.joint} d{r.dobj} has no texture pointer to point elsewhere");
            uint v = (uint)(snap[src._s].Offset - 0x20);
            b[0x20 + slot] = (byte)(v >> 24); b[0x21 + slot] = (byte)(v >> 16); b[0x22 + slot] = (byte)(v >> 8); b[0x23 + slot] = (byte)v;
            Console.WriteLine($"retex {r.model} j{r.joint} d{r.dobj} <- the texture of {r.fromModel} j{r.fromJoint} d{r.fromDobj}");
        }
        File.WriteAllBytes(outFile, b);
    }

    static uint BE(byte[] b, int o) => (uint)(b[o] << 24 | b[o + 1] << 16 | b[o + 2] << 8 | b[o + 3]);
    static void PutBE(List<byte> b, uint v) { b.Add((byte)(v >> 24)); b.Add((byte)(v >> 16)); b.Add((byte)(v >> 8)); b.Add((byte)v); }

    static void AppendSplice(HSDRawFile f, Dictionary<HSDStruct, Snap> snap, PatchSpec spec, string outFile)
    {
        if (spec.append == null || spec.append.Count == 0) return;
        var models = Models(f).Where(m => m.value is HSD_JOBJ).GroupBy(m => m.name).ToDictionary(g => g.Key, g => (HSD_JOBJ)g.First().value);
        var tmp = new HSDRawFile();
        var links = new List<(int ptr, string root)>();
        int gi = 0;
        foreach (var g in spec.append.GroupBy(a => (a.model, a.after)))
        {
            var list = models[g.Key.model].TreeList;
            if (g.Key.after != list.Count - 1) throw new Exception($"append: {g.Key.model} j{g.Key.after} is not its last joint (j{list.Count - 1})");
            var after = list[g.Key.after];
            if (after.Next != null) throw new Exception($"append: {g.Key.model} j{g.Key.after} already has a next sibling");
            HSD_JOBJ first = null, prev = null;
            foreach (var a in g)
            {
                bool lit = a.quads.Any(q => q.lit);
                var j = new HSD_JOBJ { Flags = JOBJ_FLAG.CLASSICAL_SCALING | JOBJ_FLAG.XLU | (lit ? JOBJ_FLAG.LIGHTING : 0), SX = 1, SY = 1, SZ = 1 };
                if (a.pos != null) { j.TX = a.pos[0]; j.TY = a.pos[1]; j.TZ = a.pos.Count > 2 ? a.pos[2] : 0; }
                HSD_DOBJ last = null;
                foreach (var q in a.quads)
                {
                    var d = AppendDobj(q);
                    if (last == null) j.Dobj = d; else last.Next = d;
                    last = d;
                }
                if (first == null) first = j; else prev.Next = j;
                prev = j;
                Console.WriteLine($"append {g.Key.model} after j{g.Key.after}: joint at ({j.TX},{j.TY},{j.TZ}) with {a.quads.Count} quads");
            }
            var name = $"menugraft_append_{gi++}";
            tmp.Roots.Add(new HSDRootNode { Name = name, Data = first });
            if (!snap.TryGetValue(after._s, out var sn)) throw new Exception("append: the joint has no offset in the file");
            links.Add((sn.Offset - 0x20 + 0x0C, name));   // JOBJ +0x0C: next
        }
        var tmpPath = Path.Combine(Path.GetTempPath(), $"menugraft-append-{Guid.NewGuid():N}.dat");
        tmp.Save(tmpPath);
        var t = File.ReadAllBytes(tmpPath);
        File.Delete(tmpPath);
        var o = File.ReadAllBytes(outFile);
        int ds = (int)BE(o, 4), rc = (int)BE(o, 8), nroot = (int)BE(o, 12), nref = (int)BE(o, 16);
        int tds = (int)BE(t, 4), trc = (int)BE(t, 8), tnroot = (int)BE(t, 12);
        int pad = (-ds) & 31, b = ds + pad;
        var data = new byte[b + tds];
        Array.Copy(o, 0x20, data, 0, ds);
        Array.Copy(t, 0x20, data, b, tds);
        var relocs = new List<uint>();
        for (int i = 0; i < rc; i++) relocs.Add(BE(o, 0x20 + ds + 4 * i));
        var have = new HashSet<uint>(relocs);
        for (int i = 0; i < trc; i++)
        {
            uint r = BE(t, 0x20 + tds + 4 * i);
            uint v = BE(data, b + (int)r) + (uint)b;
            data[b + r] = (byte)(v >> 24); data[b + r + 1] = (byte)(v >> 16); data[b + r + 2] = (byte)(v >> 8); data[b + r + 3] = (byte)v;
            relocs.Add((uint)b + r);
        }
        // the new roots' offsets, by name (temp string table after its roots)
        int troots = 0x20 + tds + 4 * trc, tstr = troots + 8 * tnroot;
        var rootOff = new Dictionary<string, uint>();
        for (int i = 0; i < tnroot; i++)
        {
            int so = tstr + (int)BE(t, troots + 8 * i + 4);
            int e = Array.IndexOf(t, (byte)0, so);
            rootOff[System.Text.Encoding.ASCII.GetString(t, so, e - so)] = BE(t, troots + 8 * i) + (uint)b;
        }
        bool noLink = Environment.GetEnvironmentVariable("MENUGRAFT_NOLINK") == "1";   // test: the data appended, not hung
        foreach (var (ptr, root) in noLink ? new List<(int, string)>() : links)
        {
            if (BE(data, ptr) != 0 || have.Contains((uint)ptr)) throw new Exception($"append: pointer slot 0x{ptr:X} is not empty");
            uint v = rootOff[root];
            data[ptr] = (byte)(v >> 24); data[ptr + 1] = (byte)(v >> 16); data[ptr + 2] = (byte)(v >> 8); data[ptr + 3] = (byte)v;
            relocs.Add((uint)ptr);
        }
        var outb = new List<byte>();
        var tables = new byte[o.Length - (0x20 + ds + 4 * rc)];   // roots, refs, strings: copied as they are
        Array.Copy(o, 0x20 + ds + 4 * rc, tables, 0, tables.Length);
        int size = 0x20 + data.Length + 4 * relocs.Count + tables.Length;
        PutBE(outb, (uint)size); PutBE(outb, (uint)data.Length); PutBE(outb, (uint)relocs.Count); PutBE(outb, (uint)nroot); PutBE(outb, (uint)nref);
        for (int i = 20; i < 0x20; i++) outb.Add(o[i]);
        outb.AddRange(data);
        foreach (var r in relocs) PutBE(outb, r);
        outb.AddRange(tables);
        File.WriteAllBytes(outFile, outb.ToArray());
        Console.WriteLine($"append: {tds} bytes of new structs after the data at 0x{0x20 + b:X}, {trc + links.Count} relocations added, file {o.Length} -> {size} bytes");
    }

    static int ShiftPositions(GX_Attribute at, float dx, float dy, float k = 1f)
    {
        var buf = at.Buffer._s;
        int stride = at.Stride, n = buf.Length / stride, sz = at.CompType switch { GXCompType.Float => 4, GXCompType.Int16 or GXCompType.UInt16 => 2, _ => 1 };
        float q = 1 << at.Scale;
        for (int i = 0; i < n; i++)
            for (int c = 0; c < 2; c++)
            {
                int o = i * stride + c * sz;
                float d = c == 0 ? dx : dy;
                switch (at.CompType)
                {
                    case GXCompType.Float: buf.SetFloat(o, buf.GetFloat(o) * k + d); break;
                    case GXCompType.Int16: buf.SetInt16(o, (short)Math.Round(buf.GetInt16(o) * k + d * q)); break;
                    case GXCompType.UInt16: buf.SetInt16(o, (short)(ushort)Math.Round((ushort)buf.GetInt16(o) * k + d * q)); break;
                    case GXCompType.Int8: buf.SetByte(o, (byte)(sbyte)Math.Round((sbyte)buf.GetByte(o) * k + d * q)); break;
                    default: buf.SetByte(o, (byte)Math.Round(buf.GetByte(o) * k + d * q)); break;
                }
            }
        return n;
    }

    // A select table's model (SBM_SelectChrDataTable property, e.g. MenuModel) as a tree: depth, parent, world rest
    // position, the world box of its own vertices (rigid joints only), and the ranges of its animated translations from
    // every animation of that model (<prop>Animation).
    static int Tree(string file, string prop)
    {
        var f = new HSDRawFile(file);
        HSD_JOBJ root; HSD_AnimJoint anim;
        var plain = f.Roots.FirstOrDefault(r => r.Name == prop && r.Data is HSD_JOBJ);
        if (plain != null)
        {
            // a plain root (MnMaAll: MenMainBack_Top_joint), its animation the root named ..._animjoint
            root = (HSD_JOBJ)plain.Data;
            anim = f.Roots.FirstOrDefault(r => r.Name == prop.Replace("_joint", "_animjoint"))?.Data as HSD_AnimJoint;
            if (anim == null)
            {
                var ar = f.Roots.FirstOrDefault(r => r.Name == prop.Replace("_joint", "_animjoint"));
                if (ar != null) anim = new HSD_AnimJoint { _s = ar.Data._s };
            }
        }
        else if (prop.Contains("_scene_data.j"))
        {
            // <scene root>.j<i>: that JOBJDesc's model and its first joint animation
            var cut = prop.LastIndexOf(".j");
            var sr = f.Roots.First(r => r.Name == prop.Substring(0, cut));
            var desc = Scene(sr).JOBJDescs.Array[int.Parse(prop.Substring(cut + 2))];
            root = desc.RootJoint;
            anim = desc.JointAnimations?.Array?.FirstOrDefault();
        }
        else
        {
            var table = f.Roots.Select(r => r.Data).FirstOrDefault(d => d != null && d.GetType().GetProperty(prop) != null)
                        ?? throw new Exception($"no root with a {prop}");
            root = (HSD_JOBJ)table.GetType().GetProperty(prop).GetValue(table);
            anim = table.GetType().GetProperty(prop.Replace("Model", "Animation"))?.GetValue(table) as HSD_AnimJoint;
        }
        var list = root.TreeList;
        var alist = anim?.TreeList;
        var index = list.Select((j, i) => (j, i)).ToDictionary(t => t.j._s, t => t.i);
        void Walk(HSD_JOBJ j, int depth, int parent, (float x, float y) p)
        {
            for (var c = j; c != null; c = c.Next)
            {
                int i = index[c._s];
                var w = (x: p.x + c.TX, y: p.y + c.TY);
                string box = "";
                float x0 = float.MaxValue, y0 = float.MaxValue, x1 = float.MinValue, y1 = float.MinValue;
                foreach (var d in c.Dobj?.List ?? new List<HSD_DOBJ>())
                    foreach (var po in d.Pobj?.List ?? new List<HSD_POBJ>())
                    {
                        try
                        {
                            foreach (var v in GX_VertexAccessor.GetDecodedVertices(po.ToDisplayList(), po))
                            {
                                float vx = w.x + v.POS.X * c.SX, vy = w.y + v.POS.Y * c.SY;
                                x0 = Math.Min(x0, vx); x1 = Math.Max(x1, vx); y0 = Math.Min(y0, vy); y1 = Math.Max(y1, vy);
                            }
                        }
                        catch { }
                    }
                if (x0 <= x1) box = $" box x {x0:0.0}..{x1:0.0} y {y0:0.0}..{y1:0.0}";
                string tr = "";
                if (alist != null && i < alist.Count && alist[i].AOBJ?.FObjDesc != null)
                    foreach (var fo in alist[i].AOBJ.FObjDesc.List)
                    {
                        var t = (JointTrackType)fo.TrackType;
                        if (t != JointTrackType.HSD_A_J_TRAX && t != JointTrackType.HSD_A_J_TRAY && t != JointTrackType.HSD_A_J_SCAY && t != JointTrackType.HSD_A_J_SCAX) continue;
                        var ks = fo.GetDecodedKeys();
                        tr += $" {t.ToString().Substring(8)}[{ks.Min(k => k.Value):0.0}..{ks.Max(k => k.Value):0.0} n{ks.Count}]";
                    }
                Console.WriteLine($"{new string(' ', depth * 2)}j{i} p{parent} at ({w.x:0.0},{w.y:0.0}) local ({c.TX:0.0},{c.TY:0.0}) s({c.SX:0.00},{c.SY:0.00}){box}{tr}");
                var dl = c.Dobj?.List ?? new List<HSD_DOBJ>();
                for (int di = 0; dl.Count > 1 && di < dl.Count; di++)
                {
                    float a0 = float.MaxValue, b0 = float.MaxValue, a1 = float.MinValue, b1 = float.MinValue;
                    var bufs = new List<string>();
                    foreach (var po in dl[di].Pobj?.List ?? new List<HSD_POBJ>())
                    {
                        foreach (var at in po.ToGXAttributes())
                            if (at.AttributeName == GXAttribName.GX_VA_POS && at.Buffer != null) bufs.Add($"{at.Buffer._s.GetHashCode():x}:{at.CompType}/{at.Scale}");
                        try
                        {
                            foreach (var v in GX_VertexAccessor.GetDecodedVertices(po.ToDisplayList(), po))
                            { float vx = w.x + v.POS.X, vy = w.y + v.POS.Y; a0 = Math.Min(a0, vx); a1 = Math.Max(a1, vx); b0 = Math.Min(b0, vy); b1 = Math.Max(b1, vy); }
                        }
                        catch { }
                    }
                    Console.WriteLine($"{new string(' ', depth * 2 + 4)}d{di} box x {a0:0.0}..{a1:0.0} y {b0:0.0}..{b1:0.0} pos {string.Join(",", bufs)}");
                }
                if (c.Child != null) Walk(c.Child, depth + 1, i, w);
            }
        }
        Walk(root, 0, -1, (0, 0));
        return 0;
    }

    // the animated material tracks (colour, alpha) of one joint of a material-animation tree
    static int MatAnim(string file, string model, int joint)
    {
        var f = new HSDRawFile(file);
        var m = (HSD_MatAnimJoint)Models(f).First(x => x.name == model).value;
        var j = m.TreeList[joint];
        var mats = j.MaterialAnimation?.List ?? new List<HSD_MatAnim>();
        for (int mi = 0; mi < mats.Count; mi++)
        {
            var ao = mats[mi].AnimationObject;
            Console.WriteLine($"m{mi} aobj {(ao == null ? "none" : $"end={ao.EndFrame} flags={ao.Flags}")} texanims={mats[mi].TextureAnimation?.List?.Count ?? 0}");
            foreach (var ta in mats[mi].TextureAnimation?.List ?? new List<HSD_TexAnim>())
            {
                var tobjs = ta.ToTOBJs();
                Console.WriteLine($"   texanim map={ta.GXTexMapID} images={tobjs.Length} [{string.Join(",", tobjs.Select(t => t.ImageData == null ? "-" : Md5(t.ImageData.ImageData).Substring(0, 6)))}]");
                foreach (var fo in ta.AnimationObject?.FObjDesc?.List ?? new List<HSD_FOBJDesc>())
                {
                    var keys = fo.GetDecodedKeys();
                    Console.WriteLine($"      ttrack {fo.TrackType} ({(TexTrackType)fo.TrackType}) keys: " +
                        string.Join(" ", keys.Take(16).Select(k => $"{k.Frame}:{k.Value:0.###}")));
                }
            }
            if (ao?.FObjDesc == null) continue;
            foreach (var fo in ao.FObjDesc.List)
            {
                var keys = fo.GetDecodedKeys();
                Console.WriteLine($"   track {fo.TrackType} ({(MatTrackType)fo.TrackType}) keys: " +
                    string.Join(" ", keys.Take(12).Select(k => $"{k.Frame}:{k.Value:0.###}")));
            }
        }
        return 0;
    }

    static int Pobjs(string file, string model, int joint)
    {
        var f = new HSDRawFile(file);
        var m = Models(f).Where(x => x.value is HSD_JOBJ).First(x => x.name == model).value as HSD_JOBJ;
        int di = 0;
        foreach (var d in m.TreeList[joint].Dobj?.List ?? new List<HSD_DOBJ>())
        {
            foreach (var po in d.Pobj?.List ?? new List<HSD_POBJ>())
            {
                Console.WriteLine($"d{di} pobj flags {po.Flags} attrs {string.Join(",", po.ToGXAttributes().Select(at => $"{at.AttributeName}:{at.AttributeType}:{at.CompType}"))} prims {string.Join(",", po.ToDisplayList().Primitives.Select(pr => pr.PrimitiveType + "x" + pr.Indices.Length))}");
                try
                {
                    var cols = GX_VertexAccessor.GetDecodedVertices(po.ToDisplayList(), po)
                        .Select(v => $"#{(int)Math.Round(v.CLR0.R * 255):X2}{(int)Math.Round(v.CLR0.G * 255):X2}{(int)Math.Round(v.CLR0.B * 255):X2}{(int)Math.Round(v.CLR0.A * 255):X2}")
                        .GroupBy(c => c).OrderByDescending(g => g.Count()).Take(12).Select(g => $"{g.Key}x{g.Count()}");
                    Console.WriteLine($"   clr0 {string.Join(" ", cols)}");
                }
                catch (Exception ex) { Console.WriteLine($"   clr0 ? {ex.Message}"); }
            }
            di++;
        }
        return 0;
    }

    static int Verts(string file, string model, int joint)
    {
        var f = new HSDRawFile(file);
        var m = Models(f).Where(x => x.value is HSD_JOBJ).First(x => x.name == model).value as HSD_JOBJ;
        int di = 0;
        foreach (var d in m.TreeList[joint].Dobj?.List ?? new List<HSD_DOBJ>())
        {
            int pi = 0;
            foreach (var po in d.Pobj?.List ?? new List<HSD_POBJ>())
            {
                var vs = GX_VertexAccessor.GetDecodedVertices(po.ToDisplayList(), po);
                var uniq = vs.Select(v => $"pos=({v.POS.X:0.00},{v.POS.Y:0.00},{v.POS.Z:0.00}) uv=({v.TEX0.X:0.000},{v.TEX0.Y:0.000}) rgba=({(int)Math.Round(v.CLR0.R * 255)},{(int)Math.Round(v.CLR0.G * 255)},{(int)Math.Round(v.CLR0.B * 255)},{(int)Math.Round(v.CLR0.A * 255)})")
                    .Distinct().ToList();
                Console.WriteLine($"d{di} p{pi} {vs.Length} verts, {uniq.Count} unique");
                foreach (var u in uniq) Console.WriteLine("   " + u);
                pi++;
            }
            di++;
        }
        return 0;
    }

    static int Main(string[] a)
    {
        if (a.Length >= 4 && a[0] == "verts") return Verts(a[1], a[2], int.Parse(a[3]));
        if (a.Length >= 4 && a[0] == "pobjs") return Pobjs(a[1], a[2], int.Parse(a[3]));
        if (a.Length >= 4 && a[0] == "matanim") return MatAnim(a[1], a[2], int.Parse(a[3]));
        if (a.Length >= 3 && a[0] == "mats") return Mats(a[1], a[2]);
        if (a.Length >= 3 && a[0] == "tree") return Tree(a[1], a[2]);
        if (a.Length >= 3 && a[0] == "dump") return Dump(a[1], a[2]);
        if (a.Length >= 4 && a[0] == "patch") return Patch(a[1], a[2], a[3]);
        Console.WriteLine("menugraft dump <file> <out_dir> | patch <file> <spec.json> <out>");
        return 1;
    }
}
