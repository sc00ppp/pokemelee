/* render.c: one Colosseum song to a WAV through the MusyX runtime's own PC renderer (AxioDL/musyx).
 *
 * usage: render <bank dir> <song file> <song id> <seconds> <out.wav> [master volume 0..127]
 *   <bank dir> holds snd_music_proj, snd_music_pool, snd_music_sdir (from the game's sound archive) and
 *   snd_music.samp (from the disc). The song file is one entry of bgm_archive.fsys, LZSS undone (fsys.py).
 *   The song id picks the project's MIDI setup (channel programs, volumes, pans) for the song.
 */
#include <musyx/musyx.h>
#include <musyx/pc.h>
#include <musyx/seq.h>

/* the sequencer's own state (seq.c): where the song first reaches its loop point, and each time it jumps back */
extern SEQ_INSTANCE seqInstance[8];

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void *slurp(const char *dir, const char *name, size_t *size) {
  char path[1024];
  if (dir)
    snprintf(path, sizeof path, "%s/%s", dir, name);
  else
    snprintf(path, sizeof path, "%s", name);
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

int main(int argc, char **argv) {
  if (argc < 6) {
    fprintf(stderr, "usage: render <bank dir> <song file> <song id> <seconds> <out.wav>\n");
    return 2;
  }
  const char *dir = argv[1];
  int songId = atoi(argv[3]);
  double seconds = atof(argv[4]);
  const unsigned rate = 32000, channels = 2;

  SND_HOOKS hooks = {malloc, free};
  sndSetHooks(&hooks);
  SND_PC_CONFIG cfg = {rate, channels};
  if (!sndPCConfigure(&cfg)) {
    fprintf(stderr, "configure failed\n");
    return 1;
  }
  size_t projN, poolN, sdirN, sampN, songN;
  void *proj = slurp(dir, "snd_music_proj", &projN);
  void *pool = slurp(dir, "snd_music_pool", &poolN);
  void *sdir = slurp(dir, "snd_music_sdir", &sdirN);
  void *samp = slurp(dir, "snd_music.samp", &sampN);
  void *song = slurp(NULL, argv[2], &songN);

  SND_PC_GROUP_ASSETS assets = {{proj, projN}, {pool, poolN}, {sdir, sdirN}, {samp, sampN}};
  SND_PC_ASSET_ERROR err = {0};
  if (!sndPCValidateGroup(&assets, &err)) {
    fprintf(stderr, "group invalid: %s at %zu: %s\n", err.section ? err.section : "?", err.offset,
            err.reason ? err.reason : "?");
    return 1;
  }
  if (!sndPCValidateArrangement((SND_PC_SPAN){song, songN}, &err)) {
    fprintf(stderr, "song invalid: %s at %zu: %s\n", err.section ? err.section : "?", err.offset,
            err.reason ? err.reason : "?");
    return 1;
  }
  if (sndInit(64, 64, 64, 1, 0, 0) != 0) {
    fprintf(stderr, "sndInit failed\n");
    return 1;
  }
  /* the PC push decodes the disc's own (32-bit) sample directory itself; older builds wanted it converted first */
  if (!sndPushGroup(proj, 0, samp, sdir, pool)) {
    void *copy = malloc(sdirN + 64);
    memcpy(copy, sdir, sdirN);
    void *sdir64 = sndConvert32BitSDIRTo64BitSDIR(copy);
    if (!sndPushGroup(proj, 0, samp, sdir64, pool)) {
      fprintf(stderr, "push group failed (raw and converted sample directory)\n");
      return 1;
    }
    fprintf(stderr, "pushed with the converted sample directory\n");
  }
  if (argc > 6)               /* optional music master volume 0..127, to keep a loud song off the s16 ceiling */
    sndMasterVolume((u8)atoi(argv[6]), 0, 1, 0);
  SND_SEQID seq = sndSeqPlay(0, (SND_SONGID)songId, song, NULL);
  if (seq == SND_SEQ_ERROR_ID) {
    fprintf(stderr, "sndSeqPlay failed for song id %d\n", songId);
    return 1;
  }
  size_t frames = (size_t)(seconds * rate);
  FILE *out = fopen(argv[5], "wb");
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
  s16 buf[4096 * 2];
  size_t done = 0, peak = 0;
  u16 loops[16] = {0};
  int reached[16] = {0};
  /* small chunks so the loop marks land within a few samples of the sequencer's own frame */
  while (done < frames) {
    size_t n = frames - done < 32 ? frames - done : 32;
    sndPCRender(buf, n);
    for (int k = 0; k < 8; ++k) {
      SEQ_INSTANCE *si = &seqInstance[k];
      if (!si->state || !si->arrbase)
        continue;
      for (int s = 0; s < 16; ++s) {
        SEQ_SECTION *sec = &si->section[s];
        s32 ticks = sec->time[sec->timeIndex].high;
        if (!reached[s] && sec->loopCnt == 0 && ticks >= (s32)si->arrbase->loopPoint[s] && ticks > 0 &&
            si->arrbase->loopPoint[s] > 0) {
          reached[s] = 1;
          printf("loopstart section %d tick %u frame %zu\n", s, si->arrbase->loopPoint[s], done + n);
        }
        if (sec->loopCnt != loops[s]) {
          loops[s] = sec->loopCnt;
          printf("loop section %d count %u frame %zu tick %d\n", s, sec->loopCnt, done + n, ticks);
        }
      }
    }
    for (size_t i = 0; i < n * channels; i++) {
      size_t a = (size_t)(buf[i] < 0 ? -buf[i] : buf[i]);
      if (a > peak)
        peak = a;
    }
    fwrite(buf, 2, n * channels, out);
    done += n;
  }
  fclose(out);
  printf("%s: song id %d, %.1f s, peak %zu\n", argv[5], songId, seconds, peak);
  sndQuit();
  return 0;
}
