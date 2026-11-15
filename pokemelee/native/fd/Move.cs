// Slew part of a mesh about a vertical axis (desc-local coordinates): e.g. turn Mt. Battle's tower-crane jib end-on.
// Spec (per donor): "local_move": [{"meshes": [[joint, dobj], ...], "c": [x, z], "dir_deg": a, "half_len": l, "half_w": w,
//   "y": [y0, y1], "pivot": [x, z], "deg": d}] - triangles whose centroid lies in that oriented band are rotated by d degrees
//   (math sense in the x-z plane) about the pivot; the rest of the mesh is untouched.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Text.Json;
using HSDRaw.Common;
using HSDRaw.GX;
using HSDRaw.Tools;

static partial class Program
{
    static void LocalMove(JsonElement mv, List<HSD_JOBJ> tl, Dictionary<HSD_JOBJ, Matrix4x4> locals)
    {
        foreach (var m in mv.EnumerateArray())
        {
            var c = new Vector2(m.GetProperty("c")[0].GetSingle(), m.GetProperty("c")[1].GetSingle());
            float a = m.GetProperty("dir_deg").GetSingle() * MathF.PI / 180f;
            var dir = new Vector2(MathF.Cos(a), MathF.Sin(a));
            float hl = m.GetProperty("half_len").GetSingle(), hw = m.GetProperty("half_w").GetSingle();
            float y0 = m.GetProperty("y")[0].GetSingle(), y1 = m.GetProperty("y")[1].GetSingle();
            var pv = new Vector2(m.GetProperty("pivot")[0].GetSingle(), m.GetProperty("pivot")[1].GetSingle());
            float d = m.GetProperty("deg").GetSingle() * MathF.PI / 180f;
            float cs = MathF.Cos(d), sn = MathF.Sin(d);
            int moved = 0;
            foreach (var e in m.GetProperty("meshes").EnumerateArray())
            {
                var jo = tl[e[0].GetInt32()]; var dobj = jo.Dobj.List[e[1].GetInt32()];
                if (!Matrix4x4.Invert(locals[jo], out var inv)) continue;
                HSD_POBJ head = null, tail = null;
                foreach (var p in dobj.Pobj.List)
                {
                    HSD_POBJ res = p;
                    if (Rigid(p))
                    {
                        var tris = Triangles(p.ToDisplayList()); bool any = false;
                        for (int i = 0; i + 2 < tris.Count; i += 3)
                        {
                            var w = new Vector3[3];
                            for (int k = 0; k < 3; k++) w[k] = Vector3.Transform(new Vector3(tris[i + k].POS.X, tris[i + k].POS.Y, tris[i + k].POS.Z), locals[jo]);
                            var cc = (w[0] + w[1] + w[2]) / 3; var q = new Vector2(cc.X, cc.Z) - c;
                            if (MathF.Abs(Vector2.Dot(dir, q)) > hl || MathF.Abs(dir.X * q.Y - dir.Y * q.X) > hw || cc.Y < y0 || cc.Y > y1) continue;
                            any = true; moved++;
                            for (int k = 0; k < 3; k++)
                            {
                                float rx = w[k].X - pv.X, rz = w[k].Z - pv.Y;
                                var nw = new Vector3(pv.X + rx * cs - rz * sn, w[k].Y, pv.Y + rx * sn + rz * cs);
                                var lp = Vector3.Transform(nw, inv);
                                var v = tris[i + k]; v.POS = new GXVector3(lp.X, lp.Y, lp.Z);
                                var n = new Vector3(v.NRM.X, v.NRM.Y, v.NRM.Z);
                                v.NRM = new GXVector3(n.X * cs - n.Z * sn, n.Y, n.X * sn + n.Z * cs);   // joints here carry no rotation
                                tris[i + k] = v;
                            }
                        }
                        if (any)
                        {
                            var attrs = p.ToGXAttributes().Select(x => x.AttributeName).Where(x => x != GXAttribName.GX_VA_NULL).ToArray();
                            var cf = p.Flags.HasFlag(POBJ_FLAG.CULLFRONT); var cb = p.Flags.HasFlag(POBJ_FLAG.CULLBACK);
                            var gen = new POBJ_Generator { CullMode = cf && cb ? GenCullMode.FrontAndBack : cf ? GenCullMode.Front : cb ? GenCullMode.Back : GenCullMode.None,
                                VertexColorFormat = (GXCompType)GXCompTypeClr.RGBA8 };
                            res = gen.CreatePOBJsFromTriangleList(tris, attrs, null);
                            gen.SaveChanges();
                        }
                    }
                    var last = res; while (last.Next != null) last = last.Next;
                    if (head == null) head = res; else tail.Next = res;
                    tail = last;
                }
                tail.Next = null;
                dobj.Pobj = head;
            }
            Console.WriteLine($"  local_move: {moved} triangles slewed {m.GetProperty("deg").GetSingle()} deg about ({pv.X}, {pv.Y})");
        }
    }
}
