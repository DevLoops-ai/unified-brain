# xz — question set

Nine questions on [xz](https://github.com/tukaani-project/xz) (liblzma and
the `xz` tool). The database used for the runs holds 1,349 commits, from
`f7fa309e` (January 2021) to `45d08abc` (1 July 2024); it includes the 2024
commits that added and later removed the CVE-2024-3094 backdoor material.

These are nine of the ten questions we have asked since the start of the
project, unchanged in wording. The tenth (Block Header sizes vs. decoded
bytes) was removed from the set on 2026-10-29 after the runs; see
`results/qa-xz-2026-10-29.md`. The reference points were read from the source at
`45d08abc` and from `git log` / `git show` on 2026-10-29, before the eval
runs. Line numbers are left out on purpose: grade by function names,
constants, commit hashes and facts. Where a keyword search would go wrong,
a "trap" line says how, so the grader can see whether the answer fell in.

---

## Q1 — build: the GNU-stack note

> Under which conditions does the build emit the `.note.GNU-stack` section?

Reference points:

1. The directive appears only in the two hand-written 32-bit x86 assembly
   files, `src/liblzma/check/crc32_x86.S` and `crc64_x86.S`, as
   `.section .note.GNU-stack,"",@progbits`.
2. In those files it is guarded by
   `#if defined(__ELF__) && (defined(__FreeBSD__) || defined(__linux__))`;
   the comment says it is "needed to support non-executable stack" and that
   the OS macros stand in for "using GNU assembler".
3. The files are compiled only when the x86 assembly is enabled: Autotools
   `COND_ASM_X86` from `--enable-assembler` (default `yes` → `x86` only when
   `$host_cpu` matches `i?86` on linux/bsd/mingw/cygwin/msys/djgpp; defines
   `HAVE_CRC_X86_ASM`); CMake `XZ_ASM_I386` (default from `__i386__`).
4. So: 32-bit x86 build, assembler optimisations on, target is ELF on Linux
   or FreeBSD. C sources never emit it themselves; the compiler handles the
   note for them.

Trap: `.note.GNU-stack` is not in any C file, CMake file or configure
script; grepping the build system finds nothing — the condition lives in the
`.S` files and the rule that compiles them.

## Q2 — sandboxing

> How is sandboxing enforced in this codebase, and on which platforms?

Reference points (`src/xz/sandbox.c`, `src/xz/main.c`, `src/xz/file_io.c`,
`src/xzdec/xzdec.c`, `configure.ac`):

1. Three mechanisms, one compiled in: `pledge(2)` (OpenBSD),
   Landlock (Linux, `HAVE_LINUX_LANDLOCK`, ABI up to 3 or 4), Capsicum
   (FreeBSD, `cap_enter` / `cap_rights_limit`). Chosen by configure
   `--enable-sandbox=auto|no|capsicum|pledge|landlock` (CMake has the
   equivalent); `ENABLE_SANDBOX` is defined when one is found.
2. Three levels in `xz`: `sandbox_init()` at start-up in `main()` (Landlock:
   `prctl(PR_SET_NO_NEW_PRIVS)` then a ruleset that leaves file access
   allowed; pledge: `"stdio rpath wpath cpath fattr"`);
   `sandbox_enable_read_only()` when every input goes to stdout
   (`to_stdout_only`; pledge `"stdio rpath"`); and
   `sandbox_enable_strict_if_allowed()` after the single input file is open
   (`io_open_src()`), which allows no new files at all (pledge `"stdio"`;
   Landlock ruleset with all handled rights and no rules; Capsicum
   `cap_enter()` plus `cap_rights_limit` on src, stdin, stdout, stderr and
   the abort pipe).
3. Strict mode is only *allowed* (`sandbox_allow_strict()`) when exactly one
   file is processed to standard output and `--files`/`--files0` were not
   used, because those could name an unknown number of files.
4. `prepare_for_strict_sandbox()` first touches locale/`strerror`/`iconv`
   data so that libc does not need to open files later.
5. `xzdec` has its own copy of the same idea (same three mechanisms).

Trap: the word "sandbox" names the files and functions, but the platform
answer comes from the three API names; an answer listing "Linux and BSD"
without pledge / Landlock / Capsicum has not read the code.

## Q3 — the whole decompression path

> Walk me through the full decompression path from input bytes to output,
> naming the main stages.

Reference points:

1. `lzma_code()` (`common.c`): action → `ISEQ_*`, calls
   `strm->internal->next.code()`, `LZMA_BUF_ERROR` on no progress
   (`allow_buf_error`), `LZMA_TIMED_OUT` → `LZMA_OK`.
