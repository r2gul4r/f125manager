#define NOMINMAX
#include <windows.h>
#include "qwen.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <deque>
#include <dxgi1_4.h>
#include <fstream>
#include <iterator>
#include <memory>
#include <mmsystem.h>
#include <thread>
#include <vector>
double now() {
  LARGE_INTEGER t, f;
  QueryPerformanceCounter(&t);
  QueryPerformanceFrequency(&f);
  return double(t.QuadPart) / f.QuadPart;
}
struct Packet {
  WAVEHDR h{};
  std::vector<short> pcm;
};
struct Trial {
  HWAVEOUT output{};
  std::deque<Packet> chunks;
  std::vector<short> samples;
  double start{}, firstChunk{}, firstVoice{}, firstQueued{};
  bool play{};
  static bool emit(const float *s, int n, void *user) {
    auto &t = *static_cast<Trial *>(user);
    if (n <= 0)
      return true;
    double ts = now();
    if (!t.firstChunk)
      t.firstChunk = ts;
    auto &p = t.chunks.emplace_back();
    p.pcm.reserve(n);
    for (int i = 0; i < n; i++) {
      if (!t.firstVoice && std::fabs(s[i]) > 0.00316)
        t.firstVoice = ts;
      p.pcm.push_back(short(std::clamp(s[i], -1.f, 1.f) * 32767));
    }
    t.samples.insert(t.samples.end(), p.pcm.begin(), p.pcm.end());
    if (t.play) {
      p.h.lpData = (LPSTR)p.pcm.data();
      p.h.dwBufferLength = DWORD(n * 2);
      if (waveOutPrepareHeader(t.output, &p.h, sizeof(p.h)) == 0 &&
          waveOutWrite(t.output, &p.h, sizeof(p.h)) == 0 && t.firstVoice &&
          !t.firstQueued)
        t.firstQueued = now();
    }
    return true;
  }
  void save(const char *file) {
    std::ofstream w(file, std::ios::binary);
    auto put = [&](unsigned n, int bytes) { w.write((char *)&n, bytes); };
    w.write("RIFF", 4);
    put(36 + unsigned(samples.size() * 2), 4);
    w.write("WAVEfmt ", 8);
    put(16, 4);
    put(1, 2);
    put(1, 2);
    put(24000, 4);
    put(48000, 4);
    put(2, 2);
    put(16, 2);
    w.write("data", 4);
    put(unsigned(samples.size() * 2), 4);
    w.write((char *)samples.data(), samples.size() * 2);
  }
};
int main(int argc, char **argv) {
  if (argc != 3)
    return 2;
  const char *dev = argv[1];
  const int repeats = atoi(argv[2]);
  IDXGIFactory1 *factory{};
  IDXGIAdapter3 *nv{};
  if (SUCCEEDED(
          CreateDXGIFactory1(__uuidof(IDXGIFactory1), (void **)&factory))) {
    IDXGIAdapter1 *a{};
    for (UINT i = 0; factory->EnumAdapters1(i, &a) == S_OK; i++) {
      DXGI_ADAPTER_DESC1 desc;
      a->GetDesc1(&desc);
      if (desc.VendorId == 0x10de)
        a->QueryInterface(__uuidof(IDXGIAdapter3), (void **)&nv);
      a->Release();
      if (nv)
        break;
    }
    factory->Release();
  }
  auto mem = [&](DXGI_MEMORY_SEGMENT_GROUP group) {
    DXGI_QUERY_VIDEO_MEMORY_INFO m{};
    return nv && SUCCEEDED(nv->QueryVideoMemoryInfo(0, group, &m))
               ? m.CurrentUsage / 1048576.
               : 0.;
  };
  std::atomic<bool> done{false};
  double peak = 0, shared = 0;
  std::thread watch{[&]() {
    while (!done) {
      peak = std::max(peak, mem(DXGI_MEMORY_SEGMENT_GROUP_LOCAL));
      shared = std::max(shared, mem(DXGI_MEMORY_SEGMENT_GROUP_NON_LOCAL));
      Sleep(50);
    }
  }};
  qt_init_params init;
  qt_init_default_params(&init);
  init.device = dev;
  if (getenv("Q4_DIAGNOSTIC")) {
    init.use_fa = false;
    init.clamp_fp16 = true;
  }
  init.talker_path = "qwen-talker-0.6b-base-Q4_K_M.gguf";
  init.codec_path = "qwen-tokenizer-12hz-Q4_K_M.gguf";
  double opened = now();
  auto *ctx = qt_init(&init);
  double loaded = now();
  printf("LOAD %s %.6f %.6f residentMiB %.1f\n", dev, opened, loaded,
         mem(DXGI_MEMORY_SEGMENT_GROUP_LOCAL));
  fflush(stdout);
  int status = 0;
  qt_voice_ref ref{};
  if (ctx) {
    std::ifstream file("bono/reference.pcm", std::ios::binary);
    std::vector<char> bytes((std::istreambuf_iterator<char>(file)), {});
    std::vector<float> data(bytes.size() / 2);
    for (size_t i = 0; i < data.size(); i++) {
      short value;
      memcpy(&value, &bytes[2 * i], 2);
      data[i] = value / 32768.f;
    }
    if (data.empty() || qt_extract_voice_ref(ctx, data.data(), int(data.size()),
                                             &ref) != QT_STATUS_OK) {
      fprintf(stderr, "reference failed: %s\n", qt_last_error());
      status = 1;
    }
    printf("REF %s %.6f\n", dev, now());
    fflush(stdout);
  }
  if (!ctx) {
    fprintf(stderr, "%s\n", qt_last_error());
    status = 1;
  }
  for (int i = 0; ctx && !status && i < repeats; i++) {
    Trial t;
    WAVEFORMATEX fmt{WAVE_FORMAT_PCM, 1, 24000, 48000, 2, 16, 0};
    t.play = (i > 0) && waveOutOpen(&t.output, WAVE_MAPPER, &fmt, 0, 0,
                                    CALLBACK_NULL) == MMSYSERR_NOERROR;
    if (i > 0 && !t.play)
      return 10;
    char line[256]{};
    if (!i)
      strcpy_s(line, "Radio check.");
    else {
      printf("READY\n");
      fflush(stdout);
      if (!fgets(line, sizeof(line), stdin))
        return 11;
    }
    line[strcspn(line, "\r\n")] = 0;
    qt_tts_params p;
    qt_tts_default_params(&p);
    p.text = line;
    p.lang = "english";
    p.seed = 45;
    p.max_new_tokens = 240;
    p.on_chunk = Trial::emit;
    p.on_chunk_user_data = &t;
    p.ref_text =
        "Just info, George retired with a suspected water system issue.";
    p.ref_spk_emb = ref.ref_spk_emb;
    p.ref_spk_dim = ref.ref_spk_dim;
    p.ref_codes = ref.ref_codes;
    p.ref_T = ref.ref_T;
    qt_audio out{};
    t.start = now();
    auto rc = qt_synthesize(ctx, &p, &out);
    double end = now();
    printf("RUN %s %d %.6f %.6f chunk %.4f voice %.4f queued %.4f seconds %.4f "
           "samples %zu rc %d\n",
           dev, i, t.start, end, t.firstChunk ? t.firstChunk - t.start : -1.,
           t.firstVoice ? t.firstVoice - t.start : -1.,
           t.firstQueued ? t.firstQueued - t.start : -1., end - t.start,
           t.samples.size(), int(rc));
    fflush(stdout);
    if (i && rc == QT_STATUS_OK) {
      char file[64];
      snprintf(file, sizeof(file), "bono/mic-reply.wav");
      t.save(file);
    }
    if (t.play) {
      for (auto &part : t.chunks) {
        if (part.h.dwFlags & WHDR_PREPARED) {
          while (!(part.h.dwFlags & WHDR_DONE))
            Sleep(10);
          waveOutUnprepareHeader(t.output, &part.h, sizeof(part.h));
        }
      }
      waveOutClose(t.output);
    }
    if (rc != QT_STATUS_OK || !t.firstVoice) {
      fprintf(stderr, "%s\n", qt_last_error());
      status = 1;
      break;
    }
    qt_audio_free(&out);
    Sleep(500);
  }
  done = true;
  watch.join();
  printf("MEM %s dedicatedPeakMiB %.1f sharedPeakMiB %.1f\n", dev, peak,
         shared);
  fflush(stdout);
  qt_voice_ref_free(&ref);
  if (ctx)
    qt_free(ctx);
  if (nv)
    nv->Release();
  return status;
}
