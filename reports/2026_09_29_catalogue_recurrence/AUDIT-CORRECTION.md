# Independent reader correction; no scientific rerun

The initial summarize.py stopped before producing summary.json while decoding
the archived field `A0001` with int(). The preserved failure was:

```
ValueError: invalid literal for int() with base 10: 'A0001'
```

Scientific extraction had already completed using the installed public parsers,
which support Alpha-5. The original audit source is unchanged. summarize_v2.py
substitutes only the independent raw-line roster decoder; all support, mapping,
hash and result checks remain the original auditor. Alpha-5 uses letters A–Z
excluding I and O for prefixes 10–33. The installed sgp4.alpha5 implementation
was inspected to verify that encoding; the independent decoder uses an explicit
alphabet lookup. Three post-execution tests cover numeric/letter boundaries,
invalid fields and roster order/debris exclusion. They do not replace the four
prelaunch scientific tests. No model, threshold, input or scientific result was
changed and the mapping/census child was not rerun.