2. Format detection: `auto_decode()` (0xFD → .xz, 0x4C → .lz under
   `HAVE_LZIP_DECODER`, else .lzma); the `xz` tool detects in `coder_init()`
   and calls `lzma_code()` with `avail_out = 0` first to surface header
   errors early.
3. Stream layer: `stream_decode()` states `SEQ_STREAM_HEADER → SEQ_BLOCK_HEADER
   → SEQ_BLOCK_INIT → SEQ_BLOCK_RUN → SEQ_INDEX → SEQ_STREAM_FOOTER →
   SEQ_STREAM_PADDING`; `SEQ_BLOCK_INIT` checks `lzma_raw_decoder_memusage()`
   against the memlimit; `stream_decode_mt()` adds the `THR` / `DIRECT` /
   `INDEX_WAIT_OUTPUT` states and `worker_decoder()`.
4. Block layer: `block_decode()` states `SEQ_CODE → SEQ_PADDING → SEQ_CHECK`;
   `lzma_check_update()` on produced output; `is_size_valid()`; Check
   compared with `memcmp` unless `ignore_check`.
5. Filter chain: `lzma_raw_decoder_init()` → `lzma_raw_coder_init()` with
   the `decoders[]` table; filters chain with
   `lzma_next_filter_init(…, filters + 1)`.
6. LZ layer: `decode_buffer()` in `lz_decoder.c` — dictionary window,
   `LZ_DICT_REPEAT_MAX` (288) wrap, `dict.limit`, copy from `dict.buf` to
   `out`.
7. LZMA2: `lzma2_decode()` control byte — 0x00 end, `>= 0xE0 || == 1` reset
   flags, `>= 0x80` LZMA chunk, otherwise uncompressed chunk (`SEQ_COPY`).
8. LZMA1: `lzma_decode()` with the range decoder (`rc_*`), literal / match /
   rep paths, `dict_repeat()`, resumable `SEQ_*` path and the fast path
   gated by `rc_is_fast_allowed()`.
9. Non-LZMA filters: `delta_decode()`, `simple_code()` (BCJ).
10. Index and Footer verification (see Q8); other containers
    (`alone_decode()`, `lzip_decode()`, `microlzma_decode()`) and the
    single-call wrappers as a note.

Trap: the grade is for the order of the stages and the hand-offs, not for
listing files.

## Q4 — test fixture integrity

> What mechanisms in this codebase verify or constrain the integrity of
> test fixture files?

Reference points (`tests/tuktest.h`, `tests/test_lzip_decoder.c`,
`tests/test_files.sh`, `tests/test_compress.sh`, `build-aux/license-check.sh`):

1. Loader constraints: `tuktest_file_from_srcdir()` / `_builddir()` →
   `tuktest_file_from_x()`: rejects empty files, files over
   `TUKTEST_FILE_SIZE_MAX` (`64L << 20`), read errors, and a file shorter
   than `ftell()` said; every failure is a hard error via
   `tuktest_error_impl()`.
2. Decode-and-compare: `test_lzip_decoder.c` stores CRC32s of the expected
   plaintext (`hello_world_crc = 0x15A2A343`,
   `trailing_garbage_crc = 0x87081A60`) and checks the decoder's output
   against them; `test_crc()` pins `bad-1-v1-crc32.lz` to `LZMA_DATA_ERROR`
   and to success under `LZMA_IGNORE_CHECK`.
3. Expected-failure pinning: `decode_expect_error()` asserts the exact
   error of each `bad-*` / `unsupported-*` fixture.
4. Behavioural corpus check: `test_files.sh` — every `good-*` must decode
   with `xz` and `xzdec`, every `bad-*` must fail, `unsupported-*` must fail
   except `unsupported-check.xz` with `-qQ`; feature gating via
   `have_feature()` (grep of `../config.h`, exit 77 to skip);
   `bad-3-index-uncomp-overflow.xz` must also fail under `xz -l`.
5. Round-trip check in `test_compress.sh` (`cmp` after compress +
   decompress); `create_compress_files.c` generates inputs with a fixed seed.
6. `license-check.sh` *exempts* `tests/files/*.{lz,lzma,xz}` and
   `xzgrep_expected_output` from the SPDX-tag requirement.
7. Conclusion the answer must reach: nothing verifies fixture **bytes** — no
   manifest, checksum or signature; integrity is enforced on size and on
   behaviour (decodes / fails as expected).

Trap: no identifier contains "integrity" or "fixture"; and the honest
answer is partly negative (point 7). An answer that invents a checksum
manifest is wrong.

## Q5 — padding, next stream, garbage

> When decoding concatenated .xz streams, how does the decoder distinguish
> valid stream padding, the start of another stream, and trailing garbage —
> and under what conditions does each case become an error?

