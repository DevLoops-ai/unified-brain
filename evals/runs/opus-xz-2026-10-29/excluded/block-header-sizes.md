<!-- model: claude-opus-5-5; harness agent transcript adda8dda261259c27.output -->

# Q07 — question as given

You are answering a question about the xz (XZ Utils / liblzma) codebase. The source is checked out at /tmp/claude-0/-home-claude/ce40d89e-7892-5c0e-ade6-383cef3904e1/scratchpad/xz_eval (commit 45d08abc). Use only that checkout: grep, read files, run git log/show inside it if useful. Do not use the web. Do not guess from memory: every claim must come from something you read in this checkout, and cite the file and function (and commit hash if from git) for each claim. If you could not find something, say so rather than inferring.

Question:
What exactly happens if an .xz Block Header declares compressed or uncompressed sizes that disagree with the bytes actually decoded? Trace where each mismatch is detected and what error reaches the caller.

Write the answer as you would for a senior engineer: precise, complete, with file/function citations. At the very end add a line "TOOLING: N files read, M search/shell commands run" with your honest counts.

# Answer

Short answer: the mismatch is always caught, and the caller gets `LZMA_DATA_ERROR` (xz prints "Compressed data is corrupt"). Most cases are caught inside `block_decode()` in `src/liblzma/common/block_decoder.c`. The rest are caught later, when the Index is checked. Two exceptions, covered below, can return `LZMA_BUF_ERROR` instead.

## 1. Reading the header: values are only range-checked

In `lzma_block_header_decode()` (`block_header_decoder.c`), the two sizes are read as numbers and are not compared to any data yet.
- **Compressed Size:** it must decode as a valid number, and `lzma_block_unpadded_size()` (`block_util.c`) must accept it. It rejects zero and a total Block size above the maximum. A bad value returns `LZMA_DATA_ERROR` (lines 72-78).
- **Missing size fields:** each one is set to `LZMA_VLI_UNKNOWN`.

In `lzma_block_decoder_init()` (`block_decoder.c`, lines 249-262), the declared sizes become hard limits, `compressed_limit` and `uncompressed_limit`. When a size is unknown, the limit is the largest value the format allows instead.

## 2. The filter can never go past the declared sizes

In `block_decode()`, state `SEQ_CODE` (lines 79-88), the input and output windows given to the filter chain (for example LZMA2) are cut to `limit - bytes_so_far`. So the filter physically cannot read more than Compressed Size or write more than Uncompressed Size. "Too much data" therefore shows up as "the filter returned `LZMA_OK` without finishing". Commit 1c9a5786 (2022-02-20) added this. Its message says it was done so the threaded decoder has no corner cases. It also says the test files `bad-1-lzma2-{9,10,11}.xz` cover these conditions; `tests/files/README` describes them.

## 3. Each kind of mismatch (all in `block_decode()`)

| Case | Where | Result |
|---|---|---|
| Filter ends (`LZMA_STREAM_END`) before reaching a declared size, in either direction | lines 137-141, `is_size_valid()` (lines 56-60; an unknown size always passes) | `LZMA_DATA_ERROR` |
| Filter returns `LZMA_OK` after using exactly Compressed Size and producing exactly Uncompressed Size (no end marker) | lines 107-108 | `LZMA_DATA_ERROR` (bad-1-lzma2-11) |
| All declared input used, but the filter still wants more and had free output space | lines 113-114 (`comp_done && *out_pos < out_size`) | `LZMA_DATA_ERROR` |
| All declared output produced, but the filter wants to produce more while input is still available | lines 121-122 (`uncomp_done && *in_pos < in_size`) | `LZMA_DATA_ERROR` |
| Same as above, but the caller's input buffer is empty at that moment | falls through to line 132 | returns `LZMA_OK` and waits for more input (see note 1 below) |

