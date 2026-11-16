// stagegraft flavor "texenc": HSDRaw's GX texture codec in batch, for the model-patch rebuild.
// Batch GX texture codec over HSDRaw's own converter. Job lines:
//   decode <fmt> <w> <h> <data> <palfmt> <count> <pal|-> <out.rgba>
//   encode <fmt> <palfmt> <w> <h> <in.rgba> <out.data> <out.pal>
using HSDRaw.GX;
using HSDRaw.Tools;
foreach (var line in File.ReadAllLines(args[0]))
{
    var a = line.Split('\t');
    if (a[0] == "decode")
    {
        var fmt = (GXTexFmt)int.Parse(a[1]); int w = int.Parse(a[2]), h = int.Parse(a[3]);
        var data = File.ReadAllBytes(a[4]);
        var pal = a[7] == "-" ? new byte[0] : File.ReadAllBytes(a[7]);
        var rgba = GXImageConverter.DecodeTPL(fmt, w, h, data, (GXTlutFmt)int.Parse(a[5]), int.Parse(a[6]), pal);
        File.WriteAllBytes(a[8], rgba);
    }
    else if (a[0] == "encode")
    {
        var fmt = (GXTexFmt)int.Parse(a[1]); var pf = (GXTlutFmt)int.Parse(a[2]); int w = int.Parse(a[3]), h = int.Parse(a[4]);
        var enc = GXImageConverter.EncodeImage(File.ReadAllBytes(a[5]), w, h, fmt, pf, out var pal);
        File.WriteAllBytes(a[6], enc); File.WriteAllBytes(a[7], pal ?? new byte[0]);
    }
}