Reference points (`SEQ_STREAM_PADDING`, `SEQ_STREAM_HEADER` in
`stream_decoder.c` / `stream_decoder_mt.c`):

1. Reached only with `LZMA_CONCATENATED`; without it `SEQ_STREAM_FOOTER`
   returns `LZMA_STREAM_END` and trailing bytes stay unconsumed (what
   `xz --single-stream` relies on).
2. Zero bytes are consumed while `coder->pos` counts them modulo 4.
3. Input ends: with `LZMA_FINISH`, `pos == 0` → `LZMA_STREAM_END`, else
   `LZMA_DATA_ERROR`; without `LZMA_FINISH` → `LZMA_OK`.
4. Non-zero byte at an offset not a multiple of 4: consumed,
   `LZMA_DATA_ERROR`.
5. Non-zero byte at a multiple of 4: left unconsumed,
   `stream_decoder_reset()` (fresh `lzma_index_hash`), `SEQ_STREAM_HEADER`.
6. Then 12 bytes (`LZMA_STREAM_HEADER_SIZE`): fewer → `LZMA_OK` (at real
   EOF the no-progress `LZMA_OK` becomes `LZMA_BUF_ERROR` in `lzma_code()`);
   bad magic → `LZMA_FORMAT_ERROR` converted to `LZMA_DATA_ERROR` because
   `first_stream` is false; bad CRC32 → `LZMA_DATA_ERROR`; reserved flags →
   `LZMA_OPTIONS_ERROR`.
7. Padding has no CRC — all structural. Fixtures: `bad-0pad-empty.xz`,
   `bad-0catpad-empty.xz`, `bad-0cat-header_magic.xz`, `good-0pad-empty.xz`,
   `good-0catpad-empty.xz`.

Trap: "garbage" is never detected as such — it is either bad padding (4) or
a bad Stream Header (6).

## Q6 — memory limit in the threaded decoder

> How is the decompression memory limit enforced in the multithreaded
> decoder, and what happens when a block would exceed the available memory?

Reference points (`stream_decoder_mt.c` `SEQ_BLOCK_INIT`,
`SEQ_BLOCK_THR_INIT`):

1. Two limits: `memlimit_threading` (soft; single-threaded mode may exceed
   it) and `memlimit_stop` (hard; never exceeded). `xz` sets them from
   `hardware_memlimit_mtdec_get()` and `hardware_memlimit_get(MODE_DECOMPRESS)`;
   with one thread the soft limit is 0.
2. Hard limit first: `mem_next_filters > memlimit_stop` → drain the output
   queue, `LZMA_OK` while output remains, then `LZMA_MEMLIMIT_ERROR`. It is
   the first check in `SEQ_BLOCK_INIT` so `lzma_memlimit_set()` + retry
   works (`base.h` notes the ≤ 5.2.6 single-threaded bug).
3. Direct-mode fallback, not an error: `is_direct_mode_needed()` for an
   unknown or too-large size, or `mem_next_block > memlimit_threading` →
   `SEQ_BLOCK_DIRECT_INIT`; the Block is decoded single-threaded and its
   real sizes appended to the Index hash after `LZMA_STREAM_END`.
4. Temporary wait, not an error: `block_can_start` in `SEQ_BLOCK_THR_INIT`
   needs `memlimit_threading - mem_in_use - outq.mem_in_use >=
   mem_next_block`, a free output buffer and a free or creatable thread;
   otherwise `read_output_and_wait()` waits (`LZMA_TIMED_OUT` → `LZMA_OK`).
5. Allocation failures are `LZMA_MEM_ERROR` and stop the threads.
6. `tests/test_memlimit.c` exercises resuming after raising the limit.

Trap: `memlimit_threading` never produces `LZMA_MEMLIMIT_ERROR`.

## Q7 — when xz deletes the input file

> Under what exact conditions can xz delete the original input file after
> compression or decompression, and what checks can prevent that deletion?

Reference points (`src/xz/file_io.c`, `src/xz/coder.c`, `src/xz/args.c`):

1. Deletion happens in `io_close_src()`: only if `success` is true, the
   source is not stdin, and `opt_keep_original` is false.
2. `opt_keep_original` is forced true by `--keep`, by `--stdout`, and in
   `--test` mode (`args.c`: "In test mode the data is written nowhere").
3. `success` is set in `coder_normal()` only on `LZMA_STREAM_END` with no
   trailing garbage (or with `allow_trailing_input` for `--single-stream`
   and `.lz`); any decoder error, write error or user abort leaves it false.
4. Before deleting, `io_unlink()` re-`stat`s the name (`lstat`, or `stat`
   under `--force`) and refuses if `st_dev` / `st_ino` differ from the
   opened file: "File seems to have been moved, not removing".
