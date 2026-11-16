#define NOMINMAX
#include <windows.h>
#include <algorithm>
#include <audioclient.h>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <io.h>
#include <ksmedia.h>
#include <mmdeviceapi.h>
#include <vector>
#include <wrl/client.h>
using Microsoft::WRL::ComPtr;
#define HR(x)                                                                  \
  if (FAILED(x)) {                                                             \
    fprintf(stderr, "FAILED %d\n", __LINE__);                                  \
    return 3;                                                                  \
  }
double now() {
  LARGE_INTEGER q, f;
  QueryPerformanceCounter(&q);
  QueryPerformanceFrequency(&f);
  return double(q.QuadPart) / f.QuadPart;
}
int main(int argc, char **argv) {
  bool mic = argc == 2 && !strcmp(argv[1], "mic");
  _setmode(_fileno(stdout), _O_BINARY);
  HR(CoInitializeEx(nullptr, COINIT_MULTITHREADED));
  ComPtr<IMMDeviceEnumerator> en;
  ComPtr<IMMDevice> dev;
  ComPtr<IAudioClient> client;
  ComPtr<IAudioCaptureClient> cap;
  HR(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                      IID_PPV_ARGS(&en)));
  HR(en->GetDefaultAudioEndpoint(mic ? eCapture : eRender, eMultimedia, &dev));
  HR(dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, &client));
  WAVEFORMATEX *w;
  HR(client->GetMixFormat(&w));
  bool fp = w->wFormatTag == WAVE_FORMAT_IEEE_FLOAT ||
            (w->wFormatTag == WAVE_FORMAT_EXTENSIBLE &&
             IsEqualGUID(((WAVEFORMATEXTENSIBLE *)w)->SubFormat,
                         KSDATAFORMAT_SUBTYPE_IEEE_FLOAT));
  if (!fp || w->wBitsPerSample != 32)
    return 4;
  HR(client->Initialize(AUDCLNT_SHAREMODE_SHARED,
                        mic ? 0 : AUDCLNT_STREAMFLAGS_LOOPBACK, 1000000, 0, w,
                        nullptr));
  HR(client->GetService(IID_PPV_ARGS(&cap)));
  fwrite(&w->nSamplesPerSec, 4, 1, stdout);
  fflush(stdout);
  HR(client->Start());

  double start = now();
  while (now() - start < 18.0) {
    UINT32 n;
    HR(cap->GetNextPacketSize(&n));
    if (!n) {
      Sleep(2);
      continue;
    }
    BYTE *raw;
    DWORD flags;
    UINT64 pos, stamp;
    HR(cap->GetBuffer(&raw, &n, &flags, &pos, &stamp));
    if (!(flags & AUDCLNT_BUFFERFLAGS_TIMESTAMP_ERROR)) {
      std::vector<float> mono(n, 0.0f);
      if (!(flags & AUDCLNT_BUFFERFLAGS_SILENT)) {
        auto pcm = (float *)raw;
        for (UINT32 i = 0; i < n; i++) {
          for (int c = 0; c < w->nChannels; c++)
            mono[i] += pcm[i * w->nChannels + c] / w->nChannels;
        }
      }
      fwrite(&stamp, 8, 1, stdout);
      fwrite(&n, 4, 1, stdout);
      fwrite(mono.data(), 4, n, stdout);
      fflush(stdout);
    }
    HR(cap->ReleaseBuffer(n));
  }
  client->Stop();
  CoTaskMemFree(w);
  return 0;
}
