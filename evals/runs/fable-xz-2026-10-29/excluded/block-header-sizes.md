<!-- model: claude-fable-5-1; harness agent transcript a56fe0fbded122cab.output -->

# Q07 — question as given

You are answering a question about the xz (XZ Utils / liblzma) codebase. The source is checked out at /tmp/claude-0/-home-claude/ce40d89e-7892-5c0e-ade6-383cef3904e1/scratchpad/xz_eval (commit 45d08abc). Use only that checkout: grep, read files, run git log/show inside it if useful. Do not use the web. Do not guess from memory: every claim must come from something you read in this checkout, and cite the file and function (and commit hash if from git) for each claim. If you could not find something, say so rather than inferring.

Question:
What exactly happens if an .xz Block Header declares compressed or uncompressed sizes that disagree with the bytes actually decoded? Trace where each mismatch is detected and what error reaches the caller.

Write the answer as you would for a senior engineer: precise, complete, with file/function citations. At the very end add a line "TOOLING: N files read, M search/shell commands run" with your honest counts.

# Answer

I have what I need. Here is the trace.

## Summary

Every size mismatch between the Block Header and the decoded bytes ends as **`LZMA_DATA_ERROR`** returned from `lzma_code()`. There is no distinct error code for "size mismatch"; it is folded into the generic corrupt-data error. The detection happens in three layers, depending on the direction of the mismatch and which decoder front-end is used.

## Layer 0: validation of the header values themselves (before any data is decoded)

`lzma_block_header_decode()` in `src/liblzma/common/block_header_decoder.c`:
- If the Compressed Size field is present (flag `0x40`), it is VLI-decoded and then `lzma_block_unpadded_size(block) == 0` is checked (line 77). `lzma_block_unpadded_size()` in `src/liblzma/common/block_util.c` returns 0 when `compressed_size == 0`, when it is not a valid VLI, or when `compressed_size + header_size + check_size > UNPADDED_SIZE_MAX` (lines 53-74). Result: `LZMA_DATA_ERROR` from the header decoder (test files `bad-1-block_header-4.xz` and `-5.xz`, `tests/files/README` lines 201-207).
- Uncompressed Size is only VLI-decoded here (line 85); it is not range-checked beyond VLI validity. `lzma_block_decoder_init()` (`block_decoder.c` line 223-225) re-checks `lzma_vli_is_valid(block->uncompressed_size)` and returns `LZMA_PROG_ERROR` if not, but a header that passed `lzma_vli_decode` cannot fail that.

Nothing at this layer compares header sizes to actual data; that starts in the next layer.

## Layer 1: the Block decoder (`block_decode()` in `src/liblzma/common/block_decoder.c`)

`lzma_block_decoder_init()` sets `compressed_limit` and `uncompressed_limit` to the declared sizes when known, otherwise to the maxima (lines 249-262). In `SEQ_CODE` the raw filter decoder is never given more input than `compressed_limit - compressed_size` nor more output room than `uncompressed_limit - uncompressed_size` (lines 79-88). This clamping is what makes every mismatch detectable; it was introduced by commit `1c9a5786` ("liblzma: Make Block decoder catch certain types of errors better", Lasse Collin, 2022-02-20), whose message says the test files `bad-1-lzma2-{9,10,11}.xz` exercise these paths.

The four mismatch directions:

**(a) Declared Compressed Size larger than the real compressed stream** (the filter chain reports end-of-payload early). The raw decoder returns `LZMA_STREAM_END` while `coder->compressed_size != block->compressed_size`. Lines 137-141: `is_size_valid()` fails -> `return LZMA_DATA_ERROR`.

**(b) Declared Uncompressed Size larger than the real output.** Same spot: `LZMA_STREAM_END` arrives with `uncompressed_size != block->uncompressed_size` -> lines 137-141 -> `LZMA_DATA_ERROR`. (`bad-1-lzma2-10.xz`, README lines 280-285.)

