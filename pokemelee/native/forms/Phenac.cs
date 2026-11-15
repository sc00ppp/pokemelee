// Phenac City (Pokemon Stadium): Colosseum INSTANCE joints flattened into real subtrees, plus the probe for them.
// Colosseum draws repeated props (palms, lamps) as JOBJ_INSTANCE joints whose child pointer REFERENCES a subtree
// elsewhere in the desc (Melee: jobj.c HSD_JObjDispAll draws child with jobj->mtx * inverse(child->mtx), i.e. the
// referenced subtree's root placed at the instance joint). HSDRaw's TreeList and every recursive walk here loop on
// them, so each instance becomes a plain joint whose child is a copy of the referenced subtree with identity TRS.
// Copies get new JOBJ structs but share the DOBJ chains (descs are read-only templates for the loader).
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using HSDRaw;
using HSDRaw.Common;
using HSDRaw.Common.Animation;

static partial class Program
{
    const JOBJ_FLAG RootFlags = JOBJ_FLAG.ROOT_OPA | JOBJ_FLAG.ROOT_XLU | JOBJ_FLAG.ROOT_TEXEDGE;

    static HSD_JOBJ CopyJointNode(HSD_JOBJ s)
    {
        var c = new HSD_JOBJ { _s = new HSDStruct((byte[])s._s.GetData().Clone()) };
        foreach (var r in s._s.References) c._s.References[r.Key] = r.Value;
        return c;
    }

    // copy src and its descendants (not src.Next); instance joints inside are copied as instances (flattened later)
    static HSD_JOBJ CopyJointTree(HSD_JOBJ src, Dictionary<HSD_JOBJ, HSD_JOBJ> map)
    {
        var c = CopyJointNode(src);
        map[c] = src;
        c.Next = null;
        if (!src.Flags.HasFlag(JOBJ_FLAG.INSTANCE) && src.Child != null)
        {
            HSD_JOBJ head = null, tail = null;
            for (var k = src.Child; k != null; k = k.Next)
            {
                var kc = CopyJointTree(k, map);
                if (head == null) head = kc; else tail.Next = kc;
                tail = kc;
            }
            c.Child = head;
        }
        return c;
    }

    static T CopyAnimTree<T>(T src, bool withNext) where T : HSDTreeAccessor<T>, new()
    {
        if (src == null) return null;
        var c = new T { _s = new HSDStruct((byte[])src._s.GetData().Clone()) };
        foreach (var r in src._s.References) c._s.References[r.Key] = r.Value;
        c.Child = CopyAnimTree(src.Child, true);
        c.Next = withNext ? CopyAnimTree(src.Next, true) : null;
        return c;
    }

    // pair each joint with its anim node (same shape; instance joints' children are not mirrored)
    static void PairAnim<T>(HSD_JOBJ j, T a, Dictionary<HSD_JOBJ, T> outp) where T : HSDTreeAccessor<T>, new()
    {
        for (; j != null; j = j.Next, a = a?.Next)
        {
            if (a != null) outp[j] = a;
            if (!j.Flags.HasFlag(JOBJ_FLAG.INSTANCE) && j.Child != null) PairAnim(j.Child, a?.Child, outp);
        }
    }

    static int FlattenInstances(HSD_JOBJ root, HSD_MatAnimJoint mroot, HSD_AnimJoint aroot)
    {
        var mp = new Dictionary<HSD_JOBJ, HSD_MatAnimJoint>(); if (mroot != null) PairAnim(root, mroot, mp);
        var ap = new Dictionary<HSD_JOBJ, HSD_AnimJoint>(); if (aroot != null) PairAnim(root, aroot, ap);
        int n = 0;
        void W(HSD_JOBJ first, List<HSD_JOBJ> anc)
        {
            for (var c = first; c != null; c = c.Next)
            {
                if (c.Flags.HasFlag(JOBJ_FLAG.INSTANCE))
                {
                    var target = c.Child;
                    var map = new Dictionary<HSD_JOBJ, HSD_JOBJ>();
                    var copy = CopyJointTree(target, map);
                    copy.TX = copy.TY = copy.TZ = 0; copy.RX = copy.RY = copy.RZ = 0; copy.SX = copy.SY = copy.SZ = 1;
                    c.Flags &= ~JOBJ_FLAG.INSTANCE;
                    c.Flags |= RootFlags;
                    foreach (var a in anc) a.Flags |= RootFlags;
                    c.Child = copy;
                    // anims of the referenced subtree follow the copy (the copy's own root has identity TRS: drop its root tracks)
                    if (mp.TryGetValue(target, out var mt) && mp.TryGetValue(c, out var mc)) mc.Child = CopyAnimTree(mt, false);
                    if (ap.TryGetValue(target, out var at) && ap.TryGetValue(c, out var ac))
                    {
                        var acopy = CopyAnimTree(at, false);
                        acopy.AOBJ = null;
                        ac.Child = acopy;
                    }
                    // re-pair the new nodes so nested instances inside the copy also find their anims
                    if (mp.TryGetValue(c, out var mc2) && mc2.Child != null) PairAnim(copy, mc2.Child, mp);
                    if (ap.TryGetValue(c, out var ac2) && ac2.Child != null) PairAnim(copy, ac2.Child, ap);
                    n++;
                    W(copy, new List<HSD_JOBJ>(anc) { c });
                }
                else if (c.Child != null) W(c.Child, new List<HSD_JOBJ>(anc) { c });
            }
        }
        W(root, new List<HSD_JOBJ>());
        return n;
    }

