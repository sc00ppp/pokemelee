/* fxrender.c: Colosseum sound effects to WAVs through the MusyX runtime's own PC renderer (AxioDL/musyx), the way the
 * game plays them (the effect's macro: its samples, pitch, envelopes).
 *
 * usage: fxrender <bank dir> <group name> <group id> <out dir> <first fx id> <last fx id> [max seconds]
 *   <bank dir> holds <group>_proj, <group>_pool, <group>_sdir (from the game's sound archive) and <group>.samp (from the
 *   disc). Every effect id from first to last is played alone from a fresh start and written to <out dir>/<id>.wav,
 *   32 kHz stereo, cut where it falls silent. Ids the project does not have are skipped.
 */
#include <musyx/musyx.h>
#include <musyx/pc.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void *slurp(const char *dir, const char *name, size_t *size) {
  char path[1024];
  snprintf(path, sizeof path, "%s/%s", dir, name);
  FILE *f = fopen(path, "rb");
  if (!f) {
    fprintf(stderr, "cannot open %s\n", path);
    exit(1);
  }
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  rewind(f);
  void *data = calloc(1, (size_t)n + 64);
  if (fread(data, 1, (size_t)n, f) != (size_t)n) {
    fprintf(stderr, "short read %s\n", path);
    exit(1);
  }
  fclose(f);
  if (size)
    *size = (size_t)n;
  return data;
}

static void put32(FILE *f, unsigned v) { fwrite(&v, 4, 1, f); }
static void put16(FILE *f, unsigned short v) { fwrite(&v, 2, 1, f); }

static void wav(const char *path, const s16 *pcm, size_t frames, unsigned rate, unsigned channels) {
  FILE *out = fopen(path, "wb");
  fwrite("RIFF", 1, 4, out);
  put32(out, 36 + (unsigned)(frames * channels * 2));
  fwrite("WAVEfmt ", 1, 8, out);
  put32(out, 16);
  put16(out, 1);
  put16(out, (unsigned short)channels);
  put32(out, rate);
  put32(out, rate * channels * 2);
  put16(out, (unsigned short)(channels * 2));
  put16(out, 16);
  fwrite("data", 1, 4, out);
  put32(out, (unsigned)(frames * channels * 2));
  fwrite(pcm, 2, frames * channels, out);
  fclose(out);
}

int main(int argc, char **argv) {
  if (argc < 7) {
    fprintf(stderr, "usage: fxrender <bank dir> <group name> <group id> <out dir> <first fx> <last fx> [max s]\n");
    return 2;
  }
  const char *dir = argv[1], *grp = argv[2], *outdir = argv[4];
  int gid = atoi(argv[3]), first = atoi(argv[5]), last = atoi(argv[6]);
  double maxs = argc > 7 ? atof(argv[7]) : 4.0;
  const unsigned rate = 32000, channels = 2;
  char name[256];
  size_t projN, poolN, sdirN, sampN;
  snprintf(name, sizeof name, "%s_proj", grp);
  void *proj = slurp(dir, name, &projN);
  snprintf(name, sizeof name, "%s_pool", grp);
  void *pool = slurp(dir, name, &poolN);
  snprintf(name, sizeof name, "%s_sdir", grp);
  void *sdir = slurp(dir, name, &sdirN);
  snprintf(name, sizeof name, "%s.samp", grp);
  void *samp = slurp(dir, name, &sampN);

  SND_HOOKS hooks = {malloc, free};
  sndSetHooks(&hooks);
  SND_PC_CONFIG cfg = {rate, channels};
  if (!sndPCConfigure(&cfg)) {
    fprintf(stderr, "configure failed\n");
    return 1;
  }
  SND_PC_GROUP_ASSETS assets = {{proj, projN}, {pool, poolN}, {sdir, sdirN}, {samp, sampN}};
  SND_PC_ASSET_ERROR err = {0};
  if (!sndPCValidateGroup(&assets, &err))
    fprintf(stderr, "group check: %s at %zu: %s (going on)\n", err.section ? err.section : "?", err.offset,
            err.reason ? err.reason : "?");

  size_t maxf = (size_t)(maxs * rate);
  s16 *pcm = malloc(maxf * channels * sizeof(s16) + 64);
  for (int fx = first; fx <= last; ++fx) {
    if (sndInit(64, 64, 64, 1, 0, 0) != 0) {
      fprintf(stderr, "sndInit failed\n");
      return 1;
    }
    if (!sndPushGroup(proj, (SND_GROUPID)gid, samp, sdir, pool)) {
      fprintf(stderr, "push group %d failed\n", gid);
      return 1;
    }
    sndMasterVolume(127, 0, 1, 1);
    for (int g = 0; g < 32; ++g)            /* every volume group up: the effects' groups start silent here */
      sndVolume(127, 0, (u8)g);
    SND_VOICEID vid = sndFXStart((SND_FXID)fx, 127, 64);
    if (vid == SND_ID_ERROR) {
      printf("fx %d: none\n", fx);
      sndQuit();
      continue;
    }
    size_t done = 0, lastLoud = 0, peak = 0;
    int keyed = 0;
    while (done < maxf) {
      size_t n = maxf - done < 256 ? maxf - done : 256;
      sndPCRender(pcm + done * channels, n);
      for (size_t i = 0; i < n * channels; i++) {
        s16 v = pcm[done * channels + i];
        size_t a = (size_t)(v < 0 ? -v : v);
        if (a > peak)
          peak = a;
        if (a > 64)
          lastLoud = done + i / channels;
      }
      done += n;
      if (!keyed && done > maxf * 3 / 4) {      /* a held or looping effect: let it go for its release */
        sndFXKeyOff(vid);
        keyed = 1;
      }
      if (sndFXCheck(vid) == SND_ID_ERROR && done > lastLoud + rate / 5)
        break;
    }
    size_t keep = lastLoud + rate / 50 < done ? lastLoud + rate / 50 : done;
    char path[1024];
    snprintf(path, sizeof path, "%s/%d.wav", outdir, fx);
    wav(path, pcm, keep, rate, channels);
    printf("fx %d: %.3f s, peak %zu%s\n", fx, (double)keep / rate, peak, keyed ? ", held (keyed off)" : "");
    sndQuit();
  }
  return 0;
}
