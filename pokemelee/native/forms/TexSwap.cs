// Texture swaps for stage files that must keep their geometry (Pokemon Stadium's transformation forms: their models
// follow vanilla collision exactly). A target texture image is replaced, at its own size, by a crop of a Colosseum
// texture; every TObj sharing that image follows. Encoded CMP (4 bpp) so a CI4/CI8/CMP target never grows: the form
// files load into a fixed 0x50000-byte buffer.
//   "tex_sources": {"name": [rdat, desc, flattened joint, dobj, tobj]}
//   "tex_swap": [{"t": [group, joint, dobj, tobj], "src": "name", "crop": [x0,y0,x1,y1], "tint": [r,g,b], "rot": 90,
//                 "keep_alpha": true, "seamless": true, "mirror_x": false}]
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using HSDRaw;
using HSDRaw.Common;
using HSDRaw.GX;
using HSDRaw.Melee.Gr;

static partial class Program
{
    static void TexSwap(JsonElement spec, SBM_Map_GOBJ[] groups)
    {
        var srcPx = new Dictionary<string, (byte[] px, int w, int h)>();
        foreach (var p in spec.GetProperty("tex_sources").EnumerateObject())
        {
            var e = p.Value;
            var f = new HSDRawFile(e[0].GetString());
            HSD_TOBJ t;
            if (f.Roots.Any(r => r.Name == "scene_data"))
            {
                var root = Copy(Scene(f).JOBJDescs[e[1].GetInt32()].RootJoint, new Dictionary<HSDStruct, HSDStruct>());
                FlattenInstances(root, null, null);
                t = root.TreeList[e[2].GetInt32()].Dobj.List[e[3].GetInt32()].Mobj.Textures.List[e[4].GetInt32()];
            }
            else
            {
                var gs = f.Roots.Select(r => r.Data).OfType<SBM_Map_Head>().First().ModelGroups.Array;
                t = gs[e[1].GetInt32()].RootNode.TreeList[e[2].GetInt32()].Dobj.List[e[3].GetInt32()].Mobj.Textures.List[e[4].GetInt32()];
            }
            srcPx[p.Name] = (t.GetDecodedImageData(), t.ImageData.Width, t.ImageData.Height);
            Console.WriteLine($"tex source {p.Name}: {t.ImageData.Width}x{t.ImageData.Height} {t.ImageData.Format}");
        }
        // every TObj in the file, grouped by image buffer
        var users = new Dictionary<HSDStruct, List<HSD_TOBJ>>();
        foreach (var g in groups)
        {
            if (g.RootNode == null) continue;
            foreach (var j in g.RootNode.TreeList)
            {
                if (j.Dobj == null) continue;
                foreach (var d in j.Dobj.List)
                    if (d.Mobj?.Textures != null)
                        foreach (var t in d.Mobj.Textures.List)
                        {
                            var buf = t.ImageData?._s.GetReference<HSDAccessor>(0);
                            if (buf == null) continue;
                            if (!users.TryGetValue(buf._s, out var l)) users[buf._s] = l = new List<HSD_TOBJ>();
                            l.Add(t);
                        }
            }
        }
        int n = 0;
        foreach (var s in spec.GetProperty("tex_swap").EnumerateArray())
        {
            var ti = s.GetProperty("t").EnumerateArray().Select(v => v.GetInt32()).ToArray();
            var tgt = groups[ti[0]].RootNode.TreeList[ti[1]].Dobj.List[ti[2]].Mobj.Textures.List[ti[3]];
            int w = tgt.ImageData.Width, h = tgt.ImageData.Height;
            var (spx, sw, sh) = srcPx[s.GetProperty("src").GetString()];
            var c = s.GetProperty("crop").EnumerateArray().Select(v => v.GetInt32()).ToArray();
            int rot = s.TryGetProperty("rot", out var rv) ? rv.GetInt32() : 0;
            byte[] px;
            if (rot == 90) { px = Rot90(CropResize(spx, sw, c[0], c[1], c[2] - c[0], c[3] - c[1], h, w), h, w); }
            else px = CropResize(spx, sw, c[0], c[1], c[2] - c[0], c[3] - c[1], w, h);
            if (s.TryGetProperty("seamless", out var sm) && sm.GetBoolean()) px = Seamless(px, w, h, true, true);
            if (s.TryGetProperty("tint", out var tn))
            {
                var k = tn.EnumerateArray().Select(v => v.GetSingle()).ToArray();
                for (int i = 0; i < px.Length; i += 4) { px[i] = (byte)Math.Min(255, px[i] * k[2]); px[i + 1] = (byte)Math.Min(255, px[i + 1] * k[1]); px[i + 2] = (byte)Math.Min(255, px[i + 2] * k[0]); }
            }
            if (s.TryGetProperty("keep_alpha", out var ka) && ka.GetBoolean())
            {
                var orig = tgt.GetDecodedImageData();
                for (int i = 3; i < px.Length; i += 4) px[i] = orig[i];
            }
            else for (int i = 3; i < px.Length; i += 4) px[i] = 255;
            var buf = tgt.ImageData._s.GetReference<HSDAccessor>(0);
            var img = MakeImage(px, w, h, tgt.ImageData.MipMap != 0, (int)tgt.ImageData.MaxLOD + 1);
            foreach (var t in users[buf._s]) { t.ImageData = img; t.TlutData = null; }
            n++;
        }
        Console.WriteLine($"tex_swap: {n} images replaced");
    }
}