    // probe16 <rdat> <desc> [joint...]: flattened desc, per TreeList joint: depth, world T, meshes (bounds, flags, tex)
    static int Probe16(string[] a)
    {
        var f = new HSDRawFile(a[1]);
        var jd = Scene(f).JOBJDescs[int.Parse(a[2])];
        var memo = new Dictionary<HSDStruct, HSDStruct>();
        var root = Copy(jd.RootJoint, memo);
        var ma = jd.MaterialAnimations != null && jd.MaterialAnimations.Length > 0 ? Copy(jd.MaterialAnimations[0], memo) : null;
        var aa = jd.JointAnimations != null && jd.JointAnimations.Length > 0 ? Copy(jd.JointAnimations[0], memo) : null;
        int nf = FlattenInstances(root, ma, aa);
        var tl = root.TreeList;
        var worlds = new Dictionary<HSD_JOBJ, Matrix4x4>();
        Worlds(root, Matrix4x4.Identity, worlds);
        var depth = new Dictionary<HSD_JOBJ, int>();
        void D(HSD_JOBJ j, int d) { for (var c = j; c != null; c = c.Next) { depth[c] = d; if (c.Child != null) D(c.Child, d + 1); } }
        D(root, 0);
        var animated = new HashSet<HSD_JOBJ>();
        if (aa != null) { var pa = new Dictionary<HSD_JOBJ, HSD_AnimJoint>(); PairAnim(root, aa, pa); foreach (var kv in pa) if (kv.Value.AOBJ?.FObjDesc != null) animated.Add(kv.Key); }
        var matanim = new HashSet<HSD_JOBJ>();
        if (ma != null) { var pm = new Dictionary<HSD_JOBJ, HSD_MatAnimJoint>(); PairAnim(root, ma, pm); foreach (var kv in pm) if (kv.Value.MaterialAnimation != null) matanim.Add(kv.Key); }
        Console.WriteLine($"flattened {nf} instances; {tl.Count} joints; anim joints {animated.Count}, matanim joints {matanim.Count}");
        var want = a.Skip(3).Select(int.Parse).ToHashSet();
        for (int j = 0; j < tl.Count; j++)
        {
            var jo = tl[j]; var w = worlds[jo];
            if (want.Count > 0 && !want.Contains(j)) continue;
            var line = $"j{j} d{depth[jo]} T=({w.M41:F0},{w.M42:F0},{w.M43:F0}) {(animated.Contains(jo) ? "ANIM " : "")}{(matanim.Contains(jo) ? "MATANIM " : "")}{jo.Flags & ~(JOBJ_FLAG.CLASSICAL_SCALING)}";
            Console.WriteLine(line);
            if (jo.Dobj == null) continue;
            int o = 0;
            foreach (var d in jo.Dobj.List)
            {
                var (lo, hi) = Bounds(d, w);
                var m = d.Mobj;
                var tx = m?.Textures?.List.Select(t => $"{t.ImageData?.Width}x{t.ImageData?.Height}{t.ImageData?.Format}") ?? new string[0];
                int nv = d.Pobj?.List.Sum(p => p.ToDisplayList().Vertices.Count) ?? 0;
                Console.WriteLine($"   o{o} ({lo.X:F0},{lo.Y:F0},{lo.Z:F0})..({hi.X:F0},{hi.Y:F0},{hi.Z:F0}) v{nv} {m?.RenderFlags} [{string.Join(" ", tx)}]");
                o++;
            }
        }
        return 0;
    }
}
