# Decisions

## D1 - The count is never capped by the listing limit

The first version returned `len(filings)` after collecting at most 50 rows. Apple has 50
filings in the last twelve months and would have been reported as exactly 50 forever:
a wrong number in the one field the node scores.

Now the index is walked in full for the window and the count is the true count, while the
`filings` and `urls` lists keep the newest 50 to bound the payload. A test pins it with
60 filings and asserts `60` and 50 urls.

## D2 - Full-text mentions are reported, never counted

Maersk returns 156 full-text hits for 2024. None of them are Maersk filings: they are
other companies' filings that mention Maersk. Counting them would answer a different
question than the one asked, and would do it confidently.

When no CIK resolves, the miner returns `unresolved`, keeps `filing_count` at 0, and
states the mention count in the note. The search still runs, because the number is
useful to a caller, and the honest place for it is a field that is not scored.

## D3 - Zero is a finding, unresolved is an absence

`filing_count: 0` with `ok` means the window was searched and nothing matched.
`unresolved` means the window was not searched, or the entity does not file with the SEC.
Collapsing the two is the failure mode this miner exists to avoid.

## D4 - Periods are parsed, not assumed

A free-text period invites a default window, and a default window silently answers a
different question. Accepted forms are listed in the README; everything else is
`unresolved` before any upstream call is made.