**(c) Declared Compressed Size smaller than the real stream.** The input window is clamped, so the raw decoder can never read past the declared count. Once `compressed_size == block->compressed_size` (`comp_done`) and the raw decoder still returns `LZMA_OK`:
- if there was still output space (`*out_pos < out_size`), line 113-114 -> `LZMA_DATA_ERROR` immediately: the decoder consumed everything it is allowed to consume but neither filled the output nor signalled the end;
- if the output buffer happened to be exactly full, the block decoder returns `LZMA_OK`; on the next call `in_stop == *in_pos` (zero input), and the raw decoder (LZMA2's `lzma2_decode()` in `src/liblzma/lzma/lzma2_decoder.c` only loops without input while in `SEQ_LZMA`, line 65) either emits pending output or makes no progress; either way, as soon as it returns `LZMA_OK` with output room left, line 113 fires with `LZMA_DATA_ERROR`.
- Special sub-case: both counts match the header exactly but the end-of-payload marker byte has not been seen (LZMA2 needs one more `0x00` control byte, `lzma2_decoder.c` lines 72-73). Then `comp_done && uncomp_done` with `ret == LZMA_OK` -> line 107-108 -> `LZMA_DATA_ERROR`. This is `bad-1-lzma2-11.xz` (README lines 287-290).

**(d) Declared Uncompressed Size smaller than the real output.** The output window is clamped, so the raw decoder can never write past the declared count. Once `uncompressed_size == block->uncompressed_size` (`uncomp_done`) and the raw decoder returns `LZMA_OK` while unconsumed input remains (`*in_pos < in_size`), line 121-122 -> `LZMA_DATA_ERROR`. (`bad-1-lzma2-9.xz`, README lines 276-278.) If the input also ran out at that exact point the block decoder returns `LZMA_OK` and waits for more input; when it arrives, the raw decoder gets zero output space and either consumes the end marker (-> `LZMA_STREAM_END`, sizes then compared at line 137) or stalls with input left (-> line 121). If the application instead calls `LZMA_FINISH` with no more input, the no-progress detector in `lzma_code()` (`src/liblzma/common/common.c` lines 311-323) returns `LZMA_BUF_ERROR` on the second zero-progress call; that is the truncated-input path, not a size-mismatch verdict.

After a successful `LZMA_STREAM_END` with matching sizes, lines 145-146 write the verified counts back into `block->compressed_size` / `block->uncompressed_size` for the caller. Note the Check field (`SEQ_CHECK`, lines 179-196) is only compared after the sizes are verified, so a size mismatch is reported before, and independently of, any CRC/SHA mismatch. `lzma_check_update()` runs on every produced byte regardless (line 128-130).

I found no distinct error code anywhere in `block_decode()`: every size-related branch returns `LZMA_DATA_ERROR`.

## Layer 2: how the error reaches `lzma_code()` callers

- **Single-threaded `.xz` decoder** (`stream_decode()` in `src/liblzma/common/stream_decoder.c`, `SEQ_BLOCK_RUN`, lines 259-266): `if (ret != LZMA_STREAM_END) return ret;` -> the `LZMA_DATA_ERROR` propagates unchanged. In `lzma_code()` (`common.c` lines 362-366) a fatal code sets `internal->sequence = ISEQ_ERROR`, so any later `lzma_code()` call returns `LZMA_PROG_ERROR` (line 280-282). `lzma_block_header_decode()` errors from Layer 0 propagate the same way via `return_if_error` at line 209.
- **Threaded decoder** (`src/liblzma/common/stream_decoder_mt.c`): threaded mode is only used when both sizes are present in the Block Header (`is_direct_mode_needed()` check, lines 1248-1253); otherwise it falls back to the direct single-thread path (lines 1599-1631), which behaves like above. In threaded mode the worker (`worker_decoder()`, lines 440-511) runs `block_decode()`; a non-`LZMA_STREAM_END` result is stored in `outbuf->finish_ret` and `coder->thread_error`. The main thread returns it from `read_output_and_wait()` when it reaches that outbuf via `lzma_outq_read()` (lines 677-701), or immediately if `LZMA_FAIL_FAST` is set (lines 712-717). The asserts at lines 480-482 document the invariant that `LZMA_STREAM_END` implies `in_pos == in_size` and `out_pos == uncompressed_size`, i.e. the MT decoder relies entirely on `block_decode()` for the size verification.
- **`lzma_block_buffer_decode()`** (`src/liblzma/common/block_buffer_decoder.c` lines 38-70): `LZMA_DATA_ERROR` passes through untouched; a stalled `LZMA_OK` is converted to `LZMA_DATA_ERROR` if all input was consumed, else `LZMA_BUF_ERROR`; positions are restored on error.

## Layer 3: cross-check against the Index (independent of the Block Header)

After each Block finishes, both stream decoders call `lzma_index_hash_append()` with `lzma_block_unpadded_size(&block_options)` and `block_options.uncompressed_size` (`stream_decoder.c` lines 270-273; `stream_decoder_mt.c` lines 1295-1298 before decoding in threaded mode, 1635-1638 in direct mode). Because `block_decode()` has already written the real counts into `block_options`, these are the actual sizes. When the Index is read, `lzma_index_hash_decode()` in `src/liblzma/common/index_hash.c` returns `LZMA_DATA_ERROR` if the record count differs (line 205-206), if cumulative sizes exceed the decoded totals while reading records (lines 250-256), if the final totals differ (lines 284-290), or if the per-record hashes differ (lines 295-298). So a Block whose header sizes were correct but whose Index record is wrong also ends in `LZMA_DATA_ERROR`, just later (at the Index), as in `bad-2-index-1.xz` (README line 213).

For `xz --list` (no decompression), `parse_block_header()` in `src/xz/list.c` lines 506-529 compares header sizes against the Index record via `lzma_block_compressed_size()` (`block_util.c` lines 34-36 return `LZMA_DATA_ERROR` on a Compressed Size mismatch) and explicitly compares `block.uncompressed_size` with `iter->block.uncompressed_size` (lines 516-519); either mismatch jumps to `data_error`.

TOOLING: 10 files read, 8 search/shell commands run
