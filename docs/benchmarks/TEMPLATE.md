# Simple community results template

Copy this block into the [benchmark README](README.md), replace the setup and
model placeholders, and enter the tokens/second you observed in SYNAPSE.
Add as many model rows as you like.

```markdown
## Your CPU + GPU (or CPU-only) + RAM

Community-reported results.

| Model / quantization | Mode (if known) | Reported tok/s | Notes (optional) |
| --- | --- | ---: | --- |
| Your model | — | YOUR RESULT | — |
```

That's all you need for a pull request. Quantization, mode and notes can be left
blank or marked `—` if you don't know them. Controls, logs, hashes, repeated runs
and separate reports are not required.

[How to submit your results](CONTRIBUTING.md).