5. Files that are never deleted because they are never processed in place:
   non-regular files (skipped unless writing to stdout); without `--force`
   or `--keep`, files with setuid/setgid or sticky bits, or more than one
   hard link, are skipped; symlinks are followed only with `--stdout`,
   `--force` or `--keep`.
6. On failure the *destination* is removed instead (`io_close_dest()` with
   `success == false`).

Trap: `unlink` appears in several places; only the `io_close_src()` call is
the input deletion.

## Q8 — an attacker modifies the Index

> Suppose an attacker modifies the Index of an otherwise valid .xz file
> without changing the Blocks. Walk through every independent consistency or
> integrity check that can detect the modification, and identify
> modifications that could survive one check but fail a later one.

Reference points (`src/liblzma/common/index_hash.c`, `stream_decoder*.c`):

1. `lzma_index_hash` keeps `blocks` (filled while decoding) and `records`
   (filled while parsing the Index): count, sum of rounded Block sizes, sum
   of uncompressed sizes, `index_list_size`, and a running `LZMA_CHECK_BEST`
   hash over the ordered (unpadded, uncompressed) pairs.
2. `lzma_index_hash_decode()` checks in order: Index Indicator, record count
   equals `blocks.count`, each Unpadded Size in range, running totals never
   exceed the Block totals, Index Padding zero, totals equal, the two
   `LZMA_CHECK_BEST` hashes equal (`memcmp`), Index CRC32 (compiled out
   under `FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION`).
3. Survive-then-fail: CRC32 recomputed → caught by the structural checks;
   inflated size → the running-total check during parsing; deflated size →
   the final equality; reordered records with equal totals → the
   order-sensitive hash; wrong VLI width → `index_list_size`; wrong count →
   the count check before any sizes are read.
4. Threaded decoder: sizes pre-appended at `SEQ_BLOCK_INIT`, verified by the
   worker; `SEQ_INDEX_WAIT_OUTPUT` drains workers before the Index is parsed.
5. After the Index: `SEQ_STREAM_FOOTER` compares `lzma_index_hash_size()`
   with the Footer's Backward Size and `lzma_stream_flags_compare()` the
   Header/Footer flags — so an Index edit that changes its encoded length is
   also caught there even if everything else were consistent.
6. All errors are `LZMA_DATA_ERROR`, returned directly from the stream
   decoder.

Trap: the hash in (2) is computed on both sides inside the decoder and is
not stored in the file; calling it "the Index CRC" misses the mechanism.

## Q9 — the long concatenated-streams question

> *(the full text is in `benchmarks/xz-q10.md` (file name kept); it asks for the path from
> the last Block of one Stream to the first Block of the next, the failure
> cases under an attacker who can recompute CRCs, the concatenated vs.
> single-stream behaviour, and the interaction with the threaded decoder
> and memory limits.)*

Reference points: the union of Q8 (Index), Q5 (padding and next header)
and Q6 (memory limits), plus:

1. The Block Check is verified in the worker (`block_decode()` `SEQ_CHECK`),
   so the last Block's Check result only becomes visible at
   `SEQ_INDEX_WAIT_OUTPUT`.
2. Footer: `lzma_stream_footer_decode()` (magic, CRC32, reserved flags);
   `LZMA_FORMAT_ERROR` converted to `LZMA_DATA_ERROR` after the first Stream;
   then the two cross-checks of Q8 (5).
3. `coder->concatenated` is the switch; `--single-stream` returns
   `LZMA_STREAM_END` at the Footer and never inspects what follows.
4. Confirmations: `tests/files/README` fixtures (`bad-0-backward_size.xz`,
   `bad-0catpad-empty.xz`, `bad-0cat-header_magic.xz`, `bad-2-index-*.xz`),
   `tests/test_index_hash.c`, `tests/test_memlimit.c`,
   `doc/xz-file-format.txt`, `src/liblzma/api/lzma/container.h`.

---

## Grading sheet (fill per run)

| Q | run | Jev $ | writer $ | time s | points hit / total | wrong claims | missing |
|---|---|---|---|---|---|---|---|
| 1 | 1 | | | | /4 | | |
| 2 | 1 | | | | /5 | | |
| 3 | 1 | | | | /10 | | |
| 4 | 1 | | | | /7 | | |
| 5 | 1 | | | | /7 | | |
| 6 | 1 | | | | /6 | | |
| 7 | 1 | | | | /6 | | |
| 8 | 1 | | | | /6 | | |
| 9 | 1 | | | | /4 (+ Q5, Q6, Q8) | | |

Add a second row per question for run 2.
