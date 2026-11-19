# Strict audio decoding and offline diagnosis

Install `requirements-audio-processing.txt` for production validation. MP3 needs
the pinned imageio-ffmpeg package's bundled executable; validation does not download
tools at runtime. Missing FFmpeg is an error, not permission to use a lenient fallback.
For auxiliary comparison install `requirements-audio-diagnostics.txt` and provide a
standalone mpg123 executable from its official distribution. No player output is
sent to a sound device: PCM goes only through memory pipes and is hashed/counted.

```powershell
python -m scripts.wildlife_audio diagnose D:\WildGuardAudio D:\metadata\bundle.json --mpg123 D:\tools\mpg123.exe --report-relative reports/decoder-review.json
```

The command diagnoses and retains bounded metadata but does not change states by
default. `--apply` explicitly applies the retained consensus-checked verdict. It
does not repair, re-encode, delete or redownload files. There is no network-source
or replacement-download option. Existing output paths cannot be overwritten.

The conservative scanner supports contiguous MPEG-1/2/2.5 Layer III, recognized
ID3v1/v2 metadata, ordinary rate/channel profiles and protected side-information
CRCs. Invalid framing, truncation, CRC, big-values and reservoir failures reject;
unknown/free-format framing requires separate review. CRC protects the fields
defined by MPEG, not all audio data; strict decoding and source checksums are still
required. Legal bit changes without an authoritative source checksum cannot be
proven absent by any structural scanner.

Production FFmpeg uses `crccheck+bitstream+explode`, fails on errors, and records
info-level logs. It refuses frame loss on streams without timing headers. Timing
headers can legitimately describe encoder delay/padding; standalone reclassification
currently conservatively supports only exact full-frame consensus without them.
It does not promise a universal MP3 forensic validator.

FFmpeg `buffer`/`aggressive` error-recognition options are deliberately not the
acceptance profile: their decoder code can log unused positive `bits_left` as an
error and zero bands on otherwise decodable ancillary data, including clean control
recordings. This is not an ignored runtime error: those options are a different,
documented diagnostic policy. Every actual error/overread/concealment log emitted
under the selected production policy is retained and fatal, even on exit zero.

The isolated worker protocol also makes any unsolicited native stderr fatal for
SoundFile containers. Real EOF is counted from returned reads, never from a padded
estimated-length iterator. Process time and output/log buffers are bounded. File
hashes are checked before/after validation. Fingerprints reuse that PCM route.

See the [NPS diagnosis](../data/datasets/audio/releases/nps-pilot-diagnosis-2026-11-19/README.md)
for exact software versions, input/PCM hashes and the reviewed historical error.
Independent decoders may differ in sample rounding and gapless behavior; decoded
hash equality is not assumed across decoder versions or sample formats.
