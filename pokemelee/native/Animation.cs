using System.Collections.Generic;
using HSDRaw.Common.Animation;

static partial class Program
{
    static List<HSD_AnimJoint> DfsAJ(HSD_AnimJoint root)
    {
        var result = new List<HSD_AnimJoint>();
        void Visit(HSD_AnimJoint node)
        {
            for (var c = node; c != null; c = c.Next)
            {
                result.Add(c);
                if (c.Child != null) Visit(c.Child);
            }
        }
        Visit(root);
        return result;
    }
}