Two details:
- `comp_done` and `uncomp_done` compare against `coder->block->*_size`. When a size is `LZMA_VLI_UNKNOWN` the running count can never equal it, so these early checks only fire for sizes the header actually declared.
- The checks are ordered. The integrity Check (CRC32 / CRC64 / SHA-256) is only reached after the sizes passed. It is computed over the output that was actually produced and compared at lines 189-194, giving `LZMA_DATA_ERROR` on mismatch. A non-zero Block Padding byte gives `LZMA_DATA_ERROR` at line 165.

**Note 1.** Looking at `lzma_code()` in `common.c` (lines 310-323): if a call makes no input or output progress twice in a row, it is turned into `LZMA_BUF_ERROR`. So if the input really ends at that point, I expect the caller to see `LZMA_BUF_ERROR`, not `LZMA_DATA_ERROR`. I did not run this.

## 4. Sizes not given in the header: checked against the Index

1. If the header left a size out, the counted value is written back into `block->compressed_size` / `uncompressed_size` (lines 145-146).
2. `stream_decode()`, state `SEQ_BLOCK_RUN` (`stream_decoder.c`, lines 270-273), passes the counted Unpadded Size and Uncompressed Size to `lzma_index_hash_append()`.
3. `lzma_index_hash_decode()` (`index_hash.c`) then compares them with the Index records:
   - lines 250-256: running totals go past what the Blocks had
   - lines 284-290: final totals differ
   - lines 295-298: hash of the size list differs

   All three return `LZMA_DATA_ERROR`.

This step also catches a header size that matches the data but disagrees with the Index.

## 5. What reaches each caller

- **`lzma_stream_decoder` (single-threaded):** the error from `block_decode()` is returned unchanged from `SEQ_BLOCK_RUN` (line 265-266), so the application gets `LZMA_DATA_ERROR` from `lzma_code()`. `message_strm()` in `src/xz/message.c` (line 812-813) turns it into "Compressed data is corrupt".
- **`lzma_stream_decoder_mt` (threaded):**
  - If either size is missing or larger than `SIZE_MAX / 3`, the Block is decoded in direct mode (`is_direct_mode_needed()`, lines 945-948). That path (lines 1620-1638) behaves like single-threaded.
  - Otherwise the main thread adds the header's sizes to the Index hash before decoding (lines 1295-1298). The worker gets an input buffer of exactly `comp_blk_size()` (Compressed Size rounded up to 4, plus the Check) and an output buffer of exactly Uncompressed Size (lines 1446-1448, 1485). So the checks in section 3 are the only protection, and the asserts at lines 480-482 depend on them.
  - The worker's error goes into `outbuf->finish_ret` and `coder->thread_error` (lines 502-511).
  - The application receives it from `lzma_outq_read()` (`outqueue.c`, which returns `finish_ret`) once all output before the broken Block has been delivered. With `LZMA_FAIL_FAST` it is returned at once (`read_output_and_wait()`, lines 712-718).
  - Separately, with `LZMA_FINISH` + fail-fast, not enough input left for the Block gives `LZMA_DATA_ERROR` (lines 1516-1528).
- **`lzma_block_buffer_decode()`** (`block_buffer_decoder.c`, lines 42-70): `LZMA_DATA_ERROR` is passed through. If the decoder returns `LZMA_OK` and all input was used, that becomes `LZMA_DATA_ERROR`; otherwise it becomes `LZMA_BUF_ERROR`. On any error `*in_pos` and `*out_pos` are put back to their starting values.
- **`lzma_block_compressed_size()`** (`block_util.c`, lines 33-36): for callers that already know the Unpadded Size from the Index. If that disagrees with the header's Compressed Size, it returns `LZMA_DATA_ERROR`. I did not trace who calls it.

Not checked: other filters' behaviour at the output limit, beyond the LZMA2 cases described in the test README.

TOOLING: 8 files read (plus 3 more partly checked with grep/sed: outqueue.c, tests/files/README, xz/message.c), 8 search/shell commands run
